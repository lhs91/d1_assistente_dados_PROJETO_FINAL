# -*- coding: utf-8 -*-
"""Testes do nó visualizador no grafo (Marco 3, microatividade 6). Mockado."""
import json

import pytest

from app.estado import (
    AnaliseDaPergunta,
    ParecerDoAuditor,
    PassoDoPlano,
    PropostaDoDesigner,
    RespostaDeNegocio,
    SqlDoPasso,
)
from app.principal import responder_pergunta
from testes.llm_falso import LlmRoteirizado

pytestmark = pytest.mark.marco3


def _analise(n_passos=1):
    return AnaliseDaPergunta(
        precisa_esclarecimento=False,
        passos=[PassoDoPlano(objetivo=f"objetivo {i + 1}") for i in range(n_passos)],
    )


SQL_PEDIDOS = SqlDoPasso(sql="SELECT COUNT(*) AS total FROM pedidos", justificativa="conta")
SQL_ORIGEM = SqlDoPasso(
    sql="SELECT origem, COUNT(*) AS n FROM pedidos GROUP BY origem",
    justificativa="agrupa por origem",
)
APROVADO = ParecerDoAuditor(aprovado=True)
RESPOSTA = RespostaDeNegocio(resposta="OK.", premissas_destacadas=[])

OPTION_VALIDO = json.dumps({
    "title": {"text": "t"},
    "xAxis": {"type": "category", "data": ["Loja", "Telefone"]},
    "yAxis": {"type": "value"},
    "series": [{"type": "bar", "data": [10, 10]}],
})
OPTION_COM_JS = json.dumps({
    "tooltip": {"formatter": "function(p){return p}"},
    "series": [{"type": "bar", "data": [1]}],
})


def _roteiro_base(n_passos=1, designers=None):
    roteiro = {
        AnaliseDaPergunta: [_analise(n_passos)],
        SqlDoPasso: [SQL_PEDIDOS, SQL_ORIGEM][:n_passos],
        ParecerDoAuditor: [APROVADO],
        RespostaDeNegocio: [RESPOSTA],
    }
    if designers is not None:
        roteiro[PropostaDoDesigner] = designers
    return roteiro


def test_modo_pre_setado_zero_llm_extra(banco_sintetico):
    """Modo pré-setado: especificação pronta SEM chamar o Designer (4 chamadas)."""
    llm = LlmRoteirizado(_roteiro_base())          # SEM roteiro de Designer
    saida = responder_pergunta(
        "Quantos pedidos?", banco_sintetico, llm=llm,
        modo_visualizacao="pre_setado",
    )
    espec = saida["especificacao_visual"]
    assert espec is not None
    assert espec.modo == "pre_setado"
    assert espec.tipo == "metrica"                 # COUNT(*) → 1 valor
    assert saida["chamadas_llm"] == 4              # Designer NÃO foi chamado


def test_modo_agente_option_no_estado(banco_sintetico):
    """Modo agente: option do Designer validado e presente; 5 chamadas LLM."""
    proposta = PropostaDoDesigner(
        tipo_grafico="barra", option_json=OPTION_VALIDO, justificativa="barra simples"
    )
    llm = LlmRoteirizado(_roteiro_base(designers=[proposta]))
    saida = responder_pergunta(
        "Quantos pedidos?", banco_sintetico, llm=llm, modo_visualizacao="agente",
    )
    espec = saida["especificacao_visual"]
    assert espec.modo == "agente"
    assert espec.option["series"][0]["type"] == "bar"
    assert espec.fallback_usado is False
    assert saida["chamadas_llm"] == 5


def test_option_invalido_faz_retry_com_motivo(banco_sintetico):
    """1ª proposta com function() → retry com o motivo no prompt → 2ª válida usada."""
    proposta_ruim = PropostaDoDesigner(
        tipo_grafico="barra", option_json=OPTION_COM_JS, justificativa="x"
    )
    proposta_boa = PropostaDoDesigner(
        tipo_grafico="barra", option_json=OPTION_VALIDO, justificativa="corrigida"
    )
    llm = LlmRoteirizado(_roteiro_base(designers=[proposta_ruim, proposta_boa]))
    saida = responder_pergunta(
        "Quantos pedidos?", banco_sintetico, llm=llm, modo_visualizacao="agente",
    )
    espec = saida["especificacao_visual"]
    assert espec.fallback_usado is False
    assert espec.justificativa == "corrigida"
    # O motivo da reprova chegou ao prompt do retry:
    prompt_retry = llm.prompts_por_schema[PropostaDoDesigner][1]
    assert "REPROVADA" in prompt_retry and "function(" in prompt_retry
    # E o trace registrou a reprova:
    assert any(e.tipo == "visual_reprovado" for e in saida["trace"])


def test_fallback_apos_tentativas(banco_sintetico):
    """Option inválido nas 2 tentativas → tabela com motivo; RESPOSTA intacta."""
    proposta_ruim = PropostaDoDesigner(
        tipo_grafico="barra", option_json=OPTION_COM_JS, justificativa="x"
    )
    llm = LlmRoteirizado(_roteiro_base(designers=[proposta_ruim, proposta_ruim]))
    saida = responder_pergunta(
        "Quantos pedidos?", banco_sintetico, llm=llm, modo_visualizacao="agente",
    )
    espec = saida["especificacao_visual"]
    assert espec.tipo == "tabela"
    assert espec.fallback_usado is True
    assert "function(" in espec.motivo_fallback or "executável" in espec.motivo_fallback
    assert saida["resposta"] == "OK."               # a resposta NUNCA cai


def test_visualiza_o_ultimo_passo(banco_sintetico):
    """Plano de 2 passos → a especificação usa os dados do passo 2 (origem×n)."""
    llm = LlmRoteirizado(_roteiro_base(n_passos=2))
    saida = responder_pergunta(
        "Pedidos por origem?", banco_sintetico, llm=llm,
        modo_visualizacao="pre_setado",
    )
    espec = saida["especificacao_visual"]
    assert espec.tipo == "barra"                    # passo 2: categórica
    categorias = espec.option["xAxis"]["data"]
    assert set(categorias) == {"Loja", "Telefone"}  # dados do sintético


def test_excecao_no_visualizador_nao_derruba_resposta(banco_sintetico):
    """Designer estourando exceção → fallback tabela + evento; resposta sai."""
    llm = LlmRoteirizado(_roteiro_base(designers=[]))   # roteiro vazio → AssertionError
    saida = responder_pergunta(
        "Quantos pedidos?", banco_sintetico, llm=llm, modo_visualizacao="agente",
    )
    espec = saida["especificacao_visual"]
    assert espec.fallback_usado is True
    assert saida["resposta"] == "OK."
    assert any(e.tipo == "visual_fallback" for e in saida["trace"])


def test_modo_viaja_no_estado(banco_sintetico):
    """O modo passado a responder_pergunta chega ao nó visualizador."""
    llm = LlmRoteirizado(_roteiro_base())
    saida = responder_pergunta(
        "Quantos pedidos?", banco_sintetico, llm=llm,
        modo_visualizacao="pre_setado",
    )
    assert saida["especificacao_visual"].modo == "pre_setado"
