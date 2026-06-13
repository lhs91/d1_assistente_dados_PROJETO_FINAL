# -*- coding: utf-8 -*-
"""Testes do Guardrail de Visualização (Marco 3, microatividade 3).

O conjunto mais crítico do marco: a bateria de injeção. A regra do projeto
(guardada em memória): option = JSON PURO, JsCode/JS PROIBIDOS.
"""
import json

import pytest

from app.config import LIMITE_PROFUNDIDADE_OPTION
from app.visualizacao.guardrail_visualizacao import validar_option

pytestmark = pytest.mark.marco3

OPTION_BARRA = json.dumps({
    "title": {"text": "Reclamações por canal"},
    "tooltip": {"trigger": "axis"},
    "xAxis": {"type": "category", "data": ["Telefone", "Chat", "E-mail"]},
    "yAxis": {"type": "value"},
    "series": [{"name": "total", "type": "bar", "data": [19, 18, 14]}],
})


def test_aprova_option_legitimo_de_barra():
    """Option válido com series/xAxis/yAxis passa e volta parseado em dict."""
    veredito = validar_option(OPTION_BARRA)
    assert veredito.aprovado is True
    assert veredito.option["series"][0]["data"] == [19, 18, 14]


def test_aprova_option_complexo_multiserie():
    """Linha multi-série com legend/tooltip/grid passa (liberdade dentro do JSON)."""
    option = json.dumps({
        "title": {"text": "Tendência"},
        "legend": {"data": ["Chat", "Telefone"]},
        "tooltip": {"trigger": "axis"},
        "grid": {"containLabel": True},
        "xAxis": {"type": "category", "data": ["2025-01", "2025-02"]},
        "yAxis": {"type": "value"},
        "series": [
            {"name": "Chat", "type": "line", "data": [4, 6]},
            {"name": "Telefone", "type": "line", "data": [2, 3]},
        ],
    })
    assert validar_option(option).aprovado is True


def test_aprova_formatter_template():
    """formatter como TEMPLATE ('{b}: {c}') é string de dados — passa."""
    option = json.dumps({
        "tooltip": {"formatter": "{b}: {c}"},
        "series": [{"type": "pie", "data": [{"name": "a", "value": 1}]}],
    })
    assert validar_option(option).aprovado is True


def test_reprova_function_classica():
    """formatter com function(...) é código executável — reprovado com caminho."""
    option = json.dumps({
        "tooltip": {"formatter": "function(p){ return p.value; }"},
        "series": [{"type": "bar", "data": [1]}],
    })
    veredito = validar_option(option)
    assert veredito.aprovado is False
    assert "tooltip.formatter" in veredito.motivo
    assert "function(" in veredito.motivo


def test_reprova_arrow_function():
    """Arrow function (=>) reprovada."""
    option = json.dumps({
        "tooltip": {"formatter": "(p) => p.value"},
        "series": [{"type": "bar", "data": [1]}],
    })
    assert validar_option(option).aprovado is False


@pytest.mark.parametrize("malicia", ["eval(alert(1))", "new Function('x')"])
def test_reprova_eval_e_new_function(malicia):
    """eval e new Function reprovados onde quer que apareçam."""
    option = json.dumps({
        "title": {"text": malicia},
        "series": [{"type": "bar", "data": [1]}],
    })
    assert validar_option(option).aprovado is False


@pytest.mark.parametrize(
    "malicia", ["<script>alert(1)</script>", "javascript:alert(1)"]
)
def test_reprova_script_e_javascript_uri(malicia):
    """<script> e javascript: reprovados (também protegem o preview HTML)."""
    option = json.dumps({
        "title": {"text": malicia},
        "series": [{"type": "bar", "data": [1]}],
    })
    assert validar_option(option).aprovado is False


def test_reprova_jscode_em_qualquer_caixa():
    """JsCode (o mecanismo do streamlit-echarts) reprovado, case-insensitive."""
    for variacao in ["JsCode(...)", "jscode", "JSCODE"]:
        option = json.dumps({
            "series": [{"type": "bar", "data": [1], "marcador": variacao}],
        })
        assert validar_option(option).aprovado is False


def test_reprova_padrao_em_chave():
    """Padrão proibido na CHAVE do JSON (não só no valor) também reprova."""
    option = json.dumps({
        "series": [{"type": "bar", "data": [1]}],
        "eval(x)": "qualquer coisa",
    })
    veredito = validar_option(option)
    assert veredito.aprovado is False
    assert "chave" in veredito.motivo


def test_reprova_json_invalido():
    """String que não é JSON → motivo claro, sem exceção."""
    veredito = validar_option("{series: [sem aspas]}")
    assert veredito.aprovado is False
    assert "JSON" in veredito.motivo
    assert validar_option("").aprovado is False
    assert validar_option(None).aprovado is False


def test_reprova_raiz_nao_dict():
    """Raiz lista ou escalar reprovada (option ECharts é um objeto)."""
    assert validar_option("[1, 2, 3]").aprovado is False
    assert validar_option('"texto"').aprovado is False


def test_reprova_tamanho_e_profundidade():
    """Option gigante e aninhamento além do limite reprovados."""
    gigante = json.dumps({"series": [{"data": ["x" * 60_000]}]})
    assert validar_option(gigante).aprovado is False

    aninhado = {"series": [{"type": "bar", "data": [1]}]}
    no = aninhado
    for _ in range(LIMITE_PROFUNDIDADE_OPTION + 2):
        no["filho"] = {}
        no = no["filho"]
    assert validar_option(json.dumps(aninhado)).aprovado is False


def test_reprova_sem_series():
    """Dict sem 'series' (ou com series vazia) reprovado — não há gráfico sem séries."""
    assert validar_option(json.dumps({"title": {"text": "x"}})).aprovado is False
    assert validar_option(json.dumps({"series": []})).aprovado is False


def test_reprova_tipo_map_nao_suportado():
    """series.type 'map' exige GeoJSON externo não embarcado → reprovado com motivo claro."""
    option = json.dumps({
        "series": [{"type": "map", "map": "brasil",
                    "data": [{"name": "São Paulo", "value": 184}]}]
    })
    veredito = validar_option(option)
    assert veredito.aprovado is False
    assert "map" in veredito.motivo and "tabela" in veredito.motivo


def test_reprova_componente_geo_de_topo():
    """A chave de topo 'geo' (componente de mapa do ECharts) também é barrada."""
    option = json.dumps({
        "geo": {"map": "brasil"},
        "series": [{"type": "scatter", "data": [[1, 2]]}],
    })
    assert validar_option(option).aprovado is False


def test_bar3d_rejeitado_de_forma_controlada():
    """V3.6: bar3D/scatter3D exigem echarts-gl (ausente no runtime) — o
    guardrail rejeita com motivo claro em vez de quebrar o componente."""
    resultado = validar_option(
        json.dumps({"series": [{"type": "bar3D", "data": [[0, 0, 1]]}]}))
    assert resultado.aprovado is False
    assert "bar3d" in resultado.motivo.lower()
