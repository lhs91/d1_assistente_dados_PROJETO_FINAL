# -*- coding: utf-8 -*-
"""
gerador_sql_poc.py — POC do gerador de SQL (Marco 1).

Uma única chamada ao Gemini: pergunta + dossiê do Perfilador → SqlGerado
(structured output via Pydantic). No Marco 2, este gerador evolui para o
agente Engenheiro de Dados (com loop de correção sintática).

O parâmetro `llm` é injetável de propósito: os testes determinísticos passam
um mock; a execução real usa config.criar_llm().
"""
from pydantic import BaseModel, Field

from app.config import criar_llm


class SqlGerado(BaseModel):
    """Saída estruturada do gerador (contrato com o LLM)."""
    sql: str = Field(description="A consulta SQL (apenas UM SELECT).")
    justificativa: str = Field(
        description="Por que esta consulta responde a pergunta (1-3 frases)."
    )


def _montar_prompt(pergunta: str, dossie: str) -> str:
    """Dossiê completo + regras fixas do gerador."""
    return (
        "Você é um engenheiro de dados. Escreva UMA consulta SQL (SQLite) que "
        "responda a pergunta do usuário, usando exclusivamente o banco descrito "
        "no dossiê abaixo.\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1. Apenas UM statement SELECT (CTE WITH...SELECT é permitido). "
        "Nada de INSERT/UPDATE/DELETE/DDL/PRAGMA.\n"
        "2. Datas relativas ('último ano', 'mês passado') ancoram na ÂNCORA "
        "TEMPORAL do dossiê, nunca na data de hoje.\n"
        "3. Use os valores EXATOS do dicionário de VALORES CATEGÓRICOS nos "
        "filtros (grafia e capitalização idênticas).\n"
        "4. Respeite os ALERTAS DE QUALIDADE: prefira a fonte transacional "
        "indicada neles.\n\n"
        f"{dossie}\n\n"
        f"PERGUNTA DO USUÁRIO: {pergunta}"
    )


def gerar_sql(pergunta: str, dossie: str, llm=None) -> SqlGerado:
    """Gera o SQL candidato. Se llm=None, usa a fábrica central (Gemini)."""
    if llm is None:
        llm = criar_llm()
    estruturado = llm.with_structured_output(SqlGerado)
    return estruturado.invoke(_montar_prompt(pergunta, dossie))
