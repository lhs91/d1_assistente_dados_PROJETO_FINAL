# -*- coding: utf-8 -*-
"""Teste da allowlist do checkpointer (correção do aviso de desserialização)."""
import logging

import pytest

from app.estado import (
    AnaliseDaPergunta,
    ParecerDoAuditor,
    PassoDoPlano,
    RespostaDeNegocio,
    SqlDoPasso,
)
from app.principal import responder_pergunta
from testes.llm_falso import LlmRoteirizado

pytestmark = pytest.mark.marco3


def test_resume_do_interrupt_sem_aviso_de_tipo_nao_registrado(
    banco_sintetico, caplog
):
    """O ciclo interrupt→resume (que desserializa o checkpoint) não emite
    'Deserializing unregistered type' — os tipos do estado estão na allowlist
    do serializador."""
    # O langgraph avisa só UMA VEZ por tipo/processo; limpamos o registro
    # para o teste não passar de carona em um aviso já emitido antes.
    try:
        from langgraph.checkpoint.serde import jsonplus
        getattr(jsonplus, "_warned_unregistered_types", set()).clear()
    except Exception:  # noqa: BLE001 — detalhe interno pode mudar de lugar
        pass

    ambigua = AnaliseDaPergunta(
        precisa_esclarecimento=True,
        pergunta_de_esclarecimento="Qual período?",
        passos=[],
    )
    plano = AnaliseDaPergunta(
        precisa_esclarecimento=False,
        passos=[PassoDoPlano(objetivo="contar pedidos")],
    )
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [ambigua, plano],
        SqlDoPasso: [SqlDoPasso(sql="SELECT COUNT(*) FROM pedidos",
                                justificativa="conta")],
        ParecerDoAuditor: [ParecerDoAuditor(aprovado=True)],
        RespostaDeNegocio: [RespostaDeNegocio(resposta="ok",
                                              premissas_destacadas=[])],
    })
    with caplog.at_level(logging.WARNING):
        saida = responder_pergunta(
            "Como foi?", banco_sintetico, llm=llm,
            responder_interrupt=lambda pergunta: "todo período",
            modo_visualizacao="pre_setado",
        )
    assert saida["resposta"] == "ok"
    assert "Deserializing unregistered type" not in caplog.text
