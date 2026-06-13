# -*- coding: utf-8 -*-
"""
engenheiro_dados.py — Agente: Engenheiro de Dados (text-to-SQL agêntico).

Gera (ou CORRIGE) o SQL de um passo do plano. É o dono do loop de correção
sintática: quando o Guardrail reprova ou o SQLite erra, o motivo volta aqui
('sua última consulta falhou com: ...') e a próxima geração corrige. Quando o
Auditor devolve, a instrução semântica entra no prompt da regeneração.
"""
from app.config import criar_llm
from app.estado import SqlDoPasso


def _prompt_do_engenheiro(
    objetivo_do_passo: str,
    pergunta_original: str,
    dossie: str,
    resultados_anteriores: list,
    erro_para_corrigir: str | None,
    instrucao_do_auditor: str | None,
) -> str:
    bloco_anteriores = ""
    if resultados_anteriores:
        blocos = []
        for indice, resultado in enumerate(resultados_anteriores, start=1):
            blocos.append(
                f"Passo {indice} ({resultado['objetivo']}): "
                f"colunas {resultado['colunas']}, "
                f"{resultado['n_linhas']} linha(s) no total "
                f"(exibindo até 10): {resultado['linhas'][:10]}"
            )
        bloco_anteriores = (
            "\nRESULTADOS DE PASSOS ANTERIORES (use-os se este passo depender "
            "deles):\n" + "\n".join(blocos) + "\n"
        )

    bloco_erro = ""
    if erro_para_corrigir:
        bloco_erro = (
            "\nATENÇÃO — sua última consulta FALHOU com o erro abaixo. "
            "Corrija a causa exata antes de propor de novo:\n"
            f"ERRO: {erro_para_corrigir}\n"
        )

    bloco_auditor = ""
    if instrucao_do_auditor:
        bloco_auditor = (
            "\nATENÇÃO — o Auditor de Dados reprovou a versão anterior e "
            "instruiu a correção abaixo. Siga a instrução:\n"
            f"INSTRUÇÃO DO AUDITOR: {instrucao_do_auditor}\n"
        )

    return (
        "Você é um Engenheiro de Dados. Escreva UMA consulta SQL (SQLite) que "
        "cumpra o OBJETIVO DO PASSO abaixo, dentro do contexto da pergunta "
        "original do diretor.\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1. Apenas UM statement SELECT (WITH...SELECT permitido). Nada de "
        "INSERT/UPDATE/DELETE/DDL/PRAGMA.\n"
        "2. Datas relativas ancoram na ÂNCORA TEMPORAL do dossiê, nunca na "
        "data de hoje.\n"
        "3. Use os valores EXATOS do dicionário de VALORES CATEGÓRICOS "
        "(grafia e capitalização idênticas, e da TABELA certa).\n"
        "4. Respeite os ALERTAS DE QUALIDADE: prefira a fonte transacional "
        "indicada neles.\n"
        f"{bloco_erro}{bloco_auditor}{bloco_anteriores}\n"
        f"{dossie}\n\n"
        f"PERGUNTA ORIGINAL DO DIRETOR: {pergunta_original}\n"
        f"OBJETIVO DO PASSO: {objetivo_do_passo}"
    )


def gerar_sql(
    objetivo_do_passo: str,
    pergunta_original: str,
    dossie: str,
    resultados_anteriores: list | None = None,
    erro_para_corrigir: str | None = None,
    instrucao_do_auditor: str | None = None,
    llm=None,
) -> SqlDoPasso:
    """Gera ou corrige o SQL de um passo (erro/instrução entram no prompt)."""
    if llm is None:
        llm = criar_llm()
    estruturado = llm.with_structured_output(SqlDoPasso)
    return estruturado.invoke(
        _prompt_do_engenheiro(
            objetivo_do_passo,
            pergunta_original,
            dossie,
            resultados_anteriores or [],
            erro_para_corrigir,
            instrucao_do_auditor,
        )
    )
