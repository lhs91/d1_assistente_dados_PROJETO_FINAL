# -*- coding: utf-8 -*-
"""Testes da decisão pura de renderização (Marco 4, microatividade 3)."""
import pytest

from app.estado import EspecificacaoVisual
from app.visualizacao.render_streamlit import decidir_renderizacao

pytestmark = pytest.mark.marco4


def _espec(**campos):
    base = dict(modo="agente", tipo="tabela", option=None,
                valor_metrica=None, rotulo_metrica=None,
                colunas=None, linhas=None, justificativa="j")
    base.update(campos)
    return EspecificacaoVisual(**base)


def test_option_vira_echarts():
    """Espec com option validado → veredito 'echarts' com o dict intacto."""
    option = {"series": [{"type": "bar", "data": [1, 2]}]}
    veredito = decidir_renderizacao(_espec(tipo="barra", option=option))
    assert veredito["tipo"] == "echarts"
    assert veredito["option"] is option
    assert veredito["aviso"] is None


def test_metrica_vira_metric():
    """Tipo 'metrica' → veredito com valor e rótulo para o st.metric."""
    veredito = decidir_renderizacao(
        _espec(tipo="metrica", valor_metrica="17", rotulo_metrica="clientes")
    )
    assert veredito == {"tipo": "metrica", "valor": "17",
                        "rotulo": "clientes", "aviso": None}


def test_tabela_e_fallback():
    """Tipo 'tabela' → colunas/linhas; fallback carrega o aviso com o motivo."""
    veredito = decidir_renderizacao(_espec(
        colunas=["a"], linhas=[(1,)],
        fallback_usado=True, motivo_fallback="option reprovado",
    ))
    assert veredito["tipo"] == "tabela"
    assert veredito["colunas"] == ["a"] and veredito["linhas"] == [(1,)]
    assert "option reprovado" in veredito["aviso"]


def test_espec_ausente_vira_nada():
    """Espec None (falha graciosa) → 'nada', sem exceção."""
    assert decidir_renderizacao(None) == {"tipo": "nada", "aviso": None}
