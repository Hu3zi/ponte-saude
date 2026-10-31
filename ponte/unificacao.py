"""
Coração do Ponte Saúde: lê os dados dos dois sistemas, traduz cada um para um
formato comum ("esquema canônico"), descobre quais registros são da mesma pessoa
e monta UM prontuário unificado por paciente, com alertas de inconsistência.

Passos:
  1. carregar_*        -> lê o JSON de cada sistema e converte para o formato comum
  2. agrupar           -> decide quais registros pertencem à mesma pessoa
                          (primeiro por CPF; se faltar CPF, por nome + data de nascimento)
  3. montar_paciente   -> mescla os registros do grupo e gera os alertas
"""
import json
import os
import re

from .normalizacao import (formatar_nome, normalizar_cpf, normalizar_data,
                           normalizar_texto)

ESUS = "e-SUS"
TASY = "Tasy"


# --------------------------------------------------------------------------- 1. leitura
def _ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def _registro_base(fonte, indice, nome, cpf, nascimento, municipio, sexo, cns=None):
    return {
        "fonte": fonte,
        "id_origem": f"{fonte}-{indice:03d}",
        "nome": formatar_nome(nome),
        "nome_norm": normalizar_texto(nome),
        "cpf": normalizar_cpf(cpf),
        "cpf_informado": bool(str(cpf or "").strip()),
        "nascimento": normalizar_data(nascimento),
        "municipio": municipio,
        "sexo": sexo,
        "cns": cns,
        "alergias": [], "medicamentos": [], "condicoes": [], "vacinas": [], "atendimentos": [],
    }


def carregar_esus(pasta):
    """Traduz o formato do e-SUS (nomes de campos em português, datas dd/mm/aaaa)."""
    registros = []
    for i, c in enumerate(_ler(os.path.join(pasta, "esus.json"))["cidadaos"], start=1):
        r = _registro_base(ESUS, i, c["nome"], c.get("cpf"), c.get("data_nascimento"),
                           c.get("municipio"), c.get("sexo"), c.get("cns"))
        r["alergias"] = [a for a in c.get("alergias", []) if a]
        r["medicamentos"] = [{"nome": m["nome"], "dose": m.get("dose", "")} for m in c.get("medicamentos_uso", [])]
        r["condicoes"] = [{"cid": x["cid"], "descricao": x["descricao"]} for x in c.get("condicoes", [])]
        r["vacinas"] = [{"nome": v["nome"], "data": normalizar_data(v["data"])} for v in c.get("vacinas", [])]
        r["atendimentos"] = [{"data": normalizar_data(a["data"]), "unidade": a["unidade"],
                              "tipo": a["tipo"], "profissional": a["profissional"]}
                             for a in c.get("atendimentos", [])]
        registros.append(r)
    return registros


def carregar_tasy(pasta):
    """Traduz o formato do Tasy (campos nr_/nm_/ds_, datas aaaa-mm-dd, alergias em texto único)."""
    registros = []
    for i, p in enumerate(_ler(os.path.join(pasta, "tasy.json"))["pacientes"], start=1):
        r = _registro_base(TASY, i, p["nm_pessoa_fisica"], p.get("nr_cpf"), p.get("dt_nascimento"),
                           p.get("ds_municipio"), p.get("ie_sexo"))
        r["alergias"] = [a.strip() for a in re.split(r"[;,]", p.get("ds_alergias", "")) if a.strip()]
        r["medicamentos"] = [{"nome": m["ds_medicamento"], "dose": m.get("ds_dose", "")}
                             for m in p.get("medicacoes", [])]
        r["condicoes"] = [{"cid": d["cd_cid"], "descricao": d["ds_diagnostico"]} for d in p.get("diagnosticos", [])]
        r["vacinas"] = [{"nome": v["ds_vacina"], "data": normalizar_data(v["dt_aplicacao"])}
                        for v in p.get("vacinas", [])]
        r["atendimentos"] = [{"data": normalizar_data(a["dt_atendimento"]), "unidade": a["ds_unidade"],
                              "tipo": a["ds_tipo"], "profissional": a["nm_profissional"]}
                             for a in p.get("atendimentos", [])]
        registros.append(r)
    return registros


# --------------------------------------------------------------------------- 2. agrupamento
def agrupar(registros):
    """
    Une registros da mesma pessoa usando 'union-find'.
      Regra 1: mesmo CPF válido            -> mesma pessoa
      Regra 2: mesmo nome + mesma data de nascimento, desde que os CPFs não
               se contradigam (protege contra homônimos)
    """
    pai = list(range(len(registros)))

    def raiz(x):
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    def unir(a, b):
        pai[raiz(a)] = raiz(b)

    por_cpf, por_nome_nasc = {}, {}
    for i, r in enumerate(registros):
        if r["cpf"]:
            por_cpf.setdefault(r["cpf"], []).append(i)
        if r["nome_norm"] and r["nascimento"]:
            por_nome_nasc.setdefault((r["nome_norm"], r["nascimento"]), []).append(i)

    for indices in por_cpf.values():
        for j in indices[1:]:
            unir(indices[0], j)

    for indices in por_nome_nasc.values():
        for a in indices:
            for b in indices:
                if a < b and (not registros[a]["cpf"] or not registros[b]["cpf"]
                              or registros[a]["cpf"] == registros[b]["cpf"]):
                    unir(a, b)

    grupos = {}
    for i in range(len(registros)):
        grupos.setdefault(raiz(i), []).append(registros[i])
    return list(grupos.values())


# --------------------------------------------------------------------------- 3. mesclagem
def _tokens(nome_norm):
    return {t for t in nome_norm.split() if t not in {"da", "de", "do", "das", "dos", "e"} and len(t) > 1}


def _fontes_ordenadas(fontes):
    return sorted(fontes, key=lambda f: (f != ESUS, f))


def _mesclar_lista(grupo, campo, chave):
    """Junta itens iguais vindos de sistemas diferentes e lembra de quais sistemas vieram."""
    itens = {}
    for r in grupo:
        for item in r[campo]:
            k = chave(item)
            if not k:
                continue
            if k not in itens:
                itens[k] = {"item": item, "fontes": set()}
            itens[k]["fontes"].add(r["fonte"])
    return itens


def montar_paciente(grupo):
    fontes = {r["fonte"] for r in grupo}
    nomes_norm = {r["nome_norm"] for r in grupo}
    nascs = {r["nascimento"] for r in grupo if r["nascimento"]}
    cpfs = {r["cpf"] for r in grupo if r["cpf"]}
    alertas = []

    # nome canônico: o mais completo (mais letras)
    melhor = max(grupo, key=lambda r: len(r["nome_norm"]))

    # --- alergias
    alergias = []
    for k, v in sorted(_mesclar_lista(grupo, "alergias", normalizar_texto).items()):
        alergias.append({"nome": v["item"].strip().capitalize() if v["item"].islower() else v["item"],
                         "fontes": _fontes_ordenadas(v["fontes"])})
        if len(fontes) > 1 and len(v["fontes"]) == 1:
            so = list(v["fontes"])[0]
            alertas.append({"tipo": "alergia_unica_fonte", "gravidade": "alta",
                            "mensagem": f"Alergia a {alergias[-1]['nome']} registrada somente no {so}."})

    # --- medicamentos (a mesma droga em dois sistemas vira um item só)
    medicamentos = []
    for k, v in sorted(_mesclar_lista(grupo, "medicamentos", lambda m: normalizar_texto(m["nome"])).items()):
        medicamentos.append({"nome": v["item"]["nome"], "dose": v["item"]["dose"],
                             "fontes": _fontes_ordenadas(v["fontes"])})

    # --- interação: medicamento em uso que consta como alergia
    alergias_norm = {normalizar_texto(a["nome"]) for a in alergias}
    for m in medicamentos:
        if normalizar_texto(m["nome"]) in alergias_norm:
            alertas.insert(0, {"tipo": "medicamento_alergia", "gravidade": "critica",
                               "mensagem": f"{m['nome']} está em uso, mas o paciente tem alergia registrada a {m['nome']}."})

    condicoes = [{"cid": v["item"]["cid"], "descricao": v["item"]["descricao"], "fontes": _fontes_ordenadas(v["fontes"])}
                 for _, v in sorted(_mesclar_lista(grupo, "condicoes", lambda c: c["cid"]).items())]
    vacinas = [{"nome": v["item"]["nome"], "data": v["item"]["data"], "fontes": _fontes_ordenadas(v["fontes"])}
               for _, v in sorted(_mesclar_lista(grupo, "vacinas",
                                                 lambda x: f"{normalizar_texto(x['nome'])}|{x['data']}").items(),
                                  key=lambda kv: kv[1]["item"]["data"] or "", reverse=True)]
    atendimentos = []
    vistos = set()
    for r in grupo:
        for a in r["atendimentos"]:
            chave = (a["data"], a["unidade"], a["tipo"])
            if chave in vistos:
                continue
            vistos.add(chave)
            atendimentos.append({**a, "fonte": r["fonte"]})
    atendimentos.sort(key=lambda a: a["data"] or "", reverse=True)

    # --- demais alertas de qualidade de dados
    if len(nascs) > 1:
        alertas.append({"tipo": "nascimento_divergente", "gravidade": "media",
                        "mensagem": "Data de nascimento diferente entre os sistemas: "
                                    + " x ".join(sorted(nascs)) + "."})
    if len(nomes_norm) > 1 and len({frozenset(_tokens(n)) for n in nomes_norm}) > 1:
        alertas.append({"tipo": "nome_divergente", "gravidade": "media",
                        "mensagem": "Nome escrito de formas diferentes: "
                                    + "; ".join(sorted({formatar_nome(r['nome']) for r in grupo})) + "."})
    contagem = {}
    for r in grupo:
        contagem[r["fonte"]] = contagem.get(r["fonte"], 0) + 1
    for f, n in contagem.items():
        if n > 1:
            alertas.append({"tipo": "cadastro_duplicado", "gravidade": "baixa",
                            "mensagem": f"{n} cadastros do mesmo paciente no {f}."})
    if any(not r["cpf"] for r in grupo):
        faltando = sorted({r["fonte"] for r in grupo if not r["cpf"]})
        alertas.append({"tipo": "cpf_ausente", "gravidade": "baixa",
                        "mensagem": f"CPF ausente ou inválido no {', '.join(faltando)}; vínculo feito por nome e data de nascimento."})

    municipios = sorted({r["municipio"] for r in grupo if r["municipio"]})
    cns = next((r["cns"] for r in grupo if r["cns"]), None)
    return {
        "nome": formatar_nome(melhor["nome"]),
        "cpf": next(iter(cpfs), None),
        "cns": cns,
        "nascimento": sorted(nascs)[0] if nascs else None,
        "sexo": melhor["sexo"],
        "municipio": municipios[0] if municipios else None,
        "fontes": _fontes_ordenadas(fontes),
        "ids_origem": [r["id_origem"] for r in grupo],
        "alergias": alergias, "medicamentos": medicamentos, "condicoes": condicoes,
        "vacinas": vacinas, "atendimentos": atendimentos,
        "alertas": alertas,
    }


def unificar(pasta):
    """Pipeline completo. Devolve (lista_de_pacientes_unificados, registros_originais)."""
    registros = carregar_esus(pasta) + carregar_tasy(pasta)
    pacientes = [montar_paciente(g) for g in agrupar(registros)]
    pacientes.sort(key=lambda p: normalizar_texto(p["nome"]))
    for i, p in enumerate(pacientes, start=1):
        p["id"] = f"PS-{i:04d}"
    return pacientes, registros
