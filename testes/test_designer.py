# -*- coding: utf-8 -*-
"""Testes do Designer de Visualização (Marco 3, microatividade 5). Mockado."""
import json

import pytest

from app.agentes.designer_visualizacao import propor_visualizacao
from app.estado import PropostaDoDesigner
from testes.llm_falso import LlmRoteirizado

pytestmark = pytest.mark.marco3

RESULTADO = {
    "objetivo": "contar reclamações por canal",
    "sql": "SELECT canal, COUNT(*) FROM suporte GROUP BY canal",
    "justificativa": "agrupa por canal",
    "colunas": ["canal", "total"],
    "linhas": [("Chat", 18), ("Telefone", 19)],
    "n_linhas": 2,
    "truncado": False,
    "tentativas": 1,
}

PROPOSTA_OK = PropostaDoDesigner(
    tipo_grafico="barra",
    option_json=json.dumps({"series": [{"type": "bar", "data": [19, 18]}]}),
    justificativa="comparação categórica",
)


def test_proposta_estruturada():
    """A saída do Designer vira PropostaDoDesigner (tipo, option_json, justificativa)."""
    llm = LlmRoteirizado({PropostaDoDesigner: [PROPOSTA_OK]})
    saida = propor_visualizacao("pergunta", RESULTADO, "objetivo", llm=llm)
    assert isinstance(saida, PropostaDoDesigner)
    assert saida.tipo_grafico == "barra"


def test_prompt_proibe_js_e_exige_json_puro():
    """O prompt carrega as proibições (function/JsCode/eval) e a regra do template."""
    llm = LlmRoteirizado({PropostaDoDesigner: [PROPOSTA_OK]})
    propor_visualizacao("pergunta", RESULTADO, "objetivo", llm=llm)
    prompt = llm.prompts[0]
    assert "JSON PURO" in prompt
    assert "function" in prompt and "JsCode" in prompt and "eval" in prompt
    assert "{b}: {c}" in prompt          # formatter só como template


def test_prompt_contem_dados_e_pergunta():
    """Os dados do resultado e a pergunta entram no prompt (não inventar valores)."""
    llm = LlmRoteirizado({PropostaDoDesigner: [PROPOSTA_OK]})
    propor_visualizacao("Quantas reclamações?", RESULTADO, "objetivo", llm=llm)
    prompt = llm.prompts[0]
    assert "Quantas reclamações?" in prompt
    assert "('Chat', 18)" in prompt
    assert "não invente" in prompt


def test_prompt_obedece_formato_pedido():
    """A regra do enunciado — obedecer formato pedido pelo usuário — está no prompt."""
    llm = LlmRoteirizado({PropostaDoDesigner: [PROPOSTA_OK]})
    propor_visualizacao("Me mostre em pizza", RESULTADO, "objetivo", llm=llm)
    assert "OBEDEÇA" in llm.prompts[0]


def test_retry_carrega_motivo_da_reprova():
    """No retry, o motivo do Guardrail entra no prompt para a correção."""
    llm = LlmRoteirizado({PropostaDoDesigner: [PROPOSTA_OK]})
    propor_visualizacao(
        "pergunta", RESULTADO, "objetivo",
        motivo_da_reprova="Conteúdo executável proibido em tooltip.formatter",
        llm=llm,
    )
    prompt = llm.prompts[0]
    assert "REPROVADA" in prompt
    assert "tooltip.formatter" in prompt


def test_prompt_exige_arredondamento():
    """A regra de arredondar valores (2 casas) nos dados do option está no prompt."""
    llm = LlmRoteirizado({PropostaDoDesigner: [PROPOSTA_OK]})
    propor_visualizacao("pergunta", RESULTADO, "objetivo", llm=llm)
    prompt = llm.prompts[0]
    assert "ARREDONDE" in prompt and "2" in prompt


def test_prompt_do_designer_pede_variedade_e_proibe_mapas():
    """V2: o Designer é instruído a variar (rosca/radar/heatmap/treemap...)
    e a NUNCA propor map/geo (rejeitados pelo guardrail)."""
    from app.agentes.designer_visualizacao import _prompt_do_designer
    prompt = _prompt_do_designer(
        "pergunta", {"colunas": ["a"], "linhas": [[1]], "n_linhas": 1},
        "ok", None,
    )
    for tipo in ("rosca", "radar", "treemap", "gauge", "funil"):
        assert tipo in prompt
    assert "PROIBIDO map/geo" in prompt
    assert "CAPRICHE NA ESTÉTICA" in prompt


def test_prompt_tem_galeria_preferencial_com_sentido_matematico():
    """V3.6: a regra 6c prioriza a galeria (punch card, padAngle, regressão,
    heatmap, trees, treemap, sunburst, sankey, funnel, gauge, pictorialBar,
    calendar, matriz, chord) QUANDO a pergunta fizer sentido matemático —
    caso contrário libera qualquer tipo da biblioteca."""
    from app.agentes.designer_visualizacao import _prompt_do_designer
    prompt = _prompt_do_designer(
        "p", {"objetivo": "o", "sql": "s", "colunas": ["c"],
              "linhas": [[1]], "n_linhas": 1, "truncado": False},
        justificativa_da_resposta="j", motivo_da_reprova=None)
    assert "GALERIA PREFERENCIAL" in prompt
    assert "SENTIDO MATEMÁTICO" in prompt
    for marco in ("Punch card", "padAngle", "Polynomial Regression",
                  "Heatmap", "tree", "Treemap", "Sunburst", "Sankey",
                  "Funnel", "Gauge", "PictorialBar", "Calendar", "Matrix",
                  "Chord", "escolha LIVREMENTE"):
        assert marco in prompt, marco


def test_prompt_do_designer_cobre_pedido_de_tabela():
    """V3.7: a regra 6z instrui o Designer a responder tipo_grafico='tabela'
    com option vazio quando o usuário pede o resultado em tabela."""
    from app.agentes.designer_visualizacao import _prompt_do_designer
    prompt = _prompt_do_designer(
        "Mostre em tabela", {"objetivo": "o", "sql": "s", "colunas": ["c"],
                             "linhas": [[1]], "n_linhas": 1, "truncado": False},
        justificativa_da_resposta="j", motivo_da_reprova=None)
    assert "PEDIDO EXPLÍCITO DE TABELA" in prompt
    assert "tipo_grafico='tabela'" in prompt
