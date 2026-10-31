"""Testes automatizados do Ponte Saúde (rode com: python ponte_saude.py testar)."""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import gerar_dados
from ponte.normalizacao import (cpf_valido, formatar_cpf, idade, mascarar_cpf,
                                normalizar_cpf, normalizar_data, normalizar_texto)
from ponte.seguranca import Seguranca, filtrar_prontuario
from ponte.servidor import Estado, criar_handler
from ponte.unificacao import unificar

PASTA = tempfile.mkdtemp(prefix="ponte_testes_")


def setUpModule():
    esus, tasy = gerar_dados.gerar()
    for nome, conteudo in (("esus.json", esus), ("tasy.json", tasy), ("usuarios.json", gerar_dados.gerar_usuarios())):
        with open(os.path.join(PASTA, nome), "w", encoding="utf-8") as f:
            json.dump(conteudo, f, ensure_ascii=False)


class TestNormalizacao(unittest.TestCase):
    def test_texto_sem_acento_e_minusculo(self):
        self.assertEqual(normalizar_texto("  JOÃO   da Silva "), "joao da silva")

    def test_cpf_valido_e_invalido(self):
        self.assertTrue(cpf_valido("529.982.247-25"))
        self.assertFalse(cpf_valido("111.111.111-11"))
        self.assertFalse(cpf_valido("123.456.789-00"))
        self.assertIsNone(normalizar_cpf(""))

    def test_cpf_formatos_diferentes_viram_o_mesmo(self):
        self.assertEqual(normalizar_cpf("529.982.247-25"), normalizar_cpf("52998224725"))

    def test_mascara_cpf(self):
        self.assertEqual(mascarar_cpf("52998224725"), "***.982.247-**")
        self.assertEqual(formatar_cpf("52998224725"), "529.982.247-25")

    def test_datas_em_dois_formatos(self):
        self.assertEqual(normalizar_data("15/03/1980"), "1980-03-15")
        self.assertEqual(normalizar_data("1980-03-15"), "1980-03-15")
        self.assertIsNone(normalizar_data("31/02/1980"))
        self.assertIsNone(normalizar_data(""))

    def test_idade(self):
        from datetime import date
        self.assertEqual(idade("2000-06-15", hoje=date(2026, 6, 14)), 25)
        self.assertEqual(idade("2000-06-15", hoje=date(2026, 6, 15)), 26)


class TestUnificacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pacientes, cls.registros = unificar(PASTA)

    def test_unificacao_reduz_registros(self):
        self.assertLess(len(self.pacientes), len(self.registros))
        self.assertEqual(len(self.pacientes), 44)

    def test_cpfs_nao_se_repetem_entre_pacientes(self):
        cpfs = [p["cpf"] for p in self.pacientes if p["cpf"]]
        self.assertEqual(len(cpfs), len(set(cpfs)))

    def test_ids_unicos(self):
        ids = [p["id"] for p in self.pacientes]
        self.assertEqual(len(ids), len(set(ids)))

    def test_paciente_sem_cpf_no_tasy_e_unido_por_nome_e_nascimento(self):
        alvo = [p for p in self.pacientes if any(a["tipo"] == "cpf_ausente" for a in p["alertas"])]
        self.assertEqual(len(alvo), 3)
        for p in alvo:
            self.assertEqual(p["fontes"], ["e-SUS", "Tasy"])

    def test_detecta_medicamento_em_conflito_com_alergia(self):
        criticos = [p for p in self.pacientes if any(a["gravidade"] == "critica" for a in p["alertas"])]
        self.assertEqual(len(criticos), 2)
        for p in criticos:
            self.assertIn("Dipirona", p["alertas"][0]["mensagem"])

    def test_detecta_nascimento_divergente_e_duplicados(self):
        tipos = [a["tipo"] for p in self.pacientes for a in p["alertas"]]
        self.assertEqual(tipos.count("nascimento_divergente"), 2)
        self.assertEqual(tipos.count("cadastro_duplicado"), 5)

    def test_alergia_aparece_com_a_fonte_de_origem(self):
        p = next(p for p in self.pacientes if any(a["tipo"] == "alergia_unica_fonte" for a in p["alertas"]))
        self.assertTrue(any(len(a["fontes"]) == 1 for a in p["alergias"]))

    def test_homonimos_com_cpf_diferente_nao_sao_unidos(self):
        from ponte.unificacao import agrupar, _registro_base
        a = _registro_base("e-SUS", 1, "Ana Silva", "529.982.247-25", "01/01/1990", "X", "F")
        b = _registro_base("Tasy", 1, "Ana Silva", "11144477735", "1990-01-01", "X", "F")
        self.assertEqual(len(agrupar([a, b])), 2)


class TestSeguranca(unittest.TestCase):
    def setUp(self):
        self.seg = Seguranca(PASTA, os.path.join(tempfile.mkdtemp(), "auditoria.csv"))
        self.pacientes, _ = unificar(PASTA)

    def test_login_correto_e_incorreto(self):
        token, _ = self.seg.autenticar("medico", "med123")
        self.assertIsNotNone(token)
        token2, motivo = self.seg.autenticar("medico", "errada")
        self.assertIsNone(token2)
        self.assertIn("incorretos", motivo)

    def test_bloqueio_apos_varias_tentativas(self):
        for _ in range(5):
            self.seg.autenticar("recepcao", "errada")
        token, motivo = self.seg.autenticar("recepcao", "rec123")
        self.assertIsNone(token)
        self.assertIn("Muitas tentativas", motivo)

    def test_senha_nao_fica_em_texto_puro(self):
        with open(os.path.join(PASTA, "usuarios.json"), encoding="utf-8") as f:
            conteudo = f.read()
        for senha in ("med123", "enf123", "rec123", "ges123"):
            self.assertNotIn(senha, conteudo)

    def test_perfis_veem_dados_diferentes(self):
        p = next(p for p in self.pacientes if p["cpf"] and p["alergias"])
        medico = filtrar_prontuario(p, "medico")
        enf = filtrar_prontuario(p, "enfermeiro")
        rec = filtrar_prontuario(p, "recepcao")
        self.assertEqual(medico["cpf_exibicao"], f"{p['cpf'][:3]}.{p['cpf'][3:6]}.{p['cpf'][6:9]}-{p['cpf'][9:]}")
        self.assertTrue(enf["cpf_exibicao"].startswith("***"))
        self.assertTrue(enf["alergias"])
        self.assertEqual(rec["alergias"], [])
        self.assertFalse(rec["ver_clinico"])
        self.assertIsNone(rec["cpf"])

    def test_auditoria_registra_eventos(self):
        self.seg.autenticar("medico", "med123")
        self.seg.autenticar("medico", "errada")
        eventos = self.seg.ler_auditoria()
        self.assertEqual([e["resultado"] for e in eventos][:2], ["falha", "ok"])


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ponte.servidor as servidor
        servidor.PASTA_DADOS = PASTA
        estado = Estado()
        estado.seg = Seguranca(PASTA, os.path.join(tempfile.mkdtemp(), "auditoria.csv"))
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), criar_handler(estado))
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def chamar(self, caminho, token=None, corpo=None):
        req = urllib.request.Request(self.base + caminho, data=json.dumps(corpo).encode() if corpo is not None else None,
                                     headers={"Content-Type": "application/json"})
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def login(self, usuario, senha):
        return self.chamar("/api/login", corpo={"usuario": usuario, "senha": senha})[1].get("token")

    def test_sem_login_nao_acessa(self):
        self.assertEqual(self.chamar("/api/pacientes")[0], 401)

    def test_medico_busca_e_abre_prontuario(self):
        t = self.login("medico", "med123")
        status, dados = self.chamar("/api/pacientes?busca=", t)
        self.assertEqual((status, dados["total"]), (200, 44))
        status, p = self.chamar("/api/pacientes/" + dados["pacientes"][0]["id"], t)
        self.assertEqual(status, 200)
        self.assertIn("alergias", p)

    def test_busca_por_nome_sem_acento(self):
        t = self.login("medico", "med123")
        _, todos = self.chamar("/api/pacientes", t)
        nome = todos["pacientes"][0]["nome"].upper()
        _, achados = self.chamar("/api/pacientes?busca=" + urllib.request.quote(nome), t)
        self.assertGreaterEqual(achados["total"], 1)

    def test_gestor_nao_ve_prontuario_mas_ve_analise(self):
        t = self.login("gestor", "ges123")
        self.assertEqual(self.chamar("/api/pacientes", t)[0], 403)
        self.assertEqual(self.chamar("/api/analise", t)[0], 200)
        self.assertEqual(self.chamar("/api/auditoria", t)[0], 200)

    def test_recepcao_nao_ve_dados_clinicos_nem_analise(self):
        t = self.login("recepcao", "rec123")
        _, lista = self.chamar("/api/pacientes", t)
        status, p = self.chamar("/api/pacientes/" + lista["pacientes"][0]["id"], t)
        self.assertEqual(p["alergias"], [])
        self.assertEqual(self.chamar("/api/analise", t)[0], 403)

    def test_acesso_negado_fica_na_auditoria(self):
        self.chamar("/api/analise", self.login("enfermeiro", "enf123"))
        eventos = self.chamar("/api/auditoria", self.login("gestor", "ges123"))[1]["eventos"]
        self.assertTrue(any(e["acao"] == "acesso_negado" for e in eventos))

    def test_logout_invalida_token(self):
        t = self.login("medico", "med123")
        self.chamar("/api/logout", t, corpo={})
        self.assertEqual(self.chamar("/api/eu", t)[0], 401)

    def test_pagina_inicial_e_servida(self):
        with urllib.request.urlopen(self.base + "/") as r:
            self.assertIn("Ponte Saúde", r.read().decode("utf-8"))

    def test_nao_permite_ler_arquivos_fora_da_pasta_web(self):
        req = urllib.request.Request(self.base + "/..%2Fdados%2Fusuarios.json")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
