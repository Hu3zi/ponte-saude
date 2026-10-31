"""
Servidor web da Prova de Conceito (só biblioteca padrão do Python - nada para instalar).

Rotas da API:
  POST /api/login               {usuario, senha}  -> token de sessão
  POST /api/logout
  GET  /api/eu                  -> dados da sessão
  GET  /api/pacientes?busca=    -> lista/busca (nome, CPF ou ID)
  GET  /api/pacientes/<id>      -> prontuário unificado (filtrado pelo perfil)
  GET  /api/analise             -> indicadores da análise de dados
  GET  /api/auditoria           -> últimos acessos registrados
"""
import json
import mimetypes
import os
import re
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .analise import analisar
from .normalizacao import normalizar_texto, so_digitos
from .seguranca import Seguranca, filtrar_prontuario, permissoes, resumo_paciente
from .unificacao import unificar

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA_WEB = os.path.join(RAIZ, "web")
PASTA_DADOS = os.path.join(RAIZ, "dados")


class Estado:
    """Dados carregados uma vez, na inicialização."""
    def __init__(self):
        self.pacientes, self.registros = unificar(PASTA_DADOS)
        self.por_id = {p["id"]: p for p in self.pacientes}
        self.analise = analisar(self.pacientes, self.registros)
        self.seg = Seguranca(PASTA_DADOS, os.path.join(RAIZ, "logs", "auditoria.csv"))


def criar_handler(estado):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PonteSaude/1.0"

        # ---------------------------------------------------------- utilitários
        def log_message(self, formato, *args):  # silencia o log padrão
            pass

        def _enviar(self, codigo, corpo, tipo="application/json; charset=utf-8"):
            if not isinstance(corpo, bytes):
                corpo = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(corpo)

        def _corpo_json(self):
            try:
                tamanho = min(int(self.headers.get("Content-Length", 0)), 10_000)
                return json.loads(self.rfile.read(tamanho) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return None

        def _sessao(self):
            auth = self.headers.get("Authorization", "")
            return estado.seg.sessao(auth[7:]) if auth.startswith("Bearer ") else None

        def _exigir(self, permissao):
            """Devolve a sessão se o usuário estiver logado e tiver a permissão; senão responde com erro."""
            s = self._sessao()
            if not s:
                self._enviar(401, {"erro": "Sessão expirada. Entre novamente."})
                return None
            if not permissoes(s["perfil"]).get(permissao):
                estado.seg.registrar(s["login"], s["perfil"], "acesso_negado", self.path.split("?")[0], "negado")
                self._enviar(403, {"erro": "Seu perfil não tem permissão para ver este conteúdo."})
                return None
            return s

        # ---------------------------------------------------------- GET
        def do_GET(self):
            url = urlparse(self.path)
            caminho = url.path
            if caminho.startswith("/api/"):
                return self._api_get(caminho, parse_qs(url.query))
            return self._estatico(caminho)

        def _estatico(self, caminho):
            if caminho in ("/", ""):
                caminho = "/index.html"
            alvo = os.path.normpath(os.path.join(PASTA_WEB, caminho.lstrip("/")))
            if not alvo.startswith(PASTA_WEB) or not os.path.isfile(alvo):
                return self._enviar(404, {"erro": "Página não encontrada."})
            tipo = mimetypes.guess_type(alvo)[0] or "application/octet-stream"
            with open(alvo, "rb") as f:
                self._enviar(200, f.read(), tipo + ("; charset=utf-8" if tipo.startswith("text/") else ""))

        def _api_get(self, caminho, query):
            if caminho == "/api/eu":
                s = self._sessao()
                if not s:
                    return self._enviar(401, {"erro": "Sessão expirada."})
                return self._enviar(200, {"usuario": s["login"], "nome": s["nome"], "perfil": s["perfil"],
                                          "permissoes": permissoes(s["perfil"])})

            if caminho == "/api/pacientes":
                s = self._exigir("ver_prontuarios")
                if not s:
                    return
                busca = (query.get("busca", [""])[0] or "").strip()
                termo, digitos = normalizar_texto(busca), so_digitos(busca)
                resultado = []
                for p in estado.pacientes:
                    if not busca or termo in normalizar_texto(p["nome"]) or termo == p["id"].lower() \
                            or (len(digitos) >= 3 and p["cpf"] and digitos in p["cpf"]):
                        resultado.append(resumo_paciente(p, s["perfil"]))
                estado.seg.registrar(s["login"], s["perfil"], "busca", f"'{busca}'" if busca else "(todos)", f"{len(resultado)} resultado(s)")
                return self._enviar(200, {"total": len(resultado), "pacientes": resultado[:100]})

            m = re.fullmatch(r"/api/pacientes/(PS-\d{4})", caminho)
            if m:
                s = self._exigir("ver_prontuarios")
                if not s:
                    return
                p = estado.por_id.get(m.group(1))
                if not p:
                    return self._enviar(404, {"erro": "Paciente não encontrado."})
                estado.seg.registrar(s["login"], s["perfil"], "ver_prontuario", p["id"])
                return self._enviar(200, filtrar_prontuario(p, s["perfil"]))

            if caminho == "/api/analise":
                if not self._exigir("ver_analise"):
                    return
                return self._enviar(200, estado.analise)

            if caminho == "/api/auditoria":
                if not self._exigir("ver_auditoria"):
                    return
                return self._enviar(200, {"eventos": estado.seg.ler_auditoria()})

            return self._enviar(404, {"erro": "Rota não encontrada."})

        # ---------------------------------------------------------- POST
        def do_POST(self):
            caminho = urlparse(self.path).path
            if caminho == "/api/login":
                dados = self._corpo_json()
                if dados is None:
                    return self._enviar(400, {"erro": "Requisição inválida."})
                token, info = estado.seg.autenticar(dados.get("usuario"), dados.get("senha"))
                if not token:
                    return self._enviar(401, {"erro": info})
                return self._enviar(200, {"token": token, "usuario": info["login"], "nome": info["nome"],
                                          "perfil": info["perfil"], "permissoes": permissoes(info["perfil"])})
            if caminho == "/api/logout":
                auth = self.headers.get("Authorization", "")
                if auth.startswith("Bearer "):
                    estado.seg.encerrar(auth[7:])
                return self._enviar(200, {"ok": True})
            return self._enviar(404, {"erro": "Rota não encontrada."})

    return Handler


def iniciar(porta=8000, abrir_navegador=True):
    estado = Estado()
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), criar_handler(estado))
    url = f"http://127.0.0.1:{porta}"
    print(f"\nPonte Saúde rodando em {url}")
    print("Para parar: Ctrl+C\n")
    if abrir_navegador:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        servidor.server_close()
