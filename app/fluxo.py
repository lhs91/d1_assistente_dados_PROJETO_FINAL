# -*- coding: utf-8 -*-
"""
fluxo.py — O motor de streaming headless (Marco 4).

A UI não conhece LangGraph: ela consome este GERADOR, que traduz o
grafo.stream(stream_mode='updates') em três tipos de evento:

  'trace'     → um EventoTrace novo, no instante em que o nó o registra;
  'interrupt' → o grafo pausou (payload = pergunta de esclarecimento);
  'final'     → terminou (payload = dict no MESMO formato de
                responder_pergunta: resposta, premissas, especificacao_visual,
                trace, falha_graciosa, ...).

Decisão de isolamento (registrada): cada PERGUNTA ganha um thread_id novo —
os campos com reducer (trace, chamadas_llm) acumulam por thread; reusar o
thread entre perguntas misturaria históricos e esgotaria o orçamento global.
O GRAFO é o mesmo da sessão inteira (o MemorySaver vive nele), o que garante
que o resume do interrupt encontre o checkpoint certo.
"""
import uuid
from dataclasses import dataclass

from langgraph.types import Command

from app.grafo import construir_grafo
from app.trace import registrar


@dataclass
class EventoDeFluxo:
    """O que o gerador emite para quem estiver assistindo (UI, CLI, teste)."""
    tipo: str        # 'trace' | 'interrupt' | 'final'
    payload: object


@dataclass
class SessaoDeFluxo:
    """Tudo que precisa sobreviver entre o interrupt e o resume."""
    grafo: object
    configuracao: dict


def criar_sessao(llm=None) -> SessaoDeFluxo:
    """Compila o grafo UMA vez por sessão de chat (allowlist do checkpoint
    incluída, via construir_grafo). A configuração é preenchida por pergunta."""
    return SessaoDeFluxo(grafo=construir_grafo(llm=llm), configuracao={})


def executar_em_fluxo(
    sessao: SessaoDeFluxo,
    pergunta: str,
    caminho_banco,
    modo_visualizacao: str,
):
    """GERADOR: inicia uma pergunta NOVA (thread_id novo) e emite eventos."""
    sessao.configuracao = {"configurable": {"thread_id": str(uuid.uuid4())}}
    estado_inicial = {
        "pergunta": pergunta,
        "caminho_banco": str(caminho_banco),
        "modo_visualizacao": modo_visualizacao,
        "indice_passo_atual": 0,
        "resultados": [],
        "tentativas_no_passo": 0,
        "devolucoes_auditor": 0,
        "chamadas_llm": 0,
        "esclarecimentos": [],
        "trace": [],
    }
    # V3.5: a PERGUNTA abre o log (terminal com 5 quebras, log ao vivo e
    # trace técnico — o evento entra no estado e o reducer o preserva).
    abertura = []
    registrar(abertura, "pergunta", "info", pergunta)
    estado_inicial["trace"] = abertura
    yield EventoDeFluxo("trace", abertura[0])
    yield from _emitir(sessao, estado_inicial)


def retomar_fluxo(sessao: SessaoDeFluxo, resposta_do_usuario: str):
    """GERADOR: retoma o interrupt pendente com a resposta do usuário.
    Pode haver NOVO interrupt (o orçamento global segue valendo)."""
    yield from _emitir(sessao, Command(resume=resposta_do_usuario))


def _emitir(sessao: SessaoDeFluxo, entrada):
    """Núcleo comum: traduz updates do grafo em EventoDeFluxo."""
    for atualizacao in sessao.grafo.stream(
        entrada, sessao.configuracao, stream_mode="updates"
    ):
        if "__interrupt__" in atualizacao:
            yield EventoDeFluxo(
                "interrupt", atualizacao["__interrupt__"][0].value
            )
            return                      # quem consome decide quando retomar
        for parcial in atualizacao.values():
            if not parcial:
                continue
            for evento in parcial.get("trace") or []:
                yield EventoDeFluxo("trace", evento)

    estado = sessao.grafo.get_state(sessao.configuracao).values
    resposta = estado.get("resposta")
    yield EventoDeFluxo("final", {
        "pergunta": estado.get("pergunta"),
        "resposta": resposta.resposta if resposta else None,
        "premissas": resposta.premissas_destacadas if resposta else [],
        "impactos_e_acoes": resposta.impactos_e_acoes if resposta else [],
        "falha_graciosa": estado.get("falha_graciosa"),
        "resultados": estado.get("resultados", []),
        "trace": estado.get("trace", []),
        "chamadas_llm": estado.get("chamadas_llm", 0),
        "especificacao_visual": estado.get("especificacao_visual"),
    })
