# -*- coding: utf-8 -*-
"""
formas.py — Classificador da FORMA do dado (determinístico, custo LLM zero).

A heurística pré-setada (decisão fechada com Vahelle):
  1 valor numérico            → métrica
  série temporal (≥3 pontos)  → linha (multi-série se houver categoria extra)
  categórica + numérica       → barra
  todo o resto                → lista (= tabela)

Em dúvida, tabela: ela nunca mente e sempre responde. A detecção temporal é
por CONTEÚDO (reusa o detector do Perfilador) estendida a meses ('2025-01')
e anos ('2025') — agrupamentos mensais/anuais são a forma mais comum de
série em SQL e o detector de datas completas não os cobre (desvio registrado).
"""
import re
from dataclasses import dataclass

from app.config import MAX_CATEGORIAS_BARRA, MIN_PONTOS_LINHA
from app.perfilador import _eh_coluna_de_data

_PADRAO_ANO_MES = re.compile(r"^\d{4}-\d{2}$")
_PADRAO_ANO = re.compile(r"^\d{4}$")
_FRACAO_MINIMA = 0.8


@dataclass
class FormaDoDado:
    """O veredito do classificador sobre um conjunto de resultados."""
    tipo: str                       # 'metrica' | 'serie_temporal' | 'categorica' | 'lista'
    coluna_temporal: str | None = None
    coluna_categoria: str | None = None
    coluna_valor: str | None = None


def _coluna_numerica(linhas: list, indice: int) -> bool:
    """True se a coluna no índice é numérica (int/float, bool excluído)."""
    valores = [l[indice] for l in linhas if l[indice] is not None]
    if not valores:
        return False
    return all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in valores
    )


def _eh_temporal(valores: list) -> bool:
    """Detecção temporal por conteúdo: datas completas (detector do
    Perfilador) OU ano-mês ('2025-01') OU ano ('2025') — sempre strings."""
    textos = [str(v) for v in valores if v is not None and str(v).strip()]
    if not textos:
        return False
    if _eh_coluna_de_data(textos):
        return True
    for padrao in (_PADRAO_ANO_MES, _PADRAO_ANO):
        casam = sum(1 for t in textos if padrao.match(t))
        if casam / len(textos) >= _FRACAO_MINIMA:
            return True
    return False


def classificar_forma(colunas: list, linhas: list) -> FormaDoDado:
    """Aplica a heurística pré-setada. Nunca levanta exceção: o pior caso é
    'lista' (tabela)."""
    if not linhas or not colunas:
        return FormaDoDado(tipo="lista")

    indices_numericos = [
        i for i in range(len(colunas)) if _coluna_numerica(linhas, i)
    ]

    # 1 valor numérico → métrica
    if len(linhas) == 1 and len(colunas) == 1 and indices_numericos:
        return FormaDoDado(tipo="metrica", coluna_valor=colunas[0])

    # Série temporal: 1ª coluna com conteúdo temporal + coluna numérica.
    primeira = [l[0] for l in linhas]
    if _eh_temporal(primeira) and indices_numericos:
        pontos_distintos = len({str(v) for v in primeira})
        indice_valor = next(i for i in indices_numericos if i != 0)
        # Categoria extra (multi-série): coluna textual com poucos distintos.
        coluna_categoria = None
        for i in range(1, len(colunas)):
            if i in indices_numericos:
                continue
            distintos = {l[i] for l in linhas}
            if 2 <= len(distintos) <= MAX_CATEGORIAS_BARRA:
                coluna_categoria = colunas[i]
                break
        # Pontos suficientes? (por categoria, o eixo é o mesmo)
        if pontos_distintos >= MIN_PONTOS_LINHA:
            return FormaDoDado(
                tipo="serie_temporal",
                coluna_temporal=colunas[0],
                coluna_categoria=coluna_categoria,
                coluna_valor=colunas[indice_valor],
            )
        return FormaDoDado(tipo="lista")   # linha com <3 pontos engana

    # Categórica + numérica → barra (2..MAX categorias).
    for i in range(len(colunas)):
        if i in indices_numericos:
            continue
        distintos = {l[i] for l in linhas}
        if 2 <= len(distintos) <= MAX_CATEGORIAS_BARRA and indices_numericos:
            indice_valor = next(j for j in indices_numericos if j != i)
            return FormaDoDado(
                tipo="categorica",
                coluna_categoria=colunas[i],
                coluna_valor=colunas[indice_valor],
            )

    return FormaDoDado(tipo="lista")
