"""
Segurança e privacidade (LGPD) da Prova de Conceito.

  * Autenticação: login com senha guardada como hash PBKDF2 + token de sessão com validade
  * Autorização por perfil (princípio do menor privilégio): cada perfil só vê o necessário
  * Minimização: CPF e CNS mascarados para quem não precisa do número completo
  * Auditoria: todo acesso (inclusive tentativas negadas) é registrado em logs/auditoria.csv
  * Proteção contra tentativas repetidas de senha (bloqueio temporário)
"""
import csv
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from datetime import datetime

from .normalizacao import mascarar_cns, mascarar_cpf

VALIDADE_SESSAO = 30 * 60          # 30 minutos
MAX_TENTATIVAS = 5                 # erros de senha permitidos...
JANELA_BLOQUEIO = 5 * 60           # ...dentro de 5 minutos

PERMISSOES = {
    "medico":     {"ver_clinico": True,  "cpf_completo": True,  "ver_analise": True,  "ver_auditoria": False, "ver_prontuarios": True},
    "enfermeiro": {"ver_clinico": True,  "cpf_completo": False, "ver_analise": False, "ver_auditoria": False, "ver_prontuarios": True},
    "recepcao":   {"ver_clinico": False, "cpf_completo": False, "ver_analise": False, "ver_auditoria": False, "ver_prontuarios": True},
    "gestor":     {"ver_clinico": False, "cpf_completo": False, "ver_analise": True,  "ver_auditoria": True,  "ver_prontuarios": False},
}

_trava = threading.Lock()


class Seguranca:
    def __init__(self, pasta_dados, arquivo_auditoria):
        with open(os.path.join(pasta_dados, "usuarios.json"), encoding="utf-8") as f:
            self.usuarios = json.load(f)
        self.arquivo_auditoria = arquivo_auditoria
        self.sessoes = {}
        self.falhas = {}
        os.makedirs(os.path.dirname(arquivo_auditoria), exist_ok=True)
        if not os.path.exists(arquivo_auditoria):
            with open(arquivo_auditoria, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(["data_hora", "usuario", "perfil", "acao", "recurso", "resultado"])

    # ------------------------------------------------------------------ auditoria
    def registrar(self, usuario, perfil, acao, recurso="-", resultado="ok"):
        with _trava:
            with open(self.arquivo_auditoria, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        usuario, perfil, acao, recurso, resultado])

    def ler_auditoria(self, limite=200):
        with _trava:
            with open(self.arquivo_auditoria, encoding="utf-8") as f:
                linhas = list(csv.DictReader(f))
        return list(reversed(linhas))[:limite]

    # ------------------------------------------------------------------ login
    def _bloqueado(self, login):
        agora = time.time()
        recentes = [t for t in self.falhas.get(login, []) if agora - t < JANELA_BLOQUEIO]
        self.falhas[login] = recentes
        return len(recentes) >= MAX_TENTATIVAS

    def autenticar(self, login, senha):
        """Devolve (token, dados_do_usuario) ou (None, motivo)."""
        login = str(login or "").strip().lower()
        if self._bloqueado(login):
            self.registrar(login, "-", "login", "-", "bloqueado")
            return None, "Muitas tentativas. Aguarde alguns minutos e tente de novo."
        u = self.usuarios.get(login)
        senha_ok = False
        if u:
            calculado = hashlib.pbkdf2_hmac("sha256", str(senha or "").encode(), bytes.fromhex(u["sal"]), 120_000).hex()
            senha_ok = hmac.compare_digest(calculado, u["hash"])
        if not senha_ok:
            self.falhas.setdefault(login, []).append(time.time())
            self.registrar(login or "-", u["perfil"] if u else "-", "login", "-", "falha")
            return None, "Usuário ou senha incorretos."
        token = secrets.token_urlsafe(32)
        self.sessoes[token] = {"login": login, "perfil": u["perfil"], "nome": u["nome"],
                               "expira": time.time() + VALIDADE_SESSAO}
        self.registrar(login, u["perfil"], "login", "-", "ok")
        return token, self.sessoes[token]

    def sessao(self, token):
        s = self.sessoes.get(token)
        if not s:
            return None
        if s["expira"] < time.time():
            del self.sessoes[token]
            return None
        return s

    def encerrar(self, token):
        s = self.sessoes.pop(token, None)
        if s:
            self.registrar(s["login"], s["perfil"], "logout")


# ---------------------------------------------------------------------- filtros por perfil
def permissoes(perfil):
    return PERMISSOES.get(perfil, {})


def resumo_paciente(p, perfil):
    """Dados mínimos para a lista de busca."""
    perm = permissoes(perfil)
    return {
        "id": p["id"], "nome": p["nome"], "nascimento": p["nascimento"], "municipio": p["municipio"],
        "cpf": p["cpf"] if perm.get("cpf_completo") else None,
        "cpf_exibicao": _cpf_exibicao(p["cpf"], perm),
        "fontes": p["fontes"],
        "n_alertas": len(p["alertas"]) if perm.get("ver_clinico") else 0,
    }


def _cpf_exibicao(cpf, perm):
    if not cpf:
        return "não informado"
    if perm.get("cpf_completo"):
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    return mascarar_cpf(cpf)


def filtrar_prontuario(p, perfil):
    """Aplica o princípio do menor privilégio ao prontuário unificado."""
    perm = permissoes(perfil)
    saida = resumo_paciente(p, perfil)
    saida["sexo"] = p["sexo"]
    saida["cns_exibicao"] = mascarar_cns(p["cns"]) if p["cns"] else "não informado"
    saida["ver_clinico"] = bool(perm.get("ver_clinico"))
    if perm.get("ver_clinico"):
        for campo in ("alergias", "medicamentos", "condicoes", "vacinas", "atendimentos", "alertas"):
            saida[campo] = p[campo]
    else:
        for campo in ("alergias", "medicamentos", "condicoes", "vacinas", "atendimentos", "alertas"):
            saida[campo] = []
    return saida
