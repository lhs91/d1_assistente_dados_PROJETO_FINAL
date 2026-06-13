# -*- coding: utf-8 -*-
"""Testes do Guardrail SQL (Marco 1, microatividade 3).

O conjunto mais crítico do marco: a bateria maliciosa. Cada reprovação deve
vir com motivo claro (alimenta o trace e o loop de correção do M2).
"""
import pytest

from app.guardrail_sql import validar

pytestmark = pytest.mark.marco1


# ── O que DEVE passar ────────────────────────────────────────────────────────

def test_aprova_select_simples():
    veredito = validar("SELECT nome, estado FROM clientes")
    assert veredito.aprovado is True
    assert veredito.motivo is None


def test_aprova_select_com_join_group_by():
    sql = (
        "SELECT c.estado, COUNT(*) AS total "
        "FROM clientes c JOIN compras co ON co.cliente_id = c.id "
        "WHERE co.canal = 'App' GROUP BY c.estado ORDER BY total DESC LIMIT 5"
    )
    assert validar(sql).aprovado is True


def test_aprova_subquery():
    sql = (
        "SELECT nome FROM clientes "
        "WHERE id IN (SELECT cliente_id FROM compras WHERE valor > 1000)"
    )
    assert validar(sql).aprovado is True


def test_aprova_cte_with():
    sql = (
        "WITH gastos AS (SELECT cliente_id, SUM(valor) AS soma "
        "FROM compras GROUP BY cliente_id) "
        "SELECT c.nome, g.soma FROM clientes c JOIN gastos g ON g.cliente_id = c.id"
    )
    assert validar(sql).aprovado is True


def test_tolera_ponto_virgula_final():
    assert validar("SELECT 1;").aprovado is True


# ── O que DEVE ser barrado ───────────────────────────────────────────────────

@pytest.mark.parametrize(
    "sql_perigoso, comando",
    [
        ("DROP TABLE clientes", "DROP"),
        ("DELETE FROM clientes", "DELETE"),
        ("UPDATE clientes SET nome = 'x'", "UPDATE"),
        ("INSERT INTO clientes (nome) VALUES ('x')", "INSERT"),
        ("ALTER TABLE clientes ADD COLUMN x TEXT", "ALTER"),
        ("CREATE TABLE invasao (id INT)", "CREATE"),
    ],
)
def test_reprova_ddl_e_dml(sql_perigoso, comando):
    veredito = validar(sql_perigoso)
    assert veredito.aprovado is False
    assert comando in veredito.motivo or "SELECT" in veredito.motivo


def test_reprova_multi_statement():
    veredito = validar("SELECT 1; DROP TABLE clientes")
    assert veredito.aprovado is False
    assert "statement" in veredito.motivo.lower() or "UMA" in veredito.motivo


@pytest.mark.parametrize(
    "sql_perigoso",
    ["PRAGMA table_info(clientes)", "ATTACH DATABASE 'outro.db' AS outro"],
)
def test_reprova_pragma_e_attach(sql_perigoso):
    assert validar(sql_perigoso).aprovado is False


@pytest.mark.parametrize(
    "sql_disfarcado",
    [
        "SELECT 1 /* comentário */; DROP TABLE clientes",
        "SELECT 1 -- inofensivo\n; DROP TABLE clientes",
        "/* DROP escondido */ SELECT 1; DELETE FROM clientes",
    ],
)
def test_reprova_comando_escondido_em_comentario(sql_disfarcado):
    """Comentários são removidos ANTES da análise — não escondem comandos."""
    assert validar(sql_disfarcado).aprovado is False


def test_reprova_caixa_mista():
    assert validar("DrOp TaBlE clientes").aprovado is False
    assert validar("dElEtE FROM clientes").aprovado is False


def test_nao_reprova_substring_inocente():
    """'created_at' não dispara 'CREATE' — comparação por token, não substring.
    O falso positivo também é um risco (bloquearia consultas legítimas)."""
    sql = "SELECT created_at, updated_at, inserted_by FROM eventos"
    assert validar(sql).aprovado is True


@pytest.mark.parametrize("entrada_invalida", ["", "   ", None, 123, ["SELECT 1"]])
def test_reprova_vazio_e_nao_string(entrada_invalida):
    veredito = validar(entrada_invalida)
    assert veredito.aprovado is False
    assert veredito.motivo                      # sempre há explicação


def test_reprova_texto_que_nao_e_sql():
    veredito = validar("me mostre os clientes de São Paulo, por favor")
    assert veredito.aprovado is False
    assert "SELECT" in veredito.motivo
