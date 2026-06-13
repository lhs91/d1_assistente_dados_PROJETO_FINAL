# -*- coding: utf-8 -*-
"""Testes da configuração central (Marco 1, microatividade 1)."""
import pytest

from app import config
from app.config import ErroDeConfiguracao, carregar_chave_google

pytestmark = pytest.mark.marco1


def test_constantes_centrais_presentes():
    """Modelo, temperatura, limites e caminhos definidos e coerentes."""
    assert config.MODELO_AGENTES == "gemini-2.5-pro"
    assert config.TEMPERATURA == 0.0          # reprodutibilidade é requisito
    assert 0 < config.LIMIAR_DIVERGENCIA < 1
    assert config.LIMITE_CARDINALIDADE > 0
    assert config.LIMITE_AMOSTRAS > 0
    assert config.CAMINHO_BANCO_PADRAO.name == "anexo_desafio_1.db"
    assert config.PROJETO_LANGSMITH == "d1_franq"


def test_carregar_chave_do_ambiente(monkeypatch):
    """A chave é lida do ambiente quando presente."""
    monkeypatch.setenv("GOOGLE_API_KEY", "chave-de-teste-123")
    assert carregar_chave_google() == "chave-de-teste-123"


def test_ausencia_de_chave_gera_erro_claro(monkeypatch):
    """Sem chave: ErroDeConfiguracao com orientação ao dev — e os módulos
    determinísticos continuam importáveis/funcionais sem ela."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ErroDeConfiguracao) as excecao:
        carregar_chave_google()
    assert "GOOGLE_API_KEY" in str(excecao.value)
    assert ".env" in str(excecao.value)

    # Os componentes determinísticos não dependem da chave:
    from app import executor, guardrail_sql, perfilador  # noqa: F401  (importáveis)
