# -*- coding: utf-8 -*-
"""
bateria.py — Roda as 5 perguntas do enunciado de uma vez só.

Uso: python -m app.bateria [--banco caminho/banco.db]

Cada pergunta passa pelo grafo completo (plano → SQL → guardrail → execução →
auditoria → redação) e imprime: resposta de negócio, premissas e o trace
técnico. Ao final, um quadro-resumo da bateria.

Robustez: uma pergunta que falhe (até por exceção inesperada) NÃO derruba a
bateria — o erro é registrado e a próxima pergunta roda normalmente.
O cache do Perfilador faz o dossiê ser calculado uma única vez para as 5.
"""
import argparse
from pathlib import Path

from app.config import CAMINHO_BANCO_PADRAO
from app.cores import banner, pintar_cabecalho, pintar_erro, pintar_premissa, pintar_resposta
from app.principal import _perguntar_no_terminal, responder_pergunta

PERGUNTAS_DO_ENUNCIADO = [
    "Liste os 5 estados com maior número de clientes que compraram via app em maio.",
    "Quantos clientes interagiram com campanhas de WhatsApp em 2024?",
    "Quais categorias de produto tiveram o maior número de compras em média por cliente?",
    "Qual o número de reclamações não resolvidas por canal?",
    "Qual a tendência de reclamações por canal no último ano?",
]


def executar_bateria(
    perguntas: list | None = None,
    caminho_banco: Path = CAMINHO_BANCO_PADRAO,
    llm=None,
    responder_interrupt=None,
    modo_visualizacao: str | None = None,
    gerar_previews: bool = False,
) -> list:
    """Executa as perguntas em sequência e devolve a lista de saídas.

    Cada saída é o dict de responder_pergunta; se uma pergunta estourar
    exceção inesperada, a saída vira {"pergunta", "erro_execucao"} e a
    bateria SEGUE para a próxima."""
    perguntas = perguntas if perguntas is not None else PERGUNTAS_DO_ENUNCIADO
    saidas = []
    for numero, pergunta in enumerate(perguntas, start=1):
        print("\n" + pintar_cabecalho("#" * 72))
        print(pintar_cabecalho(f"# PERGUNTA {numero}/{len(perguntas)}: {pergunta}"))
        print(pintar_cabecalho("#" * 72))
        print(banner("TRACE TÉCNICO — acompanhe o raciocínio dos agentes"))
        try:
            from app.config import MODO_VISUALIZACAO_PADRAO
            saida = responder_pergunta(
                pergunta,
                caminho_banco,
                llm=llm,
                responder_interrupt=responder_interrupt,
                modo_visualizacao=modo_visualizacao or MODO_VISUALIZACAO_PADRAO,
            )
        except Exception as excecao:  # noqa: BLE001 — robustez da bateria
            print(pintar_erro(f"[ERRO] Pergunta {numero} falhou com exceção: {excecao}"))
            saidas.append({"pergunta": pergunta, "erro_execucao": str(excecao)})
            continue
        saidas.append(saida)

        print("\n" + pintar_cabecalho("=" * 72))
        if saida["falha_graciosa"]:
            print(pintar_cabecalho("RESPOSTA (com ressalvas):"))
            print(saida["falha_graciosa"])
        else:
            print(pintar_cabecalho("RESPOSTA:"))
            print(pintar_resposta(saida["resposta"]))
            if saida["premissas"]:
                print("\nPremissas assumidas:")
                for premissa in saida["premissas"]:
                    print(pintar_premissa(f"  - {premissa}"))
        print(pintar_cabecalho("=" * 72))

        if gerar_previews and saida.get("especificacao_visual"):
            from app.visualizacao.preview_html import gerar_preview_html
            caminho = gerar_preview_html(
                saida["especificacao_visual"], pergunta, saida["resposta"],
                Path(f"preview_pergunta_{numero}.html"),
            )
            print(f"[INFO] Preview gravado em: {caminho}")
    return saidas


def _imprimir_resumo(saidas: list) -> None:
    """Quadro-resumo da bateria: status e custo (chamadas LLM) por pergunta."""
    print("\n" + pintar_cabecalho("#" * 72))
    print(pintar_cabecalho("# RESUMO DA BATERIA"))
    print(pintar_cabecalho("#" * 72))
    for numero, saida in enumerate(saidas, start=1):
        from app.cores import AMARELO, NORMAL, VERDE, VERMELHO
        if "erro_execucao" in saida:
            status = f"{VERMELHO}EXCEÇÃO: {saida['erro_execucao'][:60]}{NORMAL}"
            chamadas = "-"
        elif saida.get("falha_graciosa"):
            status = f"{AMARELO}FALHA GRACIOSA{NORMAL}"
            chamadas = saida.get("chamadas_llm", "-")
        else:
            status = f"{VERDE}OK{NORMAL}"
            chamadas = saida.get("chamadas_llm", "-")
        print(f"  {numero}. [{status}] ({chamadas} chamadas LLM) {saida['pergunta']}")


def principal() -> None:
    """Ponto de entrada do CLI da bateria."""
    parser = argparse.ArgumentParser(
        description="Bateria: as 5 perguntas do enunciado em uma execução."
    )
    parser.add_argument(
        "--banco",
        type=Path,
        default=CAMINHO_BANCO_PADRAO,
        help="Caminho do banco SQLite (padrão: data/anexo_desafio_1.db).",
    )
    parser.add_argument(
        "--modo", choices=["agente", "pre_setado"], default=None,
        help="Autor do visual (padrão: config.MODO_VISUALIZACAO_PADRAO).",
    )
    parser.add_argument(
        "--preview", action="store_true",
        help="Gera preview_pergunta_N.html para cada pergunta.",
    )
    argumentos = parser.parse_args()

    from app.config import ErroDeConfiguracao, configurar_langsmith
    from app.executor import ErroDeBanco
    if configurar_langsmith():
        print("[INFO] LangSmith ATIVO — traces no projeto 'd1_franq' "
              "(no painel: Projects > d1_franq).")
    else:
        print("[INFO] LangSmith inativo (LANGSMITH_API_KEY ausente no .env).")
    try:
        saidas = executar_bateria(
            caminho_banco=argumentos.banco,
            responder_interrupt=_perguntar_no_terminal,
            modo_visualizacao=argumentos.modo,
            gerar_previews=argumentos.preview,
        )
    except (ErroDeConfiguracao, ErroDeBanco) as excecao:
        print(f"[ERRO] {excecao}")
        return
    _imprimir_resumo(saidas)


if __name__ == "__main__":
    principal()
