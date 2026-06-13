# -*- coding: utf-8 -*-
"""Testes dos templates pré-setados (Marco 3, microatividade 4)."""
import json

import pytest

from app.visualizacao.guardrail_visualizacao import validar_option
from app.visualizacao.templates import montar_especificacao_pre_setada

pytestmark = pytest.mark.marco3

LINHAS_BARRA = [("Chat", 18), ("Telefone", 19), ("E-mail", 14)]
LINHAS_MULTISERIE = [
    ("2025-01", "Chat", 4), ("2025-01", "Telefone", 2),
    ("2025-02", "Chat", 6),                              # Telefone falta em 2025-02
    ("2025-03", "Chat", 1), ("2025-03", "Telefone", 5),
]


def test_template_barra_ordenado():
    """Barras em ordem decrescente de valor, com categorias e valores corretos."""
    espec = montar_especificacao_pre_setada(["canal", "total"], LINHAS_BARRA, "t")
    assert espec.tipo == "barra"
    assert espec.option["xAxis"]["data"] == ["Telefone", "Chat", "E-mail"]
    assert espec.option["series"][0]["data"] == [19, 18, 14]


def test_template_linha_multiserie_pivot():
    """(mes, canal, n) → uma série por canal; meses no eixo X; zero onde falta."""
    espec = montar_especificacao_pre_setada(
        ["mes", "canal", "n"], LINHAS_MULTISERIE, "t"
    )
    assert espec.tipo == "linha"
    assert espec.option["xAxis"]["data"] == ["2025-01", "2025-02", "2025-03"]
    series = {s["name"]: s["data"] for s in espec.option["series"]}
    assert series["Chat"] == [4, 6, 1]
    assert series["Telefone"] == [2, 0, 5]       # zero preenchido pelo pivot


def test_template_metrica():
    """1 valor → métrica com valor formatado e rótulo da coluna."""
    espec = montar_especificacao_pre_setada(["clientes"], [(17,)], "t")
    assert espec.tipo == "metrica"
    assert espec.valor_metrica == "17"
    assert espec.rotulo_metrica == "clientes"
    assert espec.option is None


def test_template_tabela():
    """Forma livre → tabela com colunas e linhas intactas."""
    linhas = [("a", "b", "c"), ("d", "e", "f")]
    espec = montar_especificacao_pre_setada(["x", "y", "z"], linhas, "t")
    assert espec.tipo == "tabela"
    assert espec.colunas == ["x", "y", "z"]
    assert espec.linhas == linhas


def test_todos_templates_passam_no_guardrail():
    """TESTE CRUZADO: todo option dos templates é aprovado pelo próprio
    Guardrail (coerência interna do sistema)."""
    casos = [
        (["canal", "total"], LINHAS_BARRA),                 # barra
        (["mes", "canal", "n"], LINHAS_MULTISERIE),         # linha multi-série
        (["mes", "n"], [("2025-01", 1), ("2025-02", 2), ("2025-03", 3)]),  # linha
    ]
    for colunas, linhas in casos:
        espec = montar_especificacao_pre_setada(colunas, linhas, "título")
        assert espec.option is not None
        veredito = validar_option(json.dumps(espec.option, ensure_ascii=False))
        assert veredito.aprovado is True, veredito.motivo


def test_pre_setado_nunca_levanta_excecao():
    """Entradas patológicas → SEMPRE EspecificacaoVisual (tabela), nunca exceção."""
    casos = [
        ([], []),
        (["a"], []),
        (["a", "b"], [(None, None)]),
        (["a"], [("texto",)]),
        (["mes", "n"], [("2025-01", "não-número"), ("2025-02", 2), ("2025-03", 3)]),
    ]
    for colunas, linhas in casos:
        espec = montar_especificacao_pre_setada(colunas, linhas, "t")
        assert espec.tipo in {"tabela", "metrica", "linha", "barra"}


def test_pedido_explicito_de_tabela_vira_tabela():
    """V3.7: 'mostre em tabela' força tipo='tabela' (escolha do usuário, não
    fallback) — mesmo quando a forma dos dados sugeriria outro gráfico."""
    # dados em formato de barra (categórico), mas o usuário pediu tabela:
    espec = montar_especificacao_pre_setada(
        ["canal", "total"], [["App", 10], ["Site", 7]],
        "Mostre as vendas por canal em tabela",
    )
    assert espec.tipo == "tabela"
    assert espec.fallback_usado is False          # é escolha, não degradação
    assert espec.linhas == [["App", 10], ["Site", 7]]


def test_tabela_como_objeto_de_dado_nao_dispara_formato():
    """V3.7 (anti-falso-positivo): 'quantas linhas tem a tabela compras?'
    menciona 'tabela' como NOME de tabela, não como formato de saída — a
    heurística de forma decide normalmente (aqui, métrica)."""
    espec = montar_especificacao_pre_setada(
        ["total"], [[946]],
        "Quantas linhas tem a tabela compras?",
    )
    assert espec.tipo == "metrica"                # NÃO virou tabela por engano


def test_funcao_de_intencao_de_tabela_isola_formato_de_objeto():
    """V3.7: a função de intenção distingue formato de saída de nome de
    tabela — base testável da regra acima."""
    from app.visualizacao.templates import _pediu_tabela_explicitamente
    assert _pediu_tabela_explicitamente("quero o resultado em tabela") is True
    assert _pediu_tabela_explicitamente("exiba isso como tabela") is True
    assert _pediu_tabela_explicitamente(
        "quantas linhas tem a tabela compras?") is False
    assert _pediu_tabela_explicitamente(
        "qual o total de vendas por canal?") is False
