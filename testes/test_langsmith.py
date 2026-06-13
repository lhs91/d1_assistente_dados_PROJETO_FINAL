# -*- coding: utf-8 -*-
"""Testes da configuração do LangSmith (correção do 'Waiting for traces')."""
import pytest

from app.config import PROJETO_LANGSMITH, configurar_langsmith

pytestmark = pytest.mark.marco3


def test_configurar_langsmith_seta_as_duas_geracoes(monkeypatch):
    """Com chave presente, seta LANGSMITH_* E LANGCHAIN_* (tracing + projeto d1_franq)."""
    for variavel in ["LANGSMITH_API_KEY", "LANGCHAIN_API_KEY", "LANGSMITH_TRACING",
                     "LANGCHAIN_TRACING_V2", "LANGSMITH_PROJECT", "LANGCHAIN_PROJECT"]:
        monkeypatch.delenv(variavel, raising=False)
    monkeypatch.setenv("LANGSMITH_API_KEY", "chave-teste")

    assert configurar_langsmith() is True
    import os
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    assert os.environ["LANGSMITH_PROJECT"] == PROJETO_LANGSMITH
    assert os.environ["LANGCHAIN_PROJECT"] == PROJETO_LANGSMITH
    assert os.environ["LANGCHAIN_API_KEY"] == "chave-teste"   # espelhada


def test_configurar_langsmith_sem_chave_nao_liga_nada(monkeypatch):
    """Sem chave: retorna False e NÃO seta variável de tracing alguma."""
    import os
    for variavel in ["LANGSMITH_API_KEY", "LANGCHAIN_API_KEY", "LANGSMITH_TRACING",
                     "LANGCHAIN_TRACING_V2"]:
        monkeypatch.delenv(variavel, raising=False)
    assert configurar_langsmith() is False
    assert "LANGSMITH_TRACING" not in os.environ
    assert "LANGCHAIN_TRACING_V2" not in os.environ
