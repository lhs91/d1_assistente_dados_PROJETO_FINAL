# -*- coding: utf-8 -*-
"""Testes do grafo multiagêntico (Marco 2, microatividade 6). Gemini mockado;
Guardrail, Executor e Perfilador são os REAIS, contra o banco sintético."""
import sqlite3

import pytest

from app.config import MAX_DEVOLUCOES_AUDITOR, MAX_TENTATIVAS_SQL
from app.estado import (
    AnaliseDaPergunta,
    ParecerDoAuditor,
    PassoDoPlano,
    RespostaDeNegocio,
    SqlDoPasso,
)
from app.principal import responder_pergunta
from testes.llm_falso import LlmRoteirizado

pytestmark = pytest.mark.marco2


# ── Blocos de roteiro reutilizáveis ──────────────────────────────────────────

def _analise(n_passos=1, premissas=None):
    return AnaliseDaPergunta(
        precisa_esclarecimento=False,
        premissas=premissas or [],
        passos=[PassoDoPlano(objetivo=f"objetivo do passo {i + 1}")
                for i in range(n_passos)],
    )


def _analise_ambigua(pergunta_escl="Vendas ou suporte?"):
    return AnaliseDaPergunta(
        precisa_esclarecimento=True,
        pergunta_de_esclarecimento=pergunta_escl,
        passos=[],
    )


SQL_OK = SqlDoPasso(sql="SELECT COUNT(*) AS total FROM pedidos", justificativa="conta")
SQL_OK_2 = SqlDoPasso(sql="SELECT COUNT(*) AS itens FROM itens", justificativa="conta itens")
SQL_INVALIDO = SqlDoPasso(sql="SELECT col_fantasma FROM tabela_fantasma", justificativa="errada")
SQL_MALICIOSO = SqlDoPasso(sql="DROP TABLE pedidos", justificativa="ataque")
SQL_VAZIO = SqlDoPasso(sql="SELECT * FROM pedidos WHERE id > 9999", justificativa="vazio")
APROVADO = ParecerDoAuditor(aprovado=True)
RESPOSTA = RespostaDeNegocio(resposta="Há 20 pedidos.", premissas_destacadas=[])


def _nos_do_trace(trace):
    return [evento.no for evento in trace]


# ── Caminhos felizes ─────────────────────────────────────────────────────────

def test_caminho_feliz_um_passo(banco_sintetico):
    """Plano de 1 passo com SQL correto: resposta final + trace de todos os nós."""
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(1)],
        SqlDoPasso: [SQL_OK],
        ParecerDoAuditor: [APROVADO],
        RespostaDeNegocio: [RESPOSTA],
    })
    saida = responder_pergunta("Quantos pedidos?", banco_sintetico, llm=llm)
    assert saida["resposta"] == "Há 20 pedidos."
    assert saida["falha_graciosa"] is None
    assert saida["resultados"][0]["linhas"] == [(20,)]   # executor REAL
    nos = _nos_do_trace(saida["trace"])
    for no in ["perfilador", "analista", "engenheiro", "guardrail",
               "executor", "auditor", "redator"]:
        assert no in nos, f"nó {no} não registrou evento no trace"


def test_caminho_feliz_multi_passo(banco_sintetico):
    """Plano de 2 passos: ambos executam em ordem e chegam ao redator."""
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(2)],
        SqlDoPasso: [SQL_OK, SQL_OK_2],
        ParecerDoAuditor: [APROVADO],
        RespostaDeNegocio: [RESPOSTA],
    })
    saida = responder_pergunta("Pedidos e itens?", banco_sintetico, llm=llm)
    assert saida["falha_graciosa"] is None
    assert len(saida["resultados"]) == 2
    assert saida["resultados"][0]["linhas"] == [(20,)]
    assert saida["resultados"][1]["linhas"] == [(60,)]
    # O prompt do 2º passo recebeu o resultado do 1º (contexto multi-passo):
    prompt_do_passo_2 = llm.prompts_por_schema[SqlDoPasso][1]
    assert "(20,)" in prompt_do_passo_2


# ── Loop sintático (nível 1) ─────────────────────────────────────────────────

def test_loop_sintatico_converge(banco_sintetico):
    """Mock erra 2 vezes e acerta na 3ª: resposta final + 3 tentativas no trace."""
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(1)],
        SqlDoPasso: [SQL_INVALIDO, SQL_INVALIDO, SQL_OK],
        ParecerDoAuditor: [APROVADO],
        RespostaDeNegocio: [RESPOSTA],
    })
    saida = responder_pergunta("Quantos pedidos?", banco_sintetico, llm=llm)
    assert saida["falha_graciosa"] is None
    assert saida["resultados"][0]["tentativas"] == 3
    erros = [e for e in saida["trace"] if e.tipo == "sql_erro"]
    assert len(erros) == 2
    assert "tabela_fantasma" in erros[0].dados["motivo"]
    # O prompt da correção continha o erro anterior:
    prompt_da_2a = llm.prompts_por_schema[SqlDoPasso][1]
    assert "tabela_fantasma" in prompt_da_2a


def test_loop_sintatico_respeita_teto(banco_sintetico):
    """Mock erra sempre: após MAX_TENTATIVAS_SQL, falha graciosa sem exceção."""
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(1)],
        SqlDoPasso: [SQL_INVALIDO] * MAX_TENTATIVAS_SQL,
    })
    saida = responder_pergunta("Quantos pedidos?", banco_sintetico, llm=llm)
    assert saida["resposta"] is None
    assert saida["falha_graciosa"] is not None
    assert str(MAX_TENTATIVAS_SQL) in saida["falha_graciosa"]
    assert "tabela_fantasma" in saida["falha_graciosa"]      # explica o último erro


def test_guardrail_reprovacao_alimenta_loop(banco_sintetico):
    """DROP TABLE do mock: Guardrail reprova, o motivo realimenta, o mock
    corrige e o banco segue intacto."""
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(1)],
        SqlDoPasso: [SQL_MALICIOSO, SQL_OK],
        ParecerDoAuditor: [APROVADO],
        RespostaDeNegocio: [RESPOSTA],
    })
    saida = responder_pergunta("Quantos pedidos?", banco_sintetico, llm=llm)
    assert saida["falha_graciosa"] is None
    reprovacoes = [e for e in saida["trace"] if e.tipo == "sql_reprovado"]
    assert len(reprovacoes) == 1
    # O motivo do Guardrail chegou ao prompt da correção:
    prompt_da_correcao = llm.prompts_por_schema[SqlDoPasso][1]
    assert "Guardrail" in prompt_da_correcao
    # Banco intacto (o DROP jamais chegou ao Executor):
    con = sqlite3.connect(f"file:{banco_sintetico}?mode=ro", uri=True)
    assert con.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0] == 20
    con.close()


# ── Devolução do Auditor (nível 2) ───────────────────────────────────────────

def test_devolucao_do_auditor_regenera(banco_sintetico):
    """Auditor reprova com instrução: o passo é regenerado e depois aprovado."""
    reprovacao = ParecerDoAuditor(
        aprovado=False,
        problema="consulta não usa a fonte transacional",
        instrucao_de_correcao="some os preços da tabela itens",
        indice_passo_a_refazer=0,
    )
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(1)],
        SqlDoPasso: [SQL_OK, SQL_OK_2],
        ParecerDoAuditor: [reprovacao, APROVADO],
        RespostaDeNegocio: [RESPOSTA],
    })
    saida = responder_pergunta("Total gasto?", banco_sintetico, llm=llm)
    assert saida["falha_graciosa"] is None
    devolucoes = [e for e in saida["trace"] if e.tipo == "devolucao"]
    assert len(devolucoes) == 1
    # A instrução do Auditor chegou ao prompt da regeneração:
    prompt_regenerado = llm.prompts_por_schema[SqlDoPasso][1]
    assert "some os preços da tabela itens" in prompt_regenerado
    # O resultado final é o da consulta regenerada:
    assert saida["resultados"][0]["sql"] == SQL_OK_2.sql


def test_devolucao_respeita_teto(banco_sintetico):
    """Auditor reprova sempre: após MAX_DEVOLUCOES_AUDITOR, falha graciosa."""
    reprovacao = ParecerDoAuditor(
        aprovado=False, problema="errado",
        instrucao_de_correcao="refaça", indice_passo_a_refazer=0,
    )
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(1)],
        # SQLs DIFERENTES a cada correção: devolução legítima (o detector de
        # ciclo improdutivo da V3.3 corta correções que REPETEM o SQL).
        SqlDoPasso: [
            SqlDoPasso(sql=f"SELECT COUNT(*) AS total{i} FROM pedidos",
                       justificativa=f"v{i}")
            for i in range(MAX_DEVOLUCOES_AUDITOR + 2)
        ],
        ParecerDoAuditor: [reprovacao] * (MAX_DEVOLUCOES_AUDITOR + 1),
    })
    saida = responder_pergunta("Total gasto?", banco_sintetico, llm=llm)
    assert saida["resposta"] is None
    assert saida["falha_graciosa"] is not None
    assert "refaça" in saida["falha_graciosa"]               # explica a última instrução


# ── Interrupt (ambiguidade material) ─────────────────────────────────────────

def test_interrupt_pausa_e_retoma(banco_sintetico):
    """Ambiguidade material: o grafo PAUSA, o usuário responde, o plano é
    refeito com a premissa e o fluxo conclui."""
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [
            _analise_ambigua("Desempenho de quê: pedidos ou itens?"),
            _analise(1, premissas=["usuário escolheu pedidos"]),
        ],
        SqlDoPasso: [SQL_OK],
        ParecerDoAuditor: [APROVADO],
        RespostaDeNegocio: [RESPOSTA],
    })
    perguntas_recebidas = []

    def responder_interrupt(pergunta_de_esclarecimento):
        perguntas_recebidas.append(pergunta_de_esclarecimento)
        return "quero pedidos"

    saida = responder_pergunta(
        "Como foi o desempenho?", banco_sintetico,
        llm=llm, responder_interrupt=responder_interrupt,
    )
    assert perguntas_recebidas == ["Desempenho de quê: pedidos ou itens?"]
    assert saida["falha_graciosa"] is None
    assert saida["resposta"] == "Há 20 pedidos."
    # A resposta do usuário chegou ao prompt da 2ª análise:
    prompt_da_2a_analise = llm.prompts_por_schema[AnaliseDaPergunta][1]
    assert "quero pedidos" in prompt_da_2a_analise
    # E o trace registrou a interrupção:
    assert any(e.tipo == "interrupcao" for e in saida["trace"])


def test_responder_interrupt_ausente_gera_erro_claro(banco_sintetico):
    """Sem responder_interrupt, um pedido de esclarecimento vira RuntimeError claro."""
    llm = LlmRoteirizado({AnaliseDaPergunta: [_analise_ambigua()]})
    with pytest.raises(RuntimeError) as excecao:
        responder_pergunta("Como foi?", banco_sintetico, llm=llm)
    assert "esclarecimento" in str(excecao.value)


# ── Orçamento global e honestidade ───────────────────────────────────────────

def test_orcamento_global_para_tudo(banco_sintetico):
    """Roteiro patológico (analista↔esclarecimento em loop): o orçamento corta
    com falha graciosa antes de esgotar o roteiro do mock."""
    muitas_analises_ambiguas = [_analise_ambigua(f"dúvida {i}") for i in range(30)]
    llm = LlmRoteirizado({AnaliseDaPergunta: muitas_analises_ambiguas})
    saida = responder_pergunta(
        "Como foi?", banco_sintetico, llm=llm,
        responder_interrupt=lambda p: "tanto faz",
    )
    assert saida["falha_graciosa"] is not None
    from app.config import ORCAMENTO_GLOBAL_CHAMADAS_LLM
    assert llm.total_de_chamadas <= ORCAMENTO_GLOBAL_CHAMADAS_LLM + 1


def test_pergunta_impossivel_resposta_honesta(banco_sintetico):
    """Resultado vazio legítimo: o Auditor aprova e a resposta diz que não há dados."""
    honesta = RespostaDeNegocio(
        resposta="Não há dados no período para responder.", premissas_destacadas=[]
    )
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(1)],
        SqlDoPasso: [SQL_VAZIO],
        ParecerDoAuditor: [APROVADO],
        RespostaDeNegocio: [honesta],
    })
    saida = responder_pergunta("Qual o lucro?", banco_sintetico, llm=llm)
    assert saida["resultados"][0]["n_linhas"] == 0
    assert "Não há dados" in saida["resposta"]
    # O redator viu o resultado vazio (não recebeu números para inventar):
    prompt_do_redator = llm.prompts_por_schema[RespostaDeNegocio][0]
    assert "Linhas (0)" in prompt_do_redator


def test_resultado_completo_chega_sem_corte(banco_sintetico):
    """V3.6 (truncamento REMOVIDO): o resultado chega COMPLETO ao estado —
    n_linhas é o total real da tabela e truncado é sempre False."""
    sql_largo = SqlDoPasso(sql="SELECT id FROM itens", justificativa="lista tudo")
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(1)],
        SqlDoPasso: [sql_largo],
        ParecerDoAuditor: [APROVADO],
        RespostaDeNegocio: [RESPOSTA],
    })
    saida = responder_pergunta("Liste os itens", banco_sintetico, llm=llm)
    resultado = saida["resultados"][0]
    import sqlite3
    con = sqlite3.connect(banco_sintetico)
    total_real = con.execute("SELECT COUNT(*) FROM itens").fetchone()[0]
    con.close()
    assert resultado["truncado"] is False
    assert resultado["n_linhas"] == total_real
    assert len(resultado["linhas"]) == total_real


def test_estado_final_carrega_trace_integro(banco_sintetico):
    """Estado final: trace em ordem cronológica coerente e orçamento contabilizado."""
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(1)],
        SqlDoPasso: [SQL_OK],
        ParecerDoAuditor: [APROVADO],
        RespostaDeNegocio: [RESPOSTA],
    })
    saida = responder_pergunta("Quantos pedidos?", banco_sintetico, llm=llm)
    nos = _nos_do_trace(saida["trace"])
    assert nos.index("perfilador") < nos.index("analista") < nos.index("engenheiro")
    assert nos.index("engenheiro") < nos.index("executor") < nos.index("auditor")
    assert nos.index("auditor") < nos.index("redator")
    assert saida["chamadas_llm"] == 4        # analista + engenheiro + auditor + redator


# ── Motor headless (CLI sem UI) ──────────────────────────────────────────────

def test_responder_pergunta_headless(banco_sintetico):
    """O motor devolve o dict completo (resposta, premissas, trace) sem UI alguma."""
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(1, premissas=["premissa x"])],
        SqlDoPasso: [SQL_OK],
        ParecerDoAuditor: [APROVADO],
        RespostaDeNegocio: [RespostaDeNegocio(
            resposta="Há 20 pedidos.", premissas_destacadas=["premissa x"])],
    })
    saida = responder_pergunta("Quantos pedidos?", banco_sintetico, llm=llm)
    assert set(saida) == {"pergunta", "resposta", "premissas",
                          "impactos_e_acoes", "falha_graciosa",
                          "resultados", "trace", "chamadas_llm",
                          "especificacao_visual"}
    assert saida["premissas"] == ["premissa x"]


def test_grafo_resolve_criar_llm_no_caminho_de_producao():
    """Regressão V3.4 (NameError no Studio): construir_grafo(llm=None) é o
    caminho do studio.py/produção e depende de criar_llm estar IMPORTADO no
    namespace do grafo — os demais testes injetam mock e nunca o exercitam."""
    import app.grafo as modulo
    assert hasattr(modulo, "criar_llm")
