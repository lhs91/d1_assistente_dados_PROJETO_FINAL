# -*- coding: utf-8 -*-
"""Testes do Perfilador do Banco — camadas 1 a 5 (Marco 1, microatividade 5)."""
import pytest

from app.config import LIMITE_AMOSTRAS
from app.perfilador import (
    _eh_coluna_de_data,
    perfilar,
    renderizar_para_prompt,
)

pytestmark = pytest.mark.marco1


def _tabela(perfil, nome):
    return next(t for t in perfil.estrutura if t.nome == nome)


def test_estrutura_com_fks_corretas(banco_sintetico):
    perfil = perfilar(banco_sintetico, usar_cache=False)
    assert {t.nome for t in perfil.estrutura} == {"pedidos", "itens"}

    itens = _tabela(perfil, "itens")
    fk = next(c for c in itens.colunas if c.nome == "pedido_id")
    assert fk.e_fk is True
    assert fk.fk_referencia == "pedidos.id"

    pedidos = _tabela(perfil, "pedidos")
    pk = next(c for c in pedidos.colunas if c.nome == "id")
    assert pk.e_pk is True
    preco = next(c for c in _tabela(perfil, "itens").colunas if c.nome == "preco")
    assert preco.tipo == "REAL"


def test_volumetria_exata(banco_sintetico):
    perfil = perfilar(banco_sintetico, usar_cache=False)
    assert _tabela(perfil, "pedidos").n_linhas == 20
    assert _tabela(perfil, "itens").n_linhas == 60      # 20 pedidos × 3 itens


def test_amostras_respeitam_limite(banco_sintetico):
    perfil = perfilar(banco_sintetico, usar_cache=False)
    for nome, linhas in perfil.amostras.items():
        assert len(linhas) <= LIMITE_AMOSTRAS
        assert perfil.cabecalhos[nome]                   # cabeçalhos presentes
    assert "preco" in perfil.cabecalhos["itens"]


def test_dicionario_ignora_alta_cardinalidade(banco_sintetico):
    """itens.codigo tem 60 distintos (> limite) → fica FORA do dicionário;
    itens.origem tem 2 → fica DENTRO."""
    perfil = perfilar(banco_sintetico, usar_cache=False)
    assert "codigo" not in perfil.dicionario_categorico.get("itens", {})
    assert "origem" in perfil.dicionario_categorico["itens"]


def test_dicionario_capta_dominios_disjuntos(banco_real):
    """Banco REAL: 'canal' aparece com os 3 domínios distintos por tabela —
    a Armadilha 2 fica visível no dossiê."""
    perfil = perfilar(banco_real, usar_cache=False)
    valores = lambda tabela: {  # noqa: E731
        v for v, _ in perfil.dicionario_categorico[tabela]["canal"]
    }
    assert valores("compras") == {"App", "Loja Física", "Site"}
    assert valores("suporte") == {"Chat", "Telefone", "E-mail"}
    assert valores("campanhas_marketing") == {"SMS", "WhatsApp", "E-mail"}


def test_perfil_temporal_min_max_formato(banco_sintetico):
    perfil = perfilar(banco_sintetico, usar_cache=False)
    info = perfil.perfil_temporal["itens.data_item"]
    assert info["minimo"] == "2025-03-10"
    assert info["maximo"] == "2025-03-12"
    assert info["formatos"] == ["####-##-##"]


def test_deteccao_de_data_por_conteudo(banco_sintetico):
    """data_recente (TEXT com datas) é reconhecida; observacao (TEXT comum) não."""
    perfil = perfilar(banco_sintetico, usar_cache=False)
    assert "pedidos.data_recente" in perfil.perfil_temporal
    assert "pedidos.observacao" not in perfil.perfil_temporal
    # E a função, diretamente, nos dois sentidos:
    assert _eh_coluna_de_data(["2025-01-01", "2024-12-31"]) is True
    assert _eh_coluna_de_data(["João", "Maria", "2025-01-01"]) is False


def test_render_para_prompt_contem_secoes_criticas(banco_real):
    """O dossiê textual carrega o que mata cada armadilha."""
    perfil = perfilar(banco_real, usar_cache=False)
    dossie = renderizar_para_prompt(perfil)
    assert "VALORES CATEGÓRICOS" in dossie
    assert "'Loja Física'" in dossie                 # dicionário com valor exato
    assert "ÂNCORA TEMPORAL" in dossie
    assert "2025-07-22" in dossie                    # fim real dos dados
    assert "ALERTAS DE QUALIDADE" in dossie
    assert "fonte transacional" in dossie            # Armadilha 1 no dossiê


def test_cache_por_caminho(banco_sintetico):
    """Segunda chamada com cache devolve o MESMO objeto (não recalcula)."""
    primeiro = perfilar(banco_sintetico, usar_cache=True)
    segundo = perfilar(banco_sintetico, usar_cache=True)
    assert primeiro is segundo
    # E sem cache, recalcula (objeto novo):
    terceiro = perfilar(banco_sintetico, usar_cache=False)
    assert terceiro is not primeiro
