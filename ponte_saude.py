"""
Ponte Saúde - ponto de entrada.

Uso:
    python ponte_saude.py              # prepara os dados (se preciso) e abre o sistema no navegador
    python ponte_saude.py preparar     # gera dados fictícios + relatórios de análise (pasta relatorio/)
    python ponte_saude.py testar       # roda os testes automatizados
    python ponte_saude.py servir --porta 8080
"""
import argparse
import os
import sys
import unittest

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)


def preparar():
    import gerar_dados
    from ponte.analise import gerar_relatorios
    from ponte.unificacao import unificar
    gerar_dados.main()
    pacientes, registros = unificar(os.path.join(RAIZ, "dados"))
    analise = gerar_relatorios(os.path.join(RAIZ, "relatorio"), pacientes, registros)
    print("\nAnálise concluída:")
    print(f"  {analise['registros_total']} registros nos dois sistemas -> {analise['pacientes_unificados']} pacientes únicos")
    print(f"  {analise['pacientes_com_alerta']} pacientes com alertas de inconsistência")
    print(f"  Relatórios salvos em: {os.path.join(RAIZ, 'relatorio')}")


def testar():
    suite = unittest.defaultTestLoader.discover(os.path.join(RAIZ, "tests"), top_level_dir=RAIZ)
    resultado = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if resultado.wasSuccessful() else 1)


def servir(porta):
    if not os.path.exists(os.path.join(RAIZ, "dados", "esus.json")):
        preparar()
    from ponte.servidor import iniciar
    iniciar(porta)


def main():
    ap = argparse.ArgumentParser(description="Ponte Saúde - prontuário unificado (PoC)")
    ap.add_argument("comando", nargs="?", default="servir", choices=["servir", "preparar", "testar"])
    ap.add_argument("--porta", type=int, default=8000)
    args = ap.parse_args()
    if args.comando == "preparar":
        preparar()
    elif args.comando == "testar":
        testar()
    else:
        servir(args.porta)


if __name__ == "__main__":
    main()
