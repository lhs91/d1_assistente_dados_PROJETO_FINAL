# -*- coding: utf-8 -*-
"""Testes do detector de denormalização — camada 6 (Marco 1, microatividade 6).

A prova material do "mecanismo, não regra decorada": as armadilhas do banco
SINTÉTICO (nomes diferentes do real) são detectadas; o par CONSISTENTE não é
flagado; e os nomes das colunas do banco REAL não existem no código de
produção (verificado por varredura dos fontes).
"""
import re
import sqlite3
from pathlib import Path

import pytest

from app.detector_denormalizacao import detectar
from app.perfilador import _levantar_estrutura

pytestmark = pytest.mark.marco1


def _detectar_em(caminho_banco, limiar=None):
    con = sqlite3.connect(f"file:{caminho_banco}?mode=ro", uri=True)
    cur = con.cursor()
    estrutura = _levantar_estrutura(cur)
    alertas = detectar(cur, estrutura) if limiar is None else detectar(
        cur, estrutura, limiar=limiar
    )
    con.close()
    return alertas


def test_detecta_par_numerico_divergente(banco_sintetico):
    """total_calculado ≠ SUM(itens.preco) em 8/20 pedidos → 40% detectado."""
    alertas = _detectar_em(banco_sintetico)
    alvo = [a for a in alertas if a.coluna_pai == "total_calculado"]
    assert len(alvo) == 1
    assert alvo[0].agregado == "SUM"
    assert alvo[0].coluna_filha == "preco"
    assert alvo[0].pct_divergencia == pytest.approx(0.40)
    assert "fonte transacional" in alvo[0].mensagem


def test_detecta_par_data_divergente(banco_sintetico):
    """data_recente ≠ MAX(itens.data_item) em 6/20 pedidos → 30% detectado."""
    alertas = _detectar_em(banco_sintetico)
    alvo = [a for a in alertas if a.coluna_pai == "data_recente"]
    assert len(alvo) == 1
    assert alvo[0].agregado == "MAX"
    assert alvo[0].coluna_filha == "data_item"
    assert alvo[0].pct_divergencia == pytest.approx(0.30)


def test_nao_flagra_par_consistente(banco_sintetico):
    """total_confirmado == SUM(itens.preco) em TODAS as linhas → NENHUM alerta.
    O falso positivo é o risco mais vergonhoso do detector."""
    alertas = _detectar_em(banco_sintetico)
    assert all(a.coluna_pai != "total_confirmado" for a in alertas)


def test_ignora_coluna_sem_par(banco_sintetico):
    """observacao (sem token de agregado, não-data) é ignorada sem erro;
    origem (sem token) idem."""
    alertas = _detectar_em(banco_sintetico)
    colunas_flagadas = {a.coluna_pai for a in alertas}
    assert "observacao" not in colunas_flagadas
    assert "origem" not in colunas_flagadas
    # Só as duas armadilhas plantadas:
    assert colunas_flagadas == {"total_calculado", "data_recente"}


def test_respeita_limiar(banco_sintetico):
    """Divergência de 40%/30%: com limiar 0.5 nada alerta; com 0.05 alerta."""
    assert _detectar_em(banco_sintetico, limiar=0.5) == []
    assert len(_detectar_em(banco_sintetico, limiar=0.05)) == 2


def test_banco_real_flagra_armadilha_1_sem_regra_decorada(banco_real):
    """Contra o banco REAL, o detector flagra exatamente as duas colunas da
    Armadilha 1 — e a varredura dos fontes confirma que esses nomes só
    existem aqui no teste, nunca no código de produção."""
    alertas = _detectar_em(banco_real)
    flagadas = {(a.tabela_pai, a.coluna_pai, a.agregado) for a in alertas}
    assert ("clientes", "valor_total_gasto", "SUM") in flagadas
    assert ("clientes", "data_ultima_compra", "MAX") in flagadas
    # Divergência total (100%) nos pares canônicos com `compras` — confirmada
    # empiricamente na análise prévia. (O mecanismo também pareia com as
    # outras filhas de clientes — suporte e campanhas —, o que é correto:
    # alertas são consultivos e listam todos os candidatos divergentes.)
    for alerta in alertas:
        if (
            alerta.coluna_pai in {"valor_total_gasto", "data_ultima_compra"}
            and alerta.tabela_filha == "compras"
        ):
            assert alerta.pct_divergencia == pytest.approx(1.0)

    # Prova anti-overfitting: nenhum fonte de produção cita esses nomes.
    pasta_app = Path(__file__).resolve().parent.parent / "app"
    fontes = "\n".join(
        arquivo.read_text(encoding="utf-8")
        for arquivo in pasta_app.rglob("*.py")
    )
    assert not re.search(r"valor_total_gasto|data_ultima_compra", fontes)
