# -*- coding: utf-8 -*-
"""Testes do Executor Somente-Leitura (Marco 1, microatividade 2).

Risco central testado: a garantia FÍSICA do somente-leitura. Os testes de
escrita chamam o Executor DIRETO, sem passar pelo Guardrail — provando que a
segurança não depende da barreira lógica (defesa em profundidade).
"""
import sqlite3
from pathlib import Path

import pytest

from app.executor import ErroDeBanco, executar

pytestmark = pytest.mark.marco1


@pytest.fixture
def banco_simples(tmp_path: Path) -> Path:
    """Banco mínimo e controlado para os testes do Executor."""
    caminho = tmp_path / "simples.db"
    con = sqlite3.connect(caminho)
    con.execute("CREATE TABLE itens (id INTEGER PRIMARY KEY, nome TEXT)")
    con.executemany(
        "INSERT INTO itens (nome) VALUES (?)",
        [(f"item_{i}",) for i in range(10)],
    )
    con.commit()
    con.close()
    return caminho


def _contar_itens(caminho: Path) -> int:
    """Contagem independente, para provar que nada foi escrito."""
    con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    total = con.execute("SELECT COUNT(*) FROM itens").fetchone()[0]
    con.close()
    return total


def test_select_valido_retorna_dados(banco_simples):
    resultado = executar("SELECT id, nome FROM itens ORDER BY id", banco_simples)
    assert resultado.erro is None
    assert resultado.colunas == ["id", "nome"]
    assert resultado.n_linhas == 10
    assert resultado.linhas[0] == (1, "item_0")
    assert resultado.truncado is False
    assert resultado.tempo_ms > 0


def test_insert_falha_fisicamente(banco_simples):
    """INSERT direto no Executor (sem Guardrail) falha pelo mode=ro."""
    resultado = executar("INSERT INTO itens (nome) VALUES ('intruso')", banco_simples)
    assert resultado.erro is not None            # o SQLite recusou
    assert _contar_itens(banco_simples) == 10    # nada foi escrito


@pytest.mark.parametrize(
    "sql_de_escrita",
    [
        "UPDATE itens SET nome = 'x' WHERE id = 1",
        "DELETE FROM itens",
        "DROP TABLE itens",
    ],
)
def test_update_delete_drop_falham_fisicamente(banco_simples, sql_de_escrita):
    resultado = executar(sql_de_escrita, banco_simples)
    assert resultado.erro is not None
    assert _contar_itens(banco_simples) == 10    # banco intacto


def test_erro_sql_vira_campo_erro_nao_excecao(banco_simples):
    """SQL inválido NÃO levanta exceção: vira `erro` (combustível do M2)."""
    resultado = executar("SELECT inexistente FROM tabela_fantasma", banco_simples)
    assert resultado.erro is not None
    assert "tabela_fantasma" in resultado.erro
    assert resultado.n_linhas == 0


def test_sem_truncamento_devolve_todas_as_linhas(banco_simples):
    """V3.6 (decisão do dev): o truncamento foi REMOVIDO — o executor
    devolve TODAS as linhas do resultado, sem corte de dados, e o gráfico
    recebe o conjunto completo."""
    resultado = executar("SELECT id FROM itens", banco_simples)
    assert resultado.truncado is False
    assert resultado.n_linhas == len(resultado.linhas)
    assert resultado.n_linhas >= 5            # o banco simples tem 5+ itens
    # e a assinatura nova não aceita mais teto:
    import inspect
    from app.executor import executar as funcao
    assert "max_linhas" not in inspect.signature(funcao).parameters


def test_resultado_vazio_e_valido(banco_simples):
    """0 linhas é SUCESSO — não confundir vazio com falha."""
    resultado = executar("SELECT * FROM itens WHERE id > 999", banco_simples)
    assert resultado.erro is None
    assert resultado.n_linhas == 0
    assert resultado.colunas == ["id", "nome"]   # estrutura preservada


def test_banco_inexistente_erro_claro(tmp_path):
    """Caminho inexistente: ErroDeBanco claro e NENHUM arquivo criado."""
    caminho_fantasma = tmp_path / "nao_existe.db"
    with pytest.raises(ErroDeBanco) as excecao:
        executar("SELECT 1", caminho_fantasma)
    assert "não encontrado" in str(excecao.value)
    assert not caminho_fantasma.exists()         # mode=ro não cria arquivo
