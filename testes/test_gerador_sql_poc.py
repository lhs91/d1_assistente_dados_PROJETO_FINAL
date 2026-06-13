# -*- coding: utf-8 -*-
"""Testes do POC gerador + motor headless (Marco 1, microatividade 7).

O Gemini é SEMPRE mockado aqui; Guardrail e Executor são os reais.
O teste de fogo com API real é executado por Vahelle via CLI.
"""
import pytest

from app.gerador_sql_poc import SqlGerado, _montar_prompt, gerar_sql
from app.principal import responder_pergunta_poc as responder_pergunta

pytestmark = pytest.mark.marco1


class _LlmFalso:
    """Mock mínimo do LLM: registra o prompt e devolve um SqlGerado fixo."""

    def __init__(self, sql: str, justificativa: str = "justificativa de teste"):
        self._saida = SqlGerado(sql=sql, justificativa=justificativa)
        self.prompt_recebido = None

    def with_structured_output(self, schema):
        assert schema is SqlGerado          # contrato estruturado respeitado
        return self

    def invoke(self, prompt: str):
        self.prompt_recebido = prompt
        return self._saida


def test_prompt_contem_dossie():
    """O prompt enviado ao LLM contém o dossiê e a pergunta — e as regras."""
    prompt = _montar_prompt("Quantos pedidos houve?", "DOSSIE-MARCADOR-XYZ")
    assert "DOSSIE-MARCADOR-XYZ" in prompt
    assert "Quantos pedidos houve?" in prompt
    assert "ÂNCORA TEMPORAL" in prompt      # regra da Sutileza 3
    assert "ALERTAS DE QUALIDADE" in prompt # regra da Armadilha 1

    llm = _LlmFalso(sql="SELECT 1")
    gerar_sql("Quantos pedidos houve?", "DOSSIE-MARCADOR-XYZ", llm=llm)
    assert "DOSSIE-MARCADOR-XYZ" in llm.prompt_recebido


def test_resposta_estruturada_parseada():
    """A saída do mock vira SqlGerado (sql + justificativa)."""
    llm = _LlmFalso(sql="SELECT COUNT(*) FROM pedidos", justificativa="conta tudo")
    gerado = gerar_sql("Quantos pedidos?", "dossiê", llm=llm)
    assert isinstance(gerado, SqlGerado)
    assert gerado.sql == "SELECT COUNT(*) FROM pedidos"
    assert gerado.justificativa == "conta tudo"


def test_fluxo_completo_com_mock(banco_sintetico, capsys):
    """SQL do mock atravessa Guardrail e Executor DE VERDADE e traz dados
    reais do banco sintético."""
    llm = _LlmFalso(sql="SELECT COUNT(*) AS total FROM pedidos")
    saida = responder_pergunta("Quantos pedidos?", banco_sintetico, llm=llm)

    assert saida["erro"] is None
    assert saida["aprovado_guardrail"] is True
    assert saida["resultado"].colunas == ["total"]
    assert saida["resultado"].linhas == [(20,)]         # os 20 do sintético

    logs = capsys.readouterr().out
    assert "[INFO]" in logs and "[ERRO]" not in logs    # padrão de logs


def test_sql_malicioso_do_mock_e_barrado(banco_sintetico, capsys):
    """Mock devolve DROP TABLE → Guardrail barra → [ERRO] gracioso, sem
    traceback e sem tocar no banco."""
    llm = _LlmFalso(sql="DROP TABLE pedidos")
    saida = responder_pergunta("Apague tudo", banco_sintetico, llm=llm)

    assert saida["aprovado_guardrail"] is False
    assert saida["resultado"] is None
    assert "Guardrail" in saida["erro"]

    logs = capsys.readouterr().out
    assert "[ERRO]" in logs

    # O banco continua intacto (consulta independente):
    import sqlite3
    con = sqlite3.connect(f"file:{banco_sintetico}?mode=ro", uri=True)
    assert con.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0] == 20
    con.close()
