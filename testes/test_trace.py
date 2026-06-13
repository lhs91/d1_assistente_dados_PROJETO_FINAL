# -*- coding: utf-8 -*-
"""Testes do trace estruturado e dos tetos (Marco 2, microatividade 1)."""
import pytest

from app import config
from app.trace import EventoTrace, registrar, renderizar_trace

pytestmark = pytest.mark.marco2


def test_registrar_acrescenta_evento():
    """registrar() anexa EventoTrace com nó/tipo/conteúdo/dados corretos."""
    eventos = []
    registrar(eventos, "engenheiro", "sql_proposto", "SQL do passo 1",
              dados={"sql": "SELECT 1"}, tempo_ms=12.5)
    assert len(eventos) == 1
    evento = eventos[0]
    assert isinstance(evento, EventoTrace)
    assert (evento.no, evento.tipo) == ("engenheiro", "sql_proposto")
    assert evento.dados["sql"] == "SELECT 1"
    assert evento.tempo_ms == 12.5


def test_trace_preserva_ordem():
    """Eventos saem na ordem de registro (invariante do streaming do M4)."""
    eventos = []
    for indice in range(5):
        registrar(eventos, "no_x", "info", f"evento {indice}")
    assert [e.conteudo for e in eventos] == [f"evento {i}" for i in range(5)]


def test_renderizar_trace_contem_tentativas():
    """A renderização mostra o SQL antes/depois de uma correção, com motivo."""
    eventos = []
    registrar(eventos, "engenheiro", "sql_proposto", "tentativa 1",
              dados={"sql": "SELECT colx FROM t"})
    registrar(eventos, "executor", "sql_erro", "execução falhou",
              dados={"sql": "SELECT colx FROM t", "motivo": "no such column: colx"})
    registrar(eventos, "engenheiro", "sql_proposto", "tentativa 2 (corrigida)",
              dados={"sql": "SELECT col FROM t"})
    texto = renderizar_trace(eventos)
    assert "SELECT colx FROM t" in texto          # o antes
    assert "no such column" in texto              # o motivo
    assert "SELECT col FROM t" in texto           # o depois
    assert texto.index("colx") < texto.index("SELECT col FROM t")


def test_constantes_de_teto_presentes():
    """MAX_TENTATIVAS_SQL, MAX_DEVOLUCOES_AUDITOR e ORÇAMENTO definidos e coerentes."""
    assert config.MAX_TENTATIVAS_SQL >= 2          # ao menos 1 correção possível
    assert config.MAX_DEVOLUCOES_AUDITOR >= 1
    assert config.ORCAMENTO_GLOBAL_CHAMADAS_LLM > (
        config.MAX_TENTATIVAS_SQL + config.MAX_DEVOLUCOES_AUDITOR
    )


def test_pergunta_imprime_cinco_quebras_no_terminal(capsys):
    """V3.5: cada pergunta nova é precedida de 5 quebras de linha no
    terminal — separa visualmente as interações."""
    eventos = []
    registrar(eventos, "pergunta", "info", "Quantos pedidos?")
    saida = capsys.readouterr().out
    assert saida.startswith("\n\n\n\n\n")
    assert "[pergunta]" in saida and "Quantos pedidos?" in saida


def test_falha_graciosa_exibida_como_teto_estourado():
    """V3.6: o papel interno 'falha_graciosa' é EXIBIDO como 'teto
    estourado' no terminal e no trace técnico (ids internos estáveis)."""
    from app.cores import rotulo_do_no
    assert rotulo_do_no("falha_graciosa") == "teto estourado"
    eventos = []
    registrar(eventos, "falha_graciosa", "falha_graciosa", "Teto atingido.")
    texto_render = renderizar_trace(eventos)
    assert "[teto estourado]" in texto_render
    assert "[falha_graciosa]" not in texto_render


def test_redator_exibido_como_diretor():
    """V3.11: o papel interno 'redator' (id estável) é EXIBIDO como
    'diretor' no terminal e no trace; o nó do grafo não muda de id."""
    from app.cores import rotulo_do_no
    assert rotulo_do_no("redator") == "diretor"
    eventos = []
    registrar(eventos, "redator", "resposta", "Resposta final.")
    render = renderizar_trace(eventos)
    assert "[diretor]" in render
    assert "[redator]" not in render
