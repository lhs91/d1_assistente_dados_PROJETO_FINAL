# -*- coding: utf-8 -*-
"""
detector_denormalizacao.py — Camada 6 do Perfilador: detector GENÉRICO de
colunas denormalizadas divergentes.

O princípio (anti-overfitting, herdado do D2): este módulo NÃO conhece o
banco do desafio. Ele implementa um MECANISMO que, em qualquer SQLite:

  1. Para cada relação FK filha→pai, olha as colunas do PAI que não são PK/FK.
  2. Pareia candidatos por afinidade de NOME (tokens → agregado SUM/MAX/MIN)
     e compatibilidade de TIPO (numérico↔numérico; data↔data, com a data
     detectada por conteúdo).
  3. Mede a divergência: agregado por chave na filha vs valor na coluna do pai.
  4. Fração divergente ≥ limiar → AlertaQualidade com recomendação de fonte.

LIMITES (documentados no README — decisão registrada): o pareamento depende
de afinidade de nomes — uma coluna denormalizada com nome opaco escapa; o
mecanismo reduz drasticamente o risco, não o zera.
"""
import sqlite3
from dataclasses import dataclass

from app.config import LIMIAR_DIVERGENCIA, TOLERANCIA_REAL
from app.perfilador import AlertaQualidade, _eh_coluna_de_data

# Tokens (em minúsculas, sem acento) que sugerem cada agregado.
TOKENS_SUM = frozenset({"total", "soma", "valor", "gasto", "acumulado"})
TOKENS_MAX = frozenset({"ultima", "ultimo", "max", "recente"})
TOKENS_MIN = frozenset({"primeira", "primeiro", "min", "inicial"})

_TIPOS_NUMERICOS = {"REAL", "INTEGER", "NUMERIC", "FLOAT", "DOUBLE", "INT"}


@dataclass
class ParCandidato:
    """Um par (coluna do pai ↔ agregado de coluna da filha) a ser testado."""
    tabela_pai: str
    coluna_pai: str
    pk_pai: str
    tabela_filha: str
    coluna_filha: str
    fk_filha: str
    agregado: str               # 'SUM' | 'MAX' | 'MIN'
    tipo: str                   # 'numerico' | 'data'


def _sem_acento(texto: str) -> str:
    """Normalização simples de acentos para a comparação de tokens."""
    mapa = str.maketrans("áàâãéêíóôõúüç", "aaaaeeiooouuc")
    return texto.lower().translate(mapa)


def _afinidade_agregado(nome_coluna: str) -> str | None:
    """Tokeniza o nome (split por '_') e mapeia para SUM/MAX/MIN — ou None."""
    tokens = set(_sem_acento(nome_coluna).split("_"))
    if tokens & TOKENS_SUM:
        return "SUM"
    if tokens & TOKENS_MAX:
        return "MAX"
    if tokens & TOKENS_MIN:
        return "MIN"
    return None


def _colunas_de_data_da_tabela(cur: sqlite3.Cursor, tabela) -> set:
    """Nomes das colunas TEXT da tabela cujo CONTEÚDO parece data."""
    nomes = set()
    for coluna in tabela.colunas:
        if coluna.tipo != "TEXT" or coluna.e_pk:
            continue
        amostra = [
            v for (v,) in cur.execute(
                f"SELECT DISTINCT {coluna.nome} FROM {tabela.nome} LIMIT 50"
            )
        ]
        if _eh_coluna_de_data(amostra):
            nomes.add(coluna.nome)
    return nomes


def _parear_candidatos(cur: sqlite3.Cursor, estrutura: list) -> list:
    """Gera os pares candidatos a partir das FKs e da afinidade de nomes."""
    tabelas = {t.nome: t for t in estrutura}
    pares = []
    for filha in estrutura:
        for coluna_fk in filha.colunas:
            if not coluna_fk.e_fk or not coluna_fk.fk_referencia:
                continue
            nome_pai, pk_pai = coluna_fk.fk_referencia.split(".")
            pai = tabelas.get(nome_pai)
            if pai is None:
                continue

            datas_da_filha = _colunas_de_data_da_tabela(cur, filha)
            datas_do_pai = _colunas_de_data_da_tabela(cur, pai)

            for coluna_pai in pai.colunas:
                if coluna_pai.e_pk or coluna_pai.e_fk:
                    continue
                agregado = _afinidade_agregado(coluna_pai.nome)
                if agregado is None:
                    continue

                pai_e_numerico = coluna_pai.tipo in _TIPOS_NUMERICOS
                pai_e_data = coluna_pai.nome in datas_do_pai
                for coluna_filha in filha.colunas:
                    if coluna_filha.e_pk or coluna_filha.e_fk:
                        continue
                    filha_e_numerica = coluna_filha.tipo in _TIPOS_NUMERICOS
                    filha_e_data = coluna_filha.nome in datas_da_filha
                    # Compatibilidade de tipo define o teste:
                    if agregado == "SUM" and pai_e_numerico and filha_e_numerica:
                        tipo = "numerico"
                    elif agregado in {"MAX", "MIN"} and pai_e_data and filha_e_data:
                        tipo = "data"
                    elif agregado in {"MAX", "MIN"} and pai_e_numerico and filha_e_numerica:
                        tipo = "numerico"
                    else:
                        continue
                    pares.append(
                        ParCandidato(
                            tabela_pai=pai.nome,
                            coluna_pai=coluna_pai.nome,
                            pk_pai=pk_pai,
                            tabela_filha=filha.nome,
                            coluna_filha=coluna_filha.nome,
                            fk_filha=coluna_fk.nome,
                            agregado=agregado,
                            tipo=tipo,
                        )
                    )
    return pares


def _medir_divergencia(cur: sqlite3.Cursor, par: ParCandidato) -> float:
    """Fração de linhas do pai cujo valor difere do agregado da filha.

    LEFT JOIN: pai sem filhos compara contra agregado vazio (0 ou '').
    Comparação numérica usa TOLERANCIA_REAL; data compara igualdade exata.
    """
    if par.tipo == "numerico":
        comparacao = (
            f"ABS(COALESCE(p.{par.coluna_pai}, 0) - COALESCE(agg.valor, 0)) "
            f"> {TOLERANCIA_REAL}"
        )
    else:
        comparacao = (
            f"COALESCE(p.{par.coluna_pai}, '') != COALESCE(agg.valor, '')"
        )
    sql = f"""
        SELECT AVG(CASE WHEN {comparacao} THEN 1.0 ELSE 0.0 END)
        FROM {par.tabela_pai} p
        LEFT JOIN (
            SELECT {par.fk_filha} AS chave,
                   {par.agregado}({par.coluna_filha}) AS valor
            FROM {par.tabela_filha}
            GROUP BY {par.fk_filha}
        ) agg ON agg.chave = p.{par.pk_pai}
    """
    fracao = cur.execute(sql).fetchone()[0]
    return float(fracao or 0.0)


def detectar(
    cur: sqlite3.Cursor,
    estrutura: list,
    limiar: float = LIMIAR_DIVERGENCIA,
) -> list:
    """Roda o mecanismo completo e devolve os AlertaQualidade encontrados."""
    alertas = []
    for par in _parear_candidatos(cur, estrutura):
        fracao = _medir_divergencia(cur, par)
        if fracao >= limiar:
            pct = round(fracao * 100)
            alertas.append(
                AlertaQualidade(
                    tabela_pai=par.tabela_pai,
                    coluna_pai=par.coluna_pai,
                    tabela_filha=par.tabela_filha,
                    coluna_filha=par.coluna_filha,
                    agregado=par.agregado,
                    pct_divergencia=fracao,
                    mensagem=(
                        f"{par.tabela_pai}.{par.coluna_pai} diverge de "
                        f"{par.agregado}({par.tabela_filha}.{par.coluna_filha}) "
                        f"em {pct}% das linhas — prefira a fonte transacional "
                        f"({par.tabela_filha})."
                    ),
                )
            )
    return alertas
