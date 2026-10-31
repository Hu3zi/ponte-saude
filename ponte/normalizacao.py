"""
Funções de normalização.

Cada sistema guarda os dados de um jeito (CPF com ou sem pontos, datas em formatos
diferentes, nomes em MAIÚSCULAS ou sem acento). Antes de comparar pacientes entre
sistemas é preciso colocar tudo no mesmo padrão. Este módulo faz isso.
"""
import re
import unicodedata
from datetime import date, datetime


def normalizar_texto(texto):
    """Minúsculas, sem acentos e sem espaços repetidos. Ex.: 'JOÃO  da Silva' -> 'joao da silva'."""
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def formatar_nome(texto):
    """Nome em formato de título, mantendo 'da', 'de', 'dos'... em minúsculas."""
    minusculas = {"da", "de", "do", "das", "dos", "e"}
    partes = re.sub(r"\s+", " ", str(texto or "")).strip().lower().split(" ")
    saida = []
    for i, p in enumerate(partes):
        saida.append(p if (p in minusculas and i > 0) else p.capitalize())
    return " ".join(saida)


def so_digitos(texto):
    return re.sub(r"\D", "", str(texto or ""))


def cpf_valido(cpf):
    """Confere os dígitos verificadores do CPF (algoritmo oficial)."""
    d = so_digitos(cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(d[tamanho]):
            return False
    return True


def normalizar_cpf(cpf):
    """Retorna só os 11 dígitos, ou None se o CPF estiver ausente/inválido."""
    d = so_digitos(cpf)
    return d if cpf_valido(d) else None


def formatar_cpf(cpf):
    d = so_digitos(cpf)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else ""


def mascarar_cpf(cpf):
    """Mascara o CPF para exibição (LGPD - minimização): ***.456.789-**"""
    d = so_digitos(cpf)
    return f"***.{d[3:6]}.{d[6:9]}-**" if len(d) == 11 else "não informado"


def mascarar_cns(cns):
    d = so_digitos(cns)
    return f"{'*' * 11}{d[-4:]}" if len(d) >= 4 else "não informado"


def normalizar_data(texto):
    """Aceita 'dd/mm/aaaa' ou 'aaaa-mm-dd' e devolve 'aaaa-mm-dd' (ou None)."""
    if not texto:
        return None
    texto = str(texto).strip()[:10]
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    return None


def idade(nascimento_iso, hoje=None):
    try:
        nasc = date.fromisoformat(nascimento_iso)
    except (TypeError, ValueError):
        return None
    hoje = hoje or date.today()
    return hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))
