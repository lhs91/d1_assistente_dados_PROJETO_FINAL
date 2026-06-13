# -*- coding: utf-8 -*-
"""Testes do Engenheiro de Dados (Marco 2, microatividade 4). Gemini mockado."""
import pytest

from app.agentes.analista_negocios import analisar, redigir_resposta
from app.agentes.auditor_dados import auditar
from app.agentes.engenheiro_dados import gerar_sql
from app.estado import (
    AnaliseDaPergunta,
    ParecerDoAuditor,
    PassoDoPlano,
    RespostaDeNegocio,
    SqlDoPasso,
)
from testes.llm_falso import LlmRoteirizado

pytestmark = pytest.mark.marco2

DOSSIE = (
    "=== DOSSIÊ === ÂNCORA TEMPORAL: os dados terminam em 2025-07-22. "
    "ALERTAS DE QUALIDADE: prefira a fonte transacional."
)

RESULTADO_EXEMPLO = {
    "objetivo": "contar reclamações",
    "sql": "SELECT canal, COUNT(*) FROM suporte GROUP BY canal",
    "justificativa": "agrupa por canal",
    "colunas": ["canal", "total"],
    "linhas": [("Chat", 18), ("E-mail", 14)],
    "n_linhas": 2,
    "truncado": False,
    "tentativas": 1,
}


# ── Engenheiro de Dados ──────────────────────────────────────────────────────

def test_gerar_sql_estruturado():
    """A saída do Engenheiro vira SqlDoPasso (sql + justificativa)."""
    proposta = SqlDoPasso(sql="SELECT 1", justificativa="teste")
    llm = LlmRoteirizado({SqlDoPasso: [proposta]})
    saida = gerar_sql("objetivo", "pergunta", DOSSIE, llm=llm)
    assert isinstance(saida, SqlDoPasso)
    assert saida.sql == "SELECT 1"


def test_prompt_contem_erro_anterior():
    """Com erro_para_corrigir, o prompt avisa que a última consulta falhou."""
    llm = LlmRoteirizado({SqlDoPasso: [SqlDoPasso(sql="SELECT 1", justificativa="j")]})
    gerar_sql("objetivo", "pergunta", DOSSIE,
              erro_para_corrigir="no such column: colx", llm=llm)
    prompt = llm.prompts[0]
    assert "FALHOU" in prompt
    assert "no such column: colx" in prompt


def test_prompt_contem_instrucao_do_auditor():
    """Com devolução, a instrução do Auditor entra no prompt da regeneração."""
    llm = LlmRoteirizado({SqlDoPasso: [SqlDoPasso(sql="SELECT 1", justificativa="j")]})
    gerar_sql("objetivo", "pergunta", DOSSIE,
              instrucao_do_auditor="use a tabela compras, não a coluna do pai", llm=llm)
    prompt = llm.prompts[0]
    assert "Auditor de Dados" in prompt
    assert "use a tabela compras" in prompt


def test_prompt_contem_resultados_anteriores():
    """Multi-passo: resultados de passos prévios entram no contexto do prompt."""
    llm = LlmRoteirizado({SqlDoPasso: [SqlDoPasso(sql="SELECT 1", justificativa="j")]})
    gerar_sql("objetivo do passo 2", "pergunta", DOSSIE,
              resultados_anteriores=[RESULTADO_EXEMPLO], llm=llm)
    prompt = llm.prompts[0]
    assert "PASSOS ANTERIORES" in prompt
    assert "('Chat', 18)" in prompt




def test_prompt_sem_regra_de_teto_de_linhas():
    """V3.6 (truncamento REMOVIDO): a regra 0 do teto saiu — o executor
    devolve todas as linhas e o Engenheiro não precisa contornar nada."""
    from app.agentes.engenheiro_dados import _prompt_do_engenheiro
    prompt = _prompt_do_engenheiro(
        objetivo_do_passo="o", pergunta_original="p", dossie="d",
        resultados_anteriores=[], erro_para_corrigir=None,
        instrucao_do_auditor=None,
    )
    assert "TETO DE LINHAS" not in prompt


