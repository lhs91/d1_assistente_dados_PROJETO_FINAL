# -*- coding: utf-8 -*-
"""
perfilador.py — Perfilador do Banco: o dossiê em 6 camadas.

É o "mapa do território" que os agentes recebem no prompt. A diferença entre
dar ao LLM uma planta baixa (só DDL) e um dossiê de quem já morou na casa:

  1. Estrutura ........ tabelas, colunas, tipos, PK/FK (PRAGMA)
  2. Volumetria ....... linhas por tabela (embutida na estrutura)
  3. Amostras ......... até N linhas reais por tabela
  4. Dicionário ....... TODOS os valores das colunas categóricas
                        (mata a Armadilha 2: domínios disjuntos de 'canal')
  5. Perfil temporal .. min/máx + formato por coluna de data, por CONTEÚDO
                        (mata a Sutileza 3: âncora temporal dos dados)
  6. Qualidade ........ detector genérico de denormalização
                        (mata a Armadilha 1 — módulo detector_denormalizacao)

Tudo é calculado DINAMICAMENTE contra qualquer SQLite (requisito de
descoberta do enunciado: nada de schema hardcoded) e cacheado por processo.
"""
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app.config import LIMITE_AMOSTRAS, LIMITE_CARDINALIDADE

# Padrões de data reconhecidos (detecção por CONTEÚDO, nunca pelo nome).
_PADROES_DE_DATA = [
    re.compile(r"^\d{4}-\d{2}-\d{2}"),      # ISO: 2025-07-22 (c/ ou s/ hora)
    re.compile(r"^\d{2}/\d{2}/\d{4}$"),     # 22/07/2025
    re.compile(r"^\d{2}-\d{2}-\d{4}$"),     # 22-07-2025
    re.compile(r"^\d{4}/\d{2}/\d{2}$"),     # 2025/07/22
]
_FRACAO_MINIMA_DE_DATAS = 0.8               # 80% da amostra precisa parecer data


@dataclass
class ColunaInfo:
    nome: str
    tipo: str                   # tipo declarado no DDL (TEXT, REAL, ...)
    e_pk: bool
    e_fk: bool
    fk_referencia: str | None   # "tabela.coluna" referenciada, se FK


@dataclass
class TabelaInfo:
    nome: str
    colunas: list               # list[ColunaInfo]
    n_linhas: int               # camada 2 (volumetria) embutida aqui


@dataclass
class AlertaQualidade:          # saída da camada 6 (preenchida pelo detector)
    tabela_pai: str
    coluna_pai: str
    tabela_filha: str
    coluna_filha: str
    agregado: str               # 'SUM' | 'MAX' | 'MIN'
    pct_divergencia: float      # fração de linhas do pai que divergem (0..1)
    mensagem: str               # texto pronto para o dossiê/trace


@dataclass
class PerfilDoBanco:
    estrutura: list                         # camadas 1+2: list[TabelaInfo]
    amostras: dict                          # camada 3: tabela → list[tuple]
    cabecalhos: dict                        # tabela → nomes de colunas
    dicionario_categorico: dict             # camada 4: tabela → coluna → [(valor, n)]
    perfil_temporal: dict                   # camada 5: "tabela.coluna" →
                                            #   {minimo, maximo, formatos}
    alertas_qualidade: list = field(default_factory=list)  # camada 6


# Cache por caminho de banco: o dossiê é calculado UMA vez por processo.
_CACHE_DE_PERFIS: dict = {}


def _eh_coluna_de_data(valores_amostra: list) -> bool:
    """Detecção por CONTEÚDO: True se a grande maioria da amostra (não-nula)
    casa com algum padrão de data conhecido. Genérico — nada de decidir pelo
    nome da coluna."""
    valores = [str(v) for v in valores_amostra if v is not None and str(v).strip()]
    if not valores:
        return False
    casam = sum(
        1 for v in valores if any(p.match(v) for p in _PADROES_DE_DATA)
    )
    return casam / len(valores) >= _FRACAO_MINIMA_DE_DATAS


def _levantar_estrutura(cur: sqlite3.Cursor) -> list:
    """Camadas 1+2: tabelas (ignora sqlite_*), colunas/tipos/PK via PRAGMA
    table_info, FKs via PRAGMA foreign_key_list, volumetria via COUNT(*)."""
    nomes = [
        nome for (nome,) in cur.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    estrutura = []
    for nome in nomes:
        # fk = (id, seq, tabela_pai, coluna_filha, coluna_pai, ...)
        fks = {
            fk[3]: f"{fk[2]}.{fk[4]}"
            for fk in cur.execute(f"PRAGMA foreign_key_list({nome})")
        }
        colunas = [
            ColunaInfo(
                nome=info[1],
                tipo=(info[2] or "").upper(),
                e_pk=bool(info[5]),
                e_fk=info[1] in fks,
                fk_referencia=fks.get(info[1]),
            )
            for info in cur.execute(f"PRAGMA table_info({nome})")
        ]
        n_linhas = cur.execute(f"SELECT COUNT(*) FROM {nome}").fetchone()[0]
        estrutura.append(TabelaInfo(nome=nome, colunas=colunas, n_linhas=n_linhas))
    return estrutura


def _coletar_amostras(
    cur: sqlite3.Cursor,
    estrutura: list,
    limite: int = LIMITE_AMOSTRAS,
) -> tuple:
    """Camada 3: até `limite` linhas por tabela + cabeçalhos."""
    amostras, cabecalhos = {}, {}
    for tabela in estrutura:
        cursor = cur.execute(f"SELECT * FROM {tabela.nome} LIMIT {limite}")
        cabecalhos[tabela.nome] = [d[0] for d in cursor.description]
        amostras[tabela.nome] = cursor.fetchall()
    return amostras, cabecalhos


def _montar_dicionario_categorico(
    cur: sqlite3.Cursor,
    estrutura: list,
    limite_cardinalidade: int = LIMITE_CARDINALIDADE,
) -> dict:
    """Camada 4: para colunas TEXT/BOOLEAN não-PK com nº de distintos ≤ limite,
    lista TODOS os valores com contagem. É a camada que mata a Armadilha 2
    (mesmo nome de coluna, domínios disjuntos entre tabelas)."""
    dicionario = {}
    for tabela in estrutura:
        for coluna in tabela.colunas:
            if coluna.e_pk or coluna.tipo not in {"TEXT", "BOOLEAN"}:
                continue
            distintos = cur.execute(
                f"SELECT COUNT(DISTINCT {coluna.nome}) FROM {tabela.nome}"
            ).fetchone()[0]
            if distintos > limite_cardinalidade:
                continue
            valores = cur.execute(
                f"SELECT {coluna.nome}, COUNT(*) FROM {tabela.nome} "
                f"GROUP BY {coluna.nome} ORDER BY COUNT(*) DESC"
            ).fetchall()
            dicionario.setdefault(tabela.nome, {})[coluna.nome] = valores
    return dicionario


def _perfilar_datas(cur: sqlite3.Cursor, estrutura: list) -> dict:
    """Camada 5: para colunas detectadas como data (por conteúdo), coleta
    {minimo, maximo, formatos} (formato = dígitos→'#'). É a camada que mata
    a Sutileza 3 (âncora temporal dos dados)."""
    perfil = {}
    for tabela in estrutura:
        for coluna in tabela.colunas:
            if coluna.tipo != "TEXT" or coluna.e_pk:
                continue
            amostra = [
                v for (v,) in cur.execute(
                    f"SELECT DISTINCT {coluna.nome} FROM {tabela.nome} LIMIT 50"
                )
            ]
            if not _eh_coluna_de_data(amostra):
                continue
            minimo, maximo = cur.execute(
                f"SELECT MIN({coluna.nome}), MAX({coluna.nome}) FROM {tabela.nome}"
            ).fetchone()
            formatos = sorted({re.sub(r"\d", "#", str(v)) for v in amostra})
            perfil[f"{tabela.nome}.{coluna.nome}"] = {
                "minimo": minimo, "maximo": maximo, "formatos": formatos,
            }
    return perfil


def perfilar(caminho_banco: Path, usar_cache: bool = True) -> PerfilDoBanco:
    """Orquestra as 6 camadas. Cache em memória por caminho de banco."""
    chave = str(Path(caminho_banco).resolve())
    if usar_cache and chave in _CACHE_DE_PERFIS:
        return _CACHE_DE_PERFIS[chave]

    con = sqlite3.connect(f"file:{caminho_banco}?mode=ro", uri=True)
    cur = con.cursor()
    estrutura = _levantar_estrutura(cur)
    amostras, cabecalhos = _coletar_amostras(cur, estrutura)
    dicionario = _montar_dicionario_categorico(cur, estrutura)
    temporal = _perfilar_datas(cur, estrutura)

    # Camada 6 — delegada ao módulo próprio (import tardio evita ciclo).
    from app.detector_denormalizacao import detectar
    alertas = detectar(cur, estrutura)
    con.close()

    perfil = PerfilDoBanco(
        estrutura=estrutura,
        amostras=amostras,
        cabecalhos=cabecalhos,
        dicionario_categorico=dicionario,
        perfil_temporal=temporal,
        alertas_qualidade=alertas,
    )
    if usar_cache:
        _CACHE_DE_PERFIS[chave] = perfil
    return perfil


def renderizar_para_prompt(perfil: PerfilDoBanco) -> str:
    """Converte o PerfilDoBanco no dossiê textual injetado nos prompts dos
    agentes: seções nomeadas, valores categóricos, âncora temporal explícita
    e alertas de qualidade em destaque."""
    partes = ["=== DOSSIÊ DO BANCO DE DADOS (gerado dinamicamente) ===", ""]

    partes.append("## ESTRUTURA E VOLUMETRIA")
    for tabela in perfil.estrutura:
        partes.append(f"Tabela {tabela.nome} ({tabela.n_linhas} linhas):")
        for c in tabela.colunas:
            marcas = []
            if c.e_pk:
                marcas.append("PK")
            if c.e_fk:
                marcas.append(f"FK→{c.fk_referencia}")
            sufixo = f" [{', '.join(marcas)}]" if marcas else ""
            partes.append(f"  - {c.nome} ({c.tipo}){sufixo}")
    partes.append("")

    partes.append("## AMOSTRAS (linhas reais)")
    for nome, linhas in perfil.amostras.items():
        partes.append(f"{nome}: colunas {perfil.cabecalhos[nome]}")
        for linha in linhas:
            partes.append(f"  {linha}")
    partes.append("")

    partes.append("## VALORES CATEGÓRICOS (use estes valores EXATOS nos filtros)")
    for nome_tabela, colunas in perfil.dicionario_categorico.items():
        for nome_coluna, valores in colunas.items():
            listagem = ", ".join(f"{v!r} ({n})" for v, n in valores)
            partes.append(f"{nome_tabela}.{nome_coluna}: {listagem}")
    partes.append("")

    partes.append("## JANELAS TEMPORAIS")
    maximos = []
    for chave, info in perfil.perfil_temporal.items():
        partes.append(
            f"{chave}: de {info['minimo']} a {info['maximo']} "
            f"(formato {info['formatos']})"
        )
        if info["maximo"]:
            maximos.append(str(info["maximo"]))
    if maximos:
        ancora = max(maximos)
        partes.append(
            f"ÂNCORA TEMPORAL: os dados terminam em {ancora}. Janelas relativas "
            f"('último ano', 'mês passado') devem ancorar em {ancora}, NUNCA na "
            "data de hoje. Meses sem ano: confira em quais anos o mês existe."
        )
    partes.append("")

    partes.append("## ALERTAS DE QUALIDADE DOS DADOS")
    if perfil.alertas_qualidade:
        for alerta in perfil.alertas_qualidade:
            partes.append(f"⚠ {alerta.mensagem}")
    else:
        partes.append("(nenhuma inconsistência detectada)")

    return "\n".join(partes)
