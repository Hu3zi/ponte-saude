"""
Gera dados 100% FICTÍCIOS que simulam dois sistemas de saúde diferentes:

  * e-SUS (atenção básica / UBS)     -> dados/esus.json
  * Tasy  (hospital / especializada) -> dados/tasy.json

Os dois sistemas guardam o mesmo tipo de informação em formatos diferentes e com
problemas propositais (CPF formatado de outro jeito, nome diferente, alergia que
só aparece em um sistema, cadastro duplicado...). Esses problemas são exatamente
o que o Ponte Saúde precisa detectar e resolver.

Nenhum dado real é usado (LGPD). Os CPFs são gerados com dígitos verificadores
válidos apenas para que o algoritmo de validação possa ser testado.
"""
import hashlib
import json
import os
import random
import secrets
from datetime import date, timedelta

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")

NOMES_F = ["Maria", "Ana", "Juliana", "Fernanda", "Patrícia", "Camila", "Luciana", "Beatriz",
           "Aline", "Rosângela", "Tatiane", "Vera", "Marta", "Helena", "Simone", "Carla"]
NOMES_M = ["João", "José", "Carlos", "Pedro", "Lucas", "Marcos", "Rafael", "Paulo",
           "Antônio", "Gabriel", "Rodrigo", "Sérgio", "Eduardo", "Luís", "Fábio", "André"]
SOBRENOMES = ["Silva", "Santos", "Oliveira", "Souza", "Pereira", "Lima", "Ferreira", "Costa",
              "Rodrigues", "Almeida", "Nascimento", "Carvalho", "Gomes", "Martins", "Araújo",
              "Ribeiro", "Moreira", "Barbosa", "Cardoso", "Teixeira", "Machado", "Zanella"]
MUNICIPIOS = ["Porto Alegre", "Canoas", "Novo Hamburgo", "São Leopoldo", "Gravataí",
              "Esteio", "Cachoeirinha", "Viamão"]
UBS = ["UBS Vila Nova", "UBS Centro", "UBS Restinga", "UBS Santa Rosa", "UBS Cidade Baixa"]
HOSPITAIS = ["Hospital Municipal Esperança", "Hospital Regional Sul", "Pronto Atendimento 24h Centro"]
PROFISSIONAIS = ["Dra. Helena Duarte", "Dr. Marcelo Rocha", "Enf. Cláudia Prates",
                 "Dr. Ricardo Bastos", "Dra. Letícia Vargas", "Enf. Tiago Moura"]
ALERGIAS = ["Dipirona", "Penicilina", "Amoxicilina", "Ibuprofeno", "Látex", "Sulfa", "Frutos do mar"]
MEDICAMENTOS = [("Losartana", "50 mg"), ("Metformina", "850 mg"), ("Atenolol", "25 mg"),
                ("Omeprazol", "20 mg"), ("Sinvastatina", "20 mg"), ("Levotiroxina", "50 mcg"),
                ("Salbutamol", "100 mcg"), ("Enalapril", "10 mg"), ("Fluoxetina", "20 mg")]
CONDICOES = [("I10", "Hipertensão essencial"), ("E11", "Diabetes mellitus tipo 2"),
             ("J45", "Asma"), ("E03", "Hipotireoidismo"), ("F32", "Episódio depressivo"),
             ("E78", "Dislipidemia"), ("M54", "Dorsalgia")]
VACINAS = ["Influenza", "COVID-19", "Hepatite B", "Tétano (dT)", "Febre amarela", "Pneumocócica"]
TIPOS_ESUS = ["Consulta de rotina", "Renovação de receita", "Visita domiciliar", "Acompanhamento de crônicos"]
TIPOS_TASY = ["Pronto atendimento", "Internação", "Exame de imagem", "Consulta ambulatorial"]


def gerar_cpf(rnd):
    """CPF fictício com dígitos verificadores válidos."""
    n = [rnd.randint(0, 9) for _ in range(9)]
    for tamanho in (9, 10):
        soma = sum(n[i] * (tamanho + 1 - i) for i in range(tamanho))
        n.append((soma * 10) % 11 % 10)
    return "".join(map(str, n))


def fmt_cpf(d):
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def data_br(d):
    return d.strftime("%d/%m/%Y")


def hash_senha(senha, sal):
    return hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(sal), 120_000).hex()


def gerar_usuarios():
    """Usuários de demonstração. As senhas ficam guardadas como hash (PBKDF2), nunca em texto puro."""
    demo = [
        ("medico", "med123", "medico", "Dra. Helena Duarte"),
        ("enfermeiro", "enf123", "enfermeiro", "Enf. Tiago Moura"),
        ("recepcao", "rec123", "recepcao", "Bianca Lopes (Recepção)"),
        ("gestor", "ges123", "gestor", "Marcos Vieira (Gestão)"),
    ]
    usuarios = {}
    for login, senha, perfil, nome in demo:
        sal = secrets.token_hex(16)
        usuarios[login] = {"nome": nome, "perfil": perfil, "sal": sal, "hash": hash_senha(senha, sal)}
    return usuarios


def gerar(seed=2026, total=44):
    rnd = random.Random(seed)
    hoje = date(2026, 10, 30)
    esus, tasy = [], []
    cpfs_usados = set()

    def cpf_unico():
        while True:
            c = gerar_cpf(rnd)
            if c not in cpfs_usados:
                cpfs_usados.add(c)
                return c

    def atendimentos(tipos, unidades, n):
        saida = []
        for _ in range(n):
            d = hoje - timedelta(days=rnd.randint(5, 700))
            saida.append({"data": d, "unidade": rnd.choice(unidades), "tipo": rnd.choice(tipos),
                          "profissional": rnd.choice(PROFISSIONAIS)})
        return sorted(saida, key=lambda x: x["data"], reverse=True)

    for i in range(total):
        sexo = rnd.choice(["F", "M"])
        primeiro = rnd.choice(NOMES_F if sexo == "F" else NOMES_M)
        s1, s2 = rnd.sample(SOBRENOMES, 2)
        particula = ""
        if s1 in ("Silva", "Costa", "Rocha") and rnd.random() < 0.5:
            particula = "da "
        elif s1 in ("Souza", "Oliveira", "Almeida", "Carvalho", "Araújo") and rnd.random() < 0.5:
            particula = "de "
        nome = f"{primeiro} {particula}{s1} {s2}"
        nasc = date(1940, 1, 1) + timedelta(days=rnd.randint(0, 365 * 75))
        cpf = cpf_unico()
        cns = "7" + "".join(str(rnd.randint(0, 9)) for _ in range(14))
        municipio = rnd.choice(MUNICIPIOS)
        alergias = rnd.sample(ALERGIAS, rnd.choice([0, 0, 1, 1, 2]))
        meds = rnd.sample(MEDICAMENTOS, rnd.choice([0, 1, 2, 3]))
        conds = rnd.sample(CONDICOES, rnd.choice([0, 1, 1, 2]))
        vacs = [{"nome": v, "data": hoje - timedelta(days=rnd.randint(30, 900))}
                for v in rnd.sample(VACINAS, rnd.choice([1, 2, 3]))]

        # 0-13: só e-SUS | 14-21: só Tasy | 22+: nos dois sistemas
        so_esus = i < 14
        so_tasy = 14 <= i < 22
        ambos = i >= 22

        reg_esus = reg_tasy = None
        if so_esus or ambos:
            reg_esus = {
                "cns": cns, "cpf": fmt_cpf(cpf), "nome": nome.upper(), "sexo": sexo,
                "data_nascimento": data_br(nasc), "municipio": municipio,
                "alergias": list(alergias),
                "medicamentos_uso": [{"nome": m, "dose": d} for m, d in meds],
                "condicoes": [{"cid": c, "descricao": ds} for c, ds in conds],
                "vacinas": [{"nome": v["nome"], "data": data_br(v["data"])} for v in vacs],
                "atendimentos": [{**a, "data": data_br(a["data"])}
                                 for a in atendimentos(TIPOS_ESUS, UBS, rnd.randint(1, 3))],
            }
        if so_tasy or ambos:
            reg_tasy = {
                "nr_cpf": cpf, "nm_pessoa_fisica": nome, "ie_sexo": sexo,
                "dt_nascimento": nasc.isoformat(), "ds_municipio": municipio,
                "ds_alergias": "; ".join(alergias),
                "medicacoes": [{"ds_medicamento": m, "ds_dose": d} for m, d in meds],
                "diagnosticos": [{"cd_cid": c, "ds_diagnostico": ds} for c, ds in conds],
                "vacinas": [{"ds_vacina": v["nome"], "dt_aplicacao": v["data"].isoformat()} for v in vacs],
                "atendimentos": [{"dt_atendimento": a["data"].isoformat(), "ds_unidade": a["unidade"],
                                  "ds_tipo": a["tipo"], "nm_profissional": a["profissional"]}
                                 for a in atendimentos(TIPOS_TASY, HOSPITAIS, rnd.randint(1, 3))],
            }

        # ---------- problemas propositais (só para quem está nos dois sistemas) ----------
        if ambos:
            k = i - 22  # 0..21
            # nome escrito de forma diferente no Tasy (sobrenome faltando / abreviado)
            if k in (1, 5, 9, 14):
                reg_tasy["nm_pessoa_fisica"] = f"{primeiro} {s1[0]}. {s2}"
            if k in (3, 11):
                reg_tasy["nm_pessoa_fisica"] = f"{primeiro} {s2}"
            # data de nascimento digitada errada em um dos sistemas
            if k in (2, 12):
                errada = nasc.replace(day=min(nasc.day + 3, 28)) if nasc.day < 25 else nasc.replace(day=5)
                reg_tasy["dt_nascimento"] = errada.isoformat()
            # CPF ausente no Tasy -> unificação precisa usar nome + data de nascimento
            if k in (4, 8, 16):
                reg_tasy["nr_cpf"] = ""
                reg_tasy["nm_pessoa_fisica"] = nome  # nome completo para casar
            # alergia registrada só em um sistema (risco clínico!)
            if k in (0, 6, 7, 13, 17):
                nova = rnd.choice([a for a in ALERGIAS if a not in alergias])
                reg_esus["alergias"] = list(alergias) + [nova]
            if k in (10, 15):
                nova = rnd.choice([a for a in ALERGIAS if a not in alergias])
                reg_tasy["ds_alergias"] = "; ".join(list(alergias) + [nova])
            # medicamento prescrito no Tasy que conflita com alergia registrada no e-SUS
            if k in (18, 19):
                reg_esus["alergias"] = ["Dipirona"]
                reg_tasy["ds_alergias"] = ""
                reg_tasy["medicacoes"] = [{"ds_medicamento": "Dipirona", "ds_dose": "500 mg"}]
                reg_esus["medicamentos_uso"] = []
            # medicamento só em um sistema
            if k in (20, 21):
                if all(m["ds_medicamento"] != "Enalapril" for m in reg_tasy["medicacoes"]):
                    reg_tasy["medicacoes"] = reg_tasy["medicacoes"] + [{"ds_medicamento": "Enalapril", "ds_dose": "10 mg"}]

        if reg_esus:
            esus.append(reg_esus)
        if reg_tasy:
            tasy.append(reg_tasy)

    # ---------- cadastros duplicados dentro do mesmo sistema ----------
    for idx in (0, 5, 9):
        dup = json.loads(json.dumps(esus[idx]))
        dup["nome"] = dup["nome"].replace("  ", " ")
        dup["atendimentos"] = dup["atendimentos"][:1]
        esus.append(dup)
    for idx in (2, 6):
        dup = json.loads(json.dumps(tasy[idx]))
        dup["nr_cpf"] = fmt_cpf(dup["nr_cpf"]) if dup["nr_cpf"] else ""
        dup["atendimentos"] = dup["atendimentos"][:1]
        tasy.append(dup)

    rnd.shuffle(esus)
    rnd.shuffle(tasy)
    return {"cidadaos": esus}, {"pacientes": tasy}


def main():
    os.makedirs(PASTA, exist_ok=True)
    esus, tasy = gerar()
    with open(os.path.join(PASTA, "esus.json"), "w", encoding="utf-8") as f:
        json.dump(esus, f, ensure_ascii=False, indent=2)
    with open(os.path.join(PASTA, "tasy.json"), "w", encoding="utf-8") as f:
        json.dump(tasy, f, ensure_ascii=False, indent=2)
    with open(os.path.join(PASTA, "usuarios.json"), "w", encoding="utf-8") as f:
        json.dump(gerar_usuarios(), f, ensure_ascii=False, indent=2)
    print(f"Dados fictícios gerados em {PASTA}")
    print(f"  e-SUS: {len(esus['cidadaos'])} registros | Tasy: {len(tasy['pacientes'])} registros")


if __name__ == "__main__":
    main()
