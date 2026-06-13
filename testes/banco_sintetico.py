# -*- coding: utf-8 -*-
"""
banco_sintetico.py — Banco SQLite de teste com armadilhas PLANTADAS.

É a prova material de que o detector de denormalização é um MECANISMO
genérico, e não uma regra decorada do banco real: as armadilhas aqui têm
outros nomes, outras tabelas e proporções controladas.

Armadilhas plantadas (controladas linha a linha):
- pedidos.total_calculado  diverge de SUM(itens.preco)    em 8 de 20 pedidos (40%).
- pedidos.data_recente     diverge de MAX(itens.data_item) em 6 de 20 pedidos (30%).
- pedidos.total_confirmado é CONSISTENTE com SUM(itens.preco) (não pode ser flagado).
- itens.codigo tem 30 valores distintos (acima do limite do dicionário categórico).
- pedidos.origem e itens.origem: mesma palavra, domínios DISJUNTOS (eco da Armadilha 2).
- pedidos.observacao: TEXT comum (não-data, sem par) — deve ser ignorada.
- Datas como TEXT em ISO (a detecção de data é por CONTEÚDO).
"""
import sqlite3
from pathlib import Path

N_PEDIDOS = 20
ITENS_POR_PEDIDO = 3
PRECO_ITEM = 10.0                      # cada item custa 10.00 → soma real = 30.00
PEDIDOS_COM_TOTAL_DIVERGENTE = 8       # 8/20 = 40% de divergência numérica
PEDIDOS_COM_DATA_DIVERGENTE = 6        # 6/20 = 30% de divergência de data


def criar_banco_sintetico(caminho: Path) -> Path:
    """Cria o banco sintético no caminho dado e o retorna."""
    con = sqlite3.connect(caminho)
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            total_calculado REAL,      -- ARMADILHA: diverge em parte das linhas
            total_confirmado REAL,     -- CONSISTENTE: não pode ser flagado
            data_recente TEXT,         -- ARMADILHA: diverge de MAX(data_item)
            origem TEXT,               -- domínio: Loja | Telefone
            observacao TEXT            -- texto comum, sem par, não-data
        );
        CREATE TABLE itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER,
            preco REAL,
            data_item TEXT,            -- datas ISO como TEXT
            codigo TEXT,               -- 30 distintos (> limite do dicionário)
            origem TEXT,               -- domínio: Web | App  (DISJUNTO do pai)
            FOREIGN KEY (pedido_id) REFERENCES pedidos(id)
        );
        """
    )

    soma_real = PRECO_ITEM * ITENS_POR_PEDIDO  # 30.00 por pedido
    for numero in range(1, N_PEDIDOS + 1):
        # Datas dos itens do pedido: dias 10, 11 e 12 do mês.
        datas_itens = [f"2025-03-1{d}" for d in range(ITENS_POR_PEDIDO)]
        max_data_real = max(datas_itens)

        total_diverge = numero <= PEDIDOS_COM_TOTAL_DIVERGENTE
        data_diverge = numero <= PEDIDOS_COM_DATA_DIVERGENTE

        cur.execute(
            "INSERT INTO pedidos (total_calculado, total_confirmado, "
            "data_recente, origem, observacao) VALUES (?, ?, ?, ?, ?)",
            (
                soma_real + 99.99 if total_diverge else soma_real,
                soma_real,                                   # sempre consistente
                "2024-01-01" if data_diverge else max_data_real,
                "Loja" if numero % 2 == 0 else "Telefone",
                f"observação livre do pedido {numero}",
            ),
        )
        pedido_id = cur.lastrowid
        for indice, data_item in enumerate(datas_itens):
            cur.execute(
                "INSERT INTO itens (pedido_id, preco, data_item, codigo, origem) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    pedido_id,
                    PRECO_ITEM,
                    data_item,
                    f"COD-{pedido_id:03d}-{indice}",   # alta cardinalidade
                    "Web" if indice % 2 == 0 else "App",
                ),
            )

    con.commit()
    con.close()
    return caminho
