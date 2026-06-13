# -*- coding: utf-8 -*-
"""
templates.py — Os options pré-setados (determinísticos, custo LLM ZERO).

É a tese do projeto em miniatura: a mecânica conhecida (forma do dado →
gráfico padrão) não paga modelo. O pivot da multi-série é transformação
mecânica — Python, nunca LLM.

Coerência interna garantida por teste: TODO option gerado aqui passa no
Guardrail de Visualização (test_todos_templates_passam_no_guardrail).
"""
from app.estado import EspecificacaoVisual
from app.visualizacao.formas import FormaDoDado, classificar_forma


def _indice(colunas: list, nome: str) -> int:
    return colunas.index(nome)


def _option_base(titulo: str) -> dict:
    """Esqueleto comum: título e tooltip (template string — JSON puro)."""
    return {
        "title": {"text": titulo[:90]},
        "tooltip": {"trigger": "axis"},
        "grid": {"containLabel": True},
    }


def _option_linha(forma: FormaDoDado, colunas: list, linhas: list, titulo: str) -> dict:
    """Linha temporal; com categoria extra, PIVOT em Python: uma série por
    categoria, eixo X = pontos temporais ordenados, zeros onde faltar."""
    i_tempo = _indice(colunas, forma.coluna_temporal)
    i_valor = _indice(colunas, forma.coluna_valor)
    eixo_x = sorted({str(l[i_tempo]) for l in linhas})

    option = _option_base(titulo)
    option["xAxis"] = {"type": "category", "data": eixo_x,
                       "name": forma.coluna_temporal}
    option["yAxis"] = {"type": "value", "name": forma.coluna_valor}

    if forma.coluna_categoria:
        i_cat = _indice(colunas, forma.coluna_categoria)
        categorias = sorted({str(l[i_cat]) for l in linhas})
        mapa = {(str(l[i_tempo]), str(l[i_cat])): l[i_valor] for l in linhas}
        option["legend"] = {"data": categorias}
        option["series"] = [
            {
                "name": categoria,
                "type": "line",
                "data": [mapa.get((x, categoria), 0) for x in eixo_x],
            }
            for categoria in categorias
        ]
    else:
        mapa = {str(l[i_tempo]): l[i_valor] for l in linhas}
        option["series"] = [
            {"name": forma.coluna_valor, "type": "line",
             "data": [mapa.get(x, 0) for x in eixo_x]}
        ]
    return option


def _option_barra(forma: FormaDoDado, colunas: list, linhas: list, titulo: str) -> dict:
    """Barras por categoria, ordenadas por valor decrescente."""
    i_cat = _indice(colunas, forma.coluna_categoria)
    i_valor = _indice(colunas, forma.coluna_valor)
    pares = sorted(
        ((str(l[i_cat]), l[i_valor]) for l in linhas),
        key=lambda par: par[1],
        reverse=True,
    )
    option = _option_base(titulo)
    option["xAxis"] = {"type": "category",
                       "data": [c for c, _ in pares],
                       "name": forma.coluna_categoria}
    option["yAxis"] = {"type": "value", "name": forma.coluna_valor}
    option["series"] = [
        {"name": forma.coluna_valor, "type": "bar",
         "data": [v for _, v in pares]}
    ]
    return option


def _especificacao_metrica(colunas: list, linhas: list, titulo: str) -> EspecificacaoVisual:
    """Número grande + rótulo: 1 valor não precisa de gráfico."""
    valor = linhas[0][0]
    if isinstance(valor, float):
        valor_texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        valor_texto = str(valor)
    return EspecificacaoVisual(
        modo="pre_setado", tipo="metrica", option=None,
        valor_metrica=valor_texto, rotulo_metrica=str(colunas[0]),
        colunas=None, linhas=None,
        justificativa="Um único valor: métrica em destaque diz mais que gráfico.",
    )


def _especificacao_tabela(
    colunas: list, linhas: list, justificativa: str,
    fallback: bool = False, motivo: str | None = None,
) -> EspecificacaoVisual:
    """Tabela: o porto seguro universal — e também O fallback do sistema."""
    return EspecificacaoVisual(
        modo="pre_setado", tipo="tabela", option=None,
        valor_metrica=None, rotulo_metrica=None,
        colunas=list(colunas), linhas=list(linhas),
        justificativa=justificativa,
        fallback_usado=fallback, motivo_fallback=motivo,
    )


import re


def _pediu_tabela_explicitamente(pergunta: str) -> bool:
    """True se a pergunta pede a SAÍDA em forma de TABELA/LISTA — por menção
    de formato ('em tabela') OU por VERBO DE LISTAGEM ('liste', 'listar',
    'relacione', 'enumere', 'liste todos'). Determinístico e independente do
    LLM: vale para os DOIS modos (pre_setado e agente). Anti-falso-positivo
    para 'tabela <nome>' (objeto de dado, não formato de saída)."""
    p = (pergunta or "").lower()
    # 1) Verbo de LISTAGEM em qualquer lugar (o gatilho que faltava): pedir
    #    para "listar" é, por definição, pedir uma lista/tabela.
    if re.search(r"\b(?:liste|listar|listad[oa]s?|relacione|relacionar|"
                 r"enumere|enumerar)\b", p):
        return True
    # 2) Menção explícita de FORMATO tabela + verbo de exibição perto.
    padroes = (
        r"\bem (?:uma )?tabela\b",
        r"\b(?:como|formato|em forma) de tabela\b",
        r"\b(?:mostre|exiba|apresente|quero|gere|monte|traga|me d[eê])"
        r"[^.?!]{0,30}\btabela\b",
        r"\btabela\b[^.?!]{0,20}\b(?:com|dos|das|de)\b.*",
    )
    # Anti-falso-positivo: "tabela <nome_de_tabela>" (objeto de dado) não conta
    # — MAS só se não houver verbo de listagem (já tratado acima).
    if re.search(r"\btabela\s+(?:compras|clientes|suporte|campanhas|"
                 r"itens|pedidos)\b", p):
        return False
    return any(re.search(pat, p) for pat in padroes)


def montar_especificacao_pre_setada(
    colunas: list, linhas: list, titulo: str,
) -> EspecificacaoVisual:
    """Classifica a forma e delega ao template. NUNCA levanta exceção:
    qualquer surpresa degrada para tabela (o visual jamais derruba a resposta)."""
    try:
        # Intenção explícita de tabela (V3.7) tem prioridade sobre a heurística
        # de forma — o usuário pediu tabela, entregamos tabela (não é fallback).
        if _pediu_tabela_explicitamente(titulo):
            return _especificacao_tabela(
                colunas, linhas,
                "Você pediu o resultado em tabela.",
            )
        forma = classificar_forma(colunas, linhas)
        if forma.tipo == "metrica":
            return _especificacao_metrica(colunas, linhas, titulo)
        if forma.tipo == "serie_temporal":
            option = _option_linha(forma, colunas, linhas, titulo)
            return EspecificacaoVisual(
                modo="pre_setado", tipo="linha", option=option,
                valor_metrica=None, rotulo_metrica=None, colunas=None, linhas=None,
                justificativa=(
                    "Série temporal detectada: linha"
                    + (f" (uma por {forma.coluna_categoria})" if forma.coluna_categoria else "")
                    + " mostra a evolução."
                ),
            )
        if forma.tipo == "categorica":
            option = _option_barra(forma, colunas, linhas, titulo)
            return EspecificacaoVisual(
                modo="pre_setado", tipo="barra", option=option,
                valor_metrica=None, rotulo_metrica=None, colunas=None, linhas=None,
                justificativa=(
                    f"Comparação entre categorias de '{forma.coluna_categoria}': "
                    "barras ordenadas facilitam a leitura."
                ),
            )
        return _especificacao_tabela(
            colunas, linhas,
            "Forma livre de dados: tabela preserva tudo sem distorcer.",
        )
    except Exception as excecao:  # noqa: BLE001 — visual nunca derruba resposta
        return _especificacao_tabela(
            colunas or [], linhas or [],
            "Tabela de segurança.",
            fallback=True,
            motivo=f"Falha ao montar o gráfico pré-setado: {excecao}",
        )
