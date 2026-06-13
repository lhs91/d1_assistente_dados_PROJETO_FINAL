# -*- coding: utf-8 -*-
"""Testes do classificador de forma do dado (Marco 3, microatividade 2)."""
import pytest

from app.config import MAX_CATEGORIAS_BARRA
from app.visualizacao.formas import classificar_forma

pytestmark = pytest.mark.marco3


def test_um_valor_numerico_vira_metrica():
    """1 linha × 1 coluna numérica é classificada como métrica."""
    forma = classificar_forma(["total"], [(17,)])
    assert forma.tipo == "metrica"
    assert forma.coluna_valor == "total"


def test_serie_temporal_vira_linha():
    """1ª coluna com datas (por conteúdo) + numérica + ≥3 pontos → série temporal."""
    linhas = [("2025-01-01", 4), ("2025-02-01", 6), ("2025-03-01", 5)]
    forma = classificar_forma(["data", "n"], linhas)
    assert forma.tipo == "serie_temporal"
    assert forma.coluna_temporal == "data"
    assert forma.coluna_valor == "n"
    assert forma.coluna_categoria is None


def test_serie_com_categoria_extra_e_multiserie():
    """(mes, canal, n) vira série temporal multi-série — o caso da pergunta 5."""
    linhas = [
        ("2025-01", "Chat", 4), ("2025-01", "Telefone", 2),
        ("2025-02", "Chat", 6), ("2025-02", "Telefone", 3),
        ("2025-03", "Chat", 1), ("2025-03", "Telefone", 5),
    ]
    forma = classificar_forma(["mes", "canal", "n"], linhas)
    assert forma.tipo == "serie_temporal"
    assert forma.coluna_temporal == "mes"
    assert forma.coluna_categoria == "canal"
    assert forma.coluna_valor == "n"


def test_categorica_vira_barra():
    """Coluna textual com poucas categorias + numérica → comparação categórica."""
    linhas = [("Chat", 18), ("Telefone", 19), ("E-mail", 14)]
    forma = classificar_forma(["canal", "total"], linhas)
    assert forma.tipo == "categorica"
    assert forma.coluna_categoria == "canal"
    assert forma.coluna_valor == "total"


def test_serie_curta_nao_vira_linha():
    """2 pontos temporais → lista (linha com 2 pontos vira 'tendência' enganosa)."""
    forma = classificar_forma(["mes", "n"], [("2025-01", 3), ("2025-02", 9)])
    assert forma.tipo == "lista"


def test_muitas_categorias_vira_tabela():
    """Mais categorias que MAX_CATEGORIAS_BARRA → lista (barra viraria ruído)."""
    linhas = [(f"categoria_{i}", i) for i in range(MAX_CATEGORIAS_BARRA + 5)]
    forma = classificar_forma(["categoria", "n"], linhas)
    assert forma.tipo == "lista"


def test_resultado_vazio_vira_tabela():
    """0 linhas → lista, sem exceção (o visual nunca derruba a resposta)."""
    assert classificar_forma(["a", "b"], []).tipo == "lista"
    assert classificar_forma([], []).tipo == "lista"


def test_data_detectada_por_conteudo_nao_por_nome():
    """'mes' com '2025-01' É temporal; 'data' com texto comum NÃO é."""
    com_meses = [("2025-01", 1), ("2025-02", 2), ("2025-03", 3)]
    assert classificar_forma(["mes", "n"], com_meses).tipo == "serie_temporal"
    com_texto = [("alfa", 1), ("beta", 2), ("gama", 3)]
    assert classificar_forma(["data", "n"], com_texto).tipo == "categorica"
