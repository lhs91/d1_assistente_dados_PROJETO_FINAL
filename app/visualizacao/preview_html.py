# -*- coding: utf-8 -*-
"""
preview_html.py — Preview standalone da visualização (teste de fogo do M3).

Gera um HTML que abre em qualquer navegador: ECharts via CDN e o option
EMBUTIDO como DADOS (json.dumps) — o mesmo paradigma do renderizador final
(st_echarts no M4): nenhum código gerado por LLM é executado; o único JS da
página é o template FIXO abaixo, escrito por nós.

Segurança: o Guardrail de Visualização já barrou '<script' dentro do option,
então a serialização não pode quebrar a tag; textos do usuário/LLM passam
por html.escape.
"""
import html
import json
from pathlib import Path

from app.estado import EspecificacaoVisual

_CDN_ECHARTS = "https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"


def _bloco_visual(especificacao: EspecificacaoVisual) -> str:
    """O miolo: gráfico ECharts, métrica grande ou tabela HTML."""
    if especificacao.option is not None:
        option_serializado = json.dumps(especificacao.option, ensure_ascii=False)
        return (
            f'<div id="grafico" style="width:100%;height:480px;"></div>\n'
            f'<script src="{_CDN_ECHARTS}"></script>\n'
            "<script>\n"
            "  // JS FIXO do template (escrito por nós); o option é só DADOS.\n"
            f"  var option = {option_serializado};\n"
            '  echarts.init(document.getElementById("grafico")).setOption(option);\n'
            "</script>"
        )
    if especificacao.tipo == "metrica":
        return (
            '<div class="metrica">'
            f"<div class='valor'>{html.escape(str(especificacao.valor_metrica))}</div>"
            f"<div class='rotulo'>{html.escape(str(especificacao.rotulo_metrica))}</div>"
            "</div>"
        )
    # Tabela (inclui o fallback).
    cabecalho = "".join(
        f"<th>{html.escape(str(c))}</th>" for c in (especificacao.colunas or [])
    )
    corpo = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in linha) + "</tr>"
        for linha in (especificacao.linhas or [])
    )
    return f"<table><thead><tr>{cabecalho}</tr></thead><tbody>{corpo}</tbody></table>"


def gerar_preview_html(
    especificacao: EspecificacaoVisual,
    pergunta: str,
    resposta: str | None,
    caminho_saida: Path,
) -> Path:
    """Gera o HTML standalone e retorna o caminho gravado."""
    aviso_fallback = ""
    if especificacao.fallback_usado:
        aviso_fallback = (
            '<p class="fallback">⚠ Exibindo tabela de segurança (fallback). '
            f"Motivo: {html.escape(str(especificacao.motivo_fallback))}</p>"
        )
    documento = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Preview — Assistente Virtual de Dados</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 2rem; color: #222; }}
  h1 {{ font-size: 1.1rem; color: #444; }}
  .resposta {{ background: #f3f6ff; border-left: 4px solid #6c7ce3;
               padding: .8rem 1rem; margin: 1rem 0; }}
  .metrica {{ text-align: center; margin: 3rem 0; }}
  .metrica .valor {{ font-size: 4rem; font-weight: bold; color: #6c7ce3; }}
  .metrica .rotulo {{ font-size: 1.1rem; color: #666; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ccc; padding: .4rem .6rem; text-align: left; }}
  th {{ background: #eef; }}
  .rodape {{ margin-top: 1.2rem; font-size: .85rem; color: #777; }}
  .fallback {{ color: #b00; }}
</style>
</head>
<body>
<h1>Pergunta: {html.escape(pergunta)}</h1>
{f'<div class="resposta">{html.escape(resposta)}</div>' if resposta else ""}
{aviso_fallback}
{_bloco_visual(especificacao)}
<p class="rodape">modo: {html.escape(especificacao.modo)} ·
tipo: {html.escape(especificacao.tipo)} ·
justificativa: {html.escape(especificacao.justificativa)}</p>
</body>
</html>"""
    caminho_saida = Path(caminho_saida)
    caminho_saida.write_text(documento, encoding="utf-8")
    return caminho_saida
