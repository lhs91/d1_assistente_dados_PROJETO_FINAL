# -*- coding: utf-8 -*-
"""
ver_banco_d1.py — Inspetor do banco do Desafio 1 (anexo_desafio_1.db)

Visualiza o banco SQLite sem precisar instalar nada (DBeaver, DB Browser etc.):
estrutura, relacionamentos, volumetria, amostras, dicionário de valores
categóricos e as ARMADILHAS confirmadas empiricamente.

Uso (no PyCharm: botão direito no arquivo > Run; ou no terminal):
    python ver_banco_d1.py
    python ver_banco_d1.py caminho/para/outro_banco.db

Requisitos: nenhum além da biblioteca padrão do Python.
"""
import re
import sqlite3
import sys
from pathlib import Path

# Caminho padrão: o banco na mesma pasta deste script.
CAMINHO_PADRAO = Path(__file__).parent / "anexo_desafio_1.db"

LARGURA = 78  # largura das linhas separadoras

# Colunas categóricas: se uma coluna TEXT/BOOLEAN tiver até este número de
# valores distintos, listamos todos (vira o "dicionário de valores").
LIMITE_CARDINALIDADE = 25


def separador(titulo: str) -> None:
    """Imprime um cabeçalho de seção visualmente destacado."""
    print()
    print("=" * LARGURA)
    print(f"  {titulo}")
    print("=" * LARGURA)


def listar_tabelas(cur: sqlite3.Cursor) -> list[str]:
    """Retorna as tabelas de dados (ignora as internas do SQLite)."""
    linhas = cur.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [nome for (nome,) in linhas]


def mostrar_estrutura(cur: sqlite3.Cursor, tabelas: list[str]) -> None:
    """Mostra colunas, tipos, chave primária e total de linhas de cada tabela."""
    separador("1. ESTRUTURA DAS TABELAS")
    for tabela in tabelas:
        total = cur.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
        print(f"\n┌─ {tabela}  ({total} linhas)")
        for _, nome, tipo, nao_nulo, _, pk in cur.execute(f"PRAGMA table_info({tabela})"):
            marcas = []
            if pk:
                marcas.append("PK")
            if nao_nulo:
                marcas.append("NOT NULL")
            sufixo = f"  [{', '.join(marcas)}]" if marcas else ""
            print(f"│   {nome:<22} {tipo:<10}{sufixo}")
        print("└" + "─" * 40)


def mostrar_relacionamentos(cur: sqlite3.Cursor, tabelas: list[str]) -> None:
    """Lê as foreign keys declaradas (PRAGMA) e desenha o diagrama do banco."""
    separador("2. RELACIONAMENTOS (foreign keys declaradas no DDL)")
    relacoes = []  # (tabela_filha, coluna_filha, tabela_pai, coluna_pai)
    for tabela in tabelas:
        for fk in cur.execute(f"PRAGMA foreign_key_list({tabela})"):
            # fk = (id, seq, tabela_pai, coluna_filha, coluna_pai, ...)
            relacoes.append((tabela, fk[3], fk[2], fk[4]))

    if not relacoes:
        print("Nenhuma foreign key declarada.")
        return

    for filha, col_filha, pai, col_pai in relacoes:
        print(f"  {filha}.{col_filha}  ──(N:1)──▶  {pai}.{col_pai}")

    # Diagrama fixo do modelo estrela deste banco (1 cliente : N registros).
    print("""
  Diagrama (modelo estrela — clientes no centro):

                       ┌──────────────────────┐
                       │       clientes       │
                       │ id (PK)              │
                       │ nome, email, idade   │
                       │ cidade, estado       │
                       │ profissao, genero    │
                       │ valor_total_gasto  ⚠ │  ⚠ colunas extras
                       │ data_ultima_compra ⚠ │    (fora do enunciado
                       └──────────┬───────────┘     e DESATUALIZADAS)
                 ┌────────────────┼────────────────────┐
                 │ 1:N            │ 1:N                │ 1:N
       ┌─────────┴────────┐ ┌────┴────────────┐ ┌─────┴──────────────┐
       │     compras      │ │     suporte     │ │ campanhas_marketing│
       │ cliente_id (FK)  │ │ cliente_id (FK) │ │ cliente_id (FK)    │
       │ data_compra      │ │ data_contato    │ │ nome_campanha      │
       │ valor, categoria │ │ tipo_contato    │ │ data_envio         │
       │ canal ◀──────────┼─┼─ canal ◀────────┼─┼─ canal, interagiu  │
       └──────────────────┘ └─────────────────┘ └────────────────────┘
                 ▲ mesma palavra "canal", DOMÍNIOS DIFERENTES em cada tabela ▲
""")


def mostrar_amostras(cur: sqlite3.Cursor, tabelas: list[str], n: int = 5) -> None:
    """Mostra as primeiras N linhas de cada tabela, com nomes de colunas."""
    separador(f"3. AMOSTRAS ({n} primeiras linhas de cada tabela)")
    for tabela in tabelas:
        print(f"\n--- {tabela} ---")
        cursor = cur.execute(f"SELECT * FROM {tabela} LIMIT {n}")
        colunas = [d[0] for d in cursor.description]
        print("  " + " | ".join(colunas))
        for linha in cursor.fetchall():
            print("  " + " | ".join(str(v) for v in linha))


def mostrar_dicionario_categorico(cur: sqlite3.Cursor, tabelas: list[str]) -> None:
    """Lista todos os valores distintos das colunas de baixa cardinalidade."""
    separador("4. DICIONÁRIO DE VALORES (colunas categóricas)")
    print("(colunas com poucos valores distintos — é isto que o agente precisa")
    print(" conhecer para escrever filtros corretos, ex.: canal = 'App')\n")
    for tabela in tabelas:
        colunas = [
            (c[1], c[2]) for c in cur.execute(f"PRAGMA table_info({tabela})")
            if not c[5]  # ignora a PK
        ]
        for nome, tipo in colunas:
            distintos = cur.execute(
                f"SELECT COUNT(DISTINCT {nome}) FROM {tabela}"
            ).fetchone()[0]
            if distintos <= LIMITE_CARDINALIDADE and tipo.upper() in ("TEXT", "BOOLEAN"):
                valores = cur.execute(
                    f"SELECT {nome}, COUNT(*) FROM {tabela} "
                    f"GROUP BY {nome} ORDER BY COUNT(*) DESC"
                ).fetchall()
                lista = ", ".join(f"{v} ({q})" for v, q in valores)
                print(f"  {tabela}.{nome}: {lista}")


def mostrar_janelas_de_data(cur: sqlite3.Cursor) -> None:
    """Mostra o intervalo coberto por cada coluna de data e o formato real."""
    separador("5. JANELAS TEMPORAIS (mín/máx e formato real das datas)")
    colunas_data = [
        ("compras", "data_compra"),
        ("suporte", "data_contato"),
        ("campanhas_marketing", "data_envio"),
        ("clientes", "data_ultima_compra"),
    ]
    for tabela, coluna in colunas_data:
        minimo, maximo = cur.execute(
            f"SELECT MIN({coluna}), MAX({coluna}) FROM {tabela}"
        ).fetchone()
        # Reduz cada valor a um padrão (dígito -> #) para revelar o formato.
        padroes = set()
        for (valor,) in cur.execute(f"SELECT DISTINCT {coluna} FROM {tabela}"):
            padroes.add(re.sub(r"\d", "#", str(valor)))
        print(f"  {tabela}.{coluna}: {minimo} → {maximo}   formato(s): {sorted(padroes)}")
    print("\n  ⚠ Sutileza 3: os dados terminam em jul/2025. Perguntas como 'último")
    print("    ano' devem ancorar no MAX(data) do banco, não na data de hoje.")
    print("    E 'maio' só existe em 2025 — verificável, não precisa chutar.")


def mostrar_armadilhas(cur: sqlite3.Cursor) -> None:
    """Verifica empiricamente as armadilhas conhecidas do banco."""
    separador("6. ARMADILHAS (verificação empírica, não opinião)")

    # Armadilha 1: colunas denormalizadas de clientes mentem.
    divergentes_valor = cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT c.id
            FROM clientes c LEFT JOIN compras co ON co.cliente_id = c.id
            GROUP BY c.id
            HAVING ABS(c.valor_total_gasto - COALESCE(SUM(co.valor), 0)) > 0.01
        )
    """).fetchone()[0]
    divergentes_data = cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT c.id
            FROM clientes c LEFT JOIN compras co ON co.cliente_id = c.id
            GROUP BY c.id
            HAVING c.data_ultima_compra != COALESCE(MAX(co.data_compra), '')
        )
    """).fetchone()[0]
    total = cur.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    print(f"\n  ⚠ ARMADILHA 1 — colunas extras de clientes (fora do enunciado):")
    print(f"    clientes.valor_total_gasto  ≠ SUM(compras.valor)   em {divergentes_valor}/{total} clientes")
    print(f"    clientes.data_ultima_compra ≠ MAX(data_compra)     em {divergentes_data}/{total} clientes")
    print("    → São atalhos DESATUALIZADOS. A fonte confiável é a tabela compras.")

    # Armadilha 2: "canal" tem domínio diferente em cada tabela.
    print("\n  ⚠ ARMADILHA 2 — a coluna 'canal' significa 3 coisas diferentes:")
    for tabela in ("compras", "suporte", "campanhas_marketing"):
        valores = [v for (v,) in cur.execute(f"SELECT DISTINCT canal FROM {tabela} ORDER BY canal")]
        print(f"    {tabela}.canal = {valores}")
    print("    → 'comprou via app' usa compras.canal; 'campanha de WhatsApp' usa")
    print("      campanhas_marketing.canal; 'reclamações por canal' usa suporte.canal.")

    # Clientes sem registros em alguma tabela-filha (cuidado com INNER JOIN).
    print("\n  ℹ Cobertura (clientes sem registros — atenção a INNER vs LEFT JOIN):")
    for tabela in ("compras", "suporte", "campanhas_marketing"):
        sem = cur.execute(
            f"SELECT COUNT(*) FROM clientes "
            f"WHERE id NOT IN (SELECT DISTINCT cliente_id FROM {tabela})"
        ).fetchone()[0]
        print(f"    clientes sem registro em {tabela}: {sem}")


def principal() -> None:
    """Ponto de entrada: abre o banco em modo somente-leitura e inspeciona."""
    caminho = Path(sys.argv[1]) if len(sys.argv) > 1 else CAMINHO_PADRAO
    if not caminho.exists():
        print(f"[ERRO] Banco não encontrado: {caminho}")
        print("Coloque o anexo_desafio_1.db na mesma pasta deste script,")
        print("ou informe o caminho: python ver_banco_d1.py caminho/banco.db")
        sys.exit(1)

    # mode=ro garante que a inspeção JAMAIS altera o banco.
    conexao = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    cursor = conexao.cursor()

    print("#" * LARGURA)
    print(f"#  INSPEÇÃO DO BANCO: {caminho.name}  (aberto em modo SOMENTE-LEITURA)")
    print("#" * LARGURA)

    tabelas = listar_tabelas(cursor)
    mostrar_estrutura(cursor, tabelas)
    mostrar_relacionamentos(cursor, tabelas)
    mostrar_amostras(cursor, tabelas)
    mostrar_dicionario_categorico(cursor, tabelas)
    mostrar_janelas_de_data(cursor)
    mostrar_armadilhas(cursor)

    conexao.close()
    print("\n[FIM] Inspeção concluída. Nada foi modificado no banco.")


if __name__ == "__main__":
    principal()
