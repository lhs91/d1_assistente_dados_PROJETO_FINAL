# -*- coding: utf-8 -*-
"""Testes do preview HTML standalone (Marco 3, microatividade 7)."""
import json

import pytest

from app.estado import EspecificacaoVisual
from app.visualizacao.preview_html import gerar_preview_html

pytestmark = pytest.mark.marco3


def _espec_grafico():
    return EspecificacaoVisual(
        modo="agente", tipo="barra",
        option={"series": [{"type": "bar", "data": [19, 18, 14]}],
                "xAxis": {"data": ["Telefone", "Chat", "E-mail"]}},
        valor_metrica=None, rotulo_metrica=None, colunas=None, linhas=None,
        justificativa="comparação categórica",
    )


def test_html_embute_option_como_dados(tmp_path):
    """O option entra serializado (json.dumps) e o único JS é o template fixo."""
    caminho = gerar_preview_html(
        _espec_grafico(), "Reclamações por canal?", "Telefone lidera.",
        tmp_path / "p.html",
    )
    html = caminho.read_text(encoding="utf-8")
    assert json.dumps(_espec_grafico().option, ensure_ascii=False) in html
    assert "setOption(option)" in html
    assert "echarts.min.js" in html
    # Nenhum padrão perigoso além do JS FIXO do template (sem eval/JsCode):
    assert "eval(" not in html and "JsCode" not in html and "=>" not in html


def test_html_de_metrica_e_tabela(tmp_path):
    """Métrica vira número grande; tabela vira <table> com colunas/linhas."""
    metrica = EspecificacaoVisual(
        modo="pre_setado", tipo="metrica", option=None,
        valor_metrica="17", rotulo_metrica="clientes",
        colunas=None, linhas=None, justificativa="um valor",
    )
    html_metrica = gerar_preview_html(
        metrica, "Quantos?", "17 clientes.", tmp_path / "m.html"
    ).read_text(encoding="utf-8")
    assert ">17<" in html_metrica and "clientes" in html_metrica

    tabela = EspecificacaoVisual(
        modo="pre_setado", tipo="tabela", option=None,
        valor_metrica=None, rotulo_metrica=None,
        colunas=["canal", "total"], linhas=[("Chat", 18), ("Telefone", 19)],
        justificativa="tabela",
    )
    html_tabela = gerar_preview_html(
        tabela, "Por canal?", None, tmp_path / "t.html"
    ).read_text(encoding="utf-8")
    assert "<table>" in html_tabela
    assert "<th>canal</th>" in html_tabela
    assert "<td>Telefone</td>" in html_tabela and "<td>19</td>" in html_tabela


def test_html_indica_fallback(tmp_path):
    """fallback_usado=True → o aviso com o motivo aparece (transparência)."""
    espec = EspecificacaoVisual(
        modo="agente", tipo="tabela", option=None,
        valor_metrica=None, rotulo_metrica=None,
        colunas=["a"], linhas=[("b",)],
        justificativa="tabela de segurança",
        fallback_usado=True, motivo_fallback="option reprovado: function(",
    )
    html = gerar_preview_html(
        espec, "pergunta", "resposta", tmp_path / "f.html"
    ).read_text(encoding="utf-8")
    assert "fallback" in html
    assert "option reprovado" in html
