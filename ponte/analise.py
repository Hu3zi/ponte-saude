"""
Análise de dados: mede os problemas encontrados ao cruzar e-SUS e Tasy e gera os
relatórios (JSON, Markdown e CSV) usados como evidência no relatório final.
"""
import csv
import json
import os
from datetime import datetime

from .unificacao import ESUS, TASY

ROTULOS = {
    "medicamento_alergia": "Medicamento em uso x alergia registrada",
    "alergia_unica_fonte": "Alergia registrada em apenas um sistema",
    "nascimento_divergente": "Data de nascimento divergente",
    "nome_divergente": "Nome escrito de formas diferentes",
    "cadastro_duplicado": "Cadastro duplicado no mesmo sistema",
    "cpf_ausente": "CPF ausente ou inválido",
}

CAUSAS = {
    "medicamento_alergia": "Cada sistema guarda a alergia e a prescrição em módulos separados; sem integração, ninguém cruza as duas informações.",
    "alergia_unica_fonte": "A alergia foi informada em um atendimento (UBS ou hospital) e não foi replicada ao outro sistema.",
    "nascimento_divergente": "Digitação manual na entrada de dados, sem validação cruzada com outras bases.",
    "nome_divergente": "Abreviações, sobrenomes omitidos e uso de maiúsculas/acentos diferentes entre os sistemas.",
    "cadastro_duplicado": "Novo cadastro criado por não encontrar o paciente na busca (ou busca feita só por nome).",
    "cpf_ausente": "Campo não obrigatório na recepção; paciente atendido sem documento.",
}

OPORTUNIDADES = [
    "Tornar CPF/CNS obrigatório e validar os dígitos verificadores na entrada do cadastro.",
    "Consultar o prontuário unificado antes de criar um novo cadastro (evita duplicidades).",
    "Padronizar o campo de alergias (lista controlada em vez de texto livre).",
    "Alertar o prescritor quando um medicamento conflitar com alergia registrada em qualquer sistema.",
    "Adotar o padrão HL7 FHIR como formato de troca de dados entre os sistemas.",
]


def analisar(pacientes, registros):
    esus = [r for r in registros if r["fonte"] == ESUS]
    tasy = [r for r in registros if r["fonte"] == TASY]
    em_ambos = [p for p in pacientes if len(p["fontes"]) == 2]
    por_tipo = {t: 0 for t in ROTULOS}
    for p in pacientes:
        for tipo in {a["tipo"] for a in p["alertas"]}:
            por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
    com_alerta = [p for p in pacientes if p["alertas"]]
    return {
        "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "registros_esus": len(esus),
        "registros_tasy": len(tasy),
        "registros_total": len(registros),
        "pacientes_unificados": len(pacientes),
        "registros_redundantes_eliminados": len(registros) - len(pacientes),
        "pacientes_so_esus": sum(1 for p in pacientes if p["fontes"] == [ESUS]),
        "pacientes_so_tasy": sum(1 for p in pacientes if p["fontes"] == [TASY]),
        "pacientes_em_ambos": len(em_ambos),
        "pacientes_com_alerta": len(com_alerta),
        "percentual_ambos_com_alerta": round(100 * sum(1 for p in em_ambos if p["alertas"]) / len(em_ambos), 1) if em_ambos else 0,
        "registros_sem_cpf_valido_esus": sum(1 for r in esus if not r["cpf"]),
        "registros_sem_cpf_valido_tasy": sum(1 for r in tasy if not r["cpf"]),
        "alertas_por_tipo": [{"tipo": t, "rotulo": ROTULOS[t], "pacientes": n, "causa": CAUSAS[t]}
                             for t, n in sorted(por_tipo.items(), key=lambda x: -x[1])],
        "oportunidades": OPORTUNIDADES,
    }


def cenario_antes_depois(pacientes, registros):
    """Compara o que o profissional enxerga SEM e COM o Ponte Saúde para um caso de risco."""
    por_id = {r["id_origem"]: r for r in registros}
    alvo = next((p for p in pacientes if any(a["tipo"] == "medicamento_alergia" for a in p["alertas"])), None)
    if not alvo:
        return None
    tasy = next(por_id[i] for i in alvo["ids_origem"] if i.startswith(TASY))
    esus = next(por_id[i] for i in alvo["ids_origem"] if i.startswith(ESUS))
    return {"paciente": alvo, "tasy": tasy, "esus": esus}


def _md(analise, cenario):
    a = analise
    linhas = [
        "# Relatório de análise de dados - Ponte Saúde", "",
        f"Gerado em {a['gerado_em']}. Todos os dados são fictícios.", "",
        "## Resumo", "",
        "| Indicador | Valor |", "|---|---|",
        f"| Registros no e-SUS | {a['registros_esus']} |",
        f"| Registros no Tasy | {a['registros_tasy']} |",
        f"| Total de registros nos dois sistemas | {a['registros_total']} |",
        f"| Pacientes únicos após a unificação | {a['pacientes_unificados']} |",
        f"| Registros redundantes eliminados | {a['registros_redundantes_eliminados']} |",
        f"| Pacientes presentes só no e-SUS | {a['pacientes_so_esus']} |",
        f"| Pacientes presentes só no Tasy | {a['pacientes_so_tasy']} |",
        f"| Pacientes presentes nos dois sistemas | {a['pacientes_em_ambos']} |",
        f"| Pacientes com pelo menos um alerta | {a['pacientes_com_alerta']} |",
        f"| % dos pacientes nos dois sistemas com alerta | {a['percentual_ambos_com_alerta']}% |",
        f"| Registros sem CPF válido (e-SUS / Tasy) | {a['registros_sem_cpf_valido_esus']} / {a['registros_sem_cpf_valido_tasy']} |",
        "", "## Inconsistências encontradas e causas prováveis", "",
        "| Inconsistência | Pacientes | Causa provável |", "|---|---|---|",
    ]
    for x in a["alertas_por_tipo"]:
        linhas.append(f"| {x['rotulo']} | {x['pacientes']} | {x['causa']} |")
    linhas += ["", "## Oportunidades de melhoria", ""] + [f"- {o}" for o in a["oportunidades"]]
    if cenario:
        p, t, e = cenario["paciente"], cenario["tasy"], cenario["esus"]
        meds = ", ".join(m["nome"] for m in t["medicamentos"]) or "nenhum"
        linhas += [
            "", "## Cenário simulado: antes e depois do Ponte Saúde", "",
            f"Paciente fictício: **{p['nome']}** ({p['id']}), atendido na UBS (e-SUS) e no hospital (Tasy).", "",
            f"- **Antes:** o médico do hospital abre o Tasy e vê alergias: "
            f"{', '.join(t['alergias']) or 'nenhuma registrada'}; medicamentos: {meds}. "
            f"A alergia registrada na UBS ({', '.join(e['alergias'])}) não aparece.",
            "- **Depois:** o prontuário unificado do Ponte Saúde exibe o alerta crítico: "
            + "; ".join(x["mensagem"] for x in p["alertas"] if x["gravidade"] == "critica"),
        ]
    return "\n".join(linhas) + "\n"


def gerar_relatorios(pasta_relatorio, pacientes, registros):
    os.makedirs(pasta_relatorio, exist_ok=True)
    analise = analisar(pacientes, registros)
    cenario = cenario_antes_depois(pacientes, registros)
    with open(os.path.join(pasta_relatorio, "analise.json"), "w", encoding="utf-8") as f:
        json.dump(analise, f, ensure_ascii=False, indent=2)
    with open(os.path.join(pasta_relatorio, "analise_inconsistencias.md"), "w", encoding="utf-8") as f:
        f.write(_md(analise, cenario))
    with open(os.path.join(pasta_relatorio, "alertas_por_paciente.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["id", "paciente", "sistemas", "gravidade", "tipo", "mensagem"])
        for p in pacientes:
            for al in p["alertas"]:
                w.writerow([p["id"], p["nome"], " + ".join(p["fontes"]), al["gravidade"], ROTULOS[al["tipo"]], al["mensagem"]])
    return analise
