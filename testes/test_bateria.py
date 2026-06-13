# -*- coding: utf-8 -*-
"""Testes da bateria do enunciado (Marco 2). Gemini mockado."""
import pytest

from app.bateria import PERGUNTAS_DO_ENUNCIADO, executar_bateria
from app.estado import (
    AnaliseDaPergunta,
    ParecerDoAuditor,
    PassoDoPlano,
    RespostaDeNegocio,
    SqlDoPasso,
)
from testes.llm_falso import LlmRoteirizado

pytestmark = pytest.mark.marco2


def _analise():
    return AnaliseDaPergunta(
        precisa_esclarecimento=False,
        passos=[PassoDoPlano(objetivo="contar pedidos")],
    )


def test_bateria_tem_as_5_perguntas_do_enunciado():
    """A constante carrega exatamente as 5 perguntas do enunciado."""
    assert len(PERGUNTAS_DO_ENUNCIADO) == 5
    assert any("via app em maio" in p for p in PERGUNTAS_DO_ENUNCIADO)
    assert any("WhatsApp em 2024" in p for p in PERGUNTAS_DO_ENUNCIADO)
    assert any("não resolvidas por canal" in p for p in PERGUNTAS_DO_ENUNCIADO)


def test_bateria_executa_todas_em_ordem(banco_sintetico):
    """A bateria roda todas as perguntas e devolve uma saída por pergunta."""
    sql_ok = SqlDoPasso(sql="SELECT COUNT(*) FROM pedidos", justificativa="conta")
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(), _analise()],
        SqlDoPasso: [sql_ok, sql_ok],
        ParecerDoAuditor: [ParecerDoAuditor(aprovado=True)] * 2,
        RespostaDeNegocio: [
            RespostaDeNegocio(resposta="R1", premissas_destacadas=[]),
            RespostaDeNegocio(resposta="R2", premissas_destacadas=[]),
        ],
    })
    saidas = executar_bateria(
        perguntas=["Pergunta A?", "Pergunta B?"],
        caminho_banco=banco_sintetico,
        llm=llm,
    )
    assert [s["pergunta"] for s in saidas] == ["Pergunta A?", "Pergunta B?"]
    assert [s["resposta"] for s in saidas] == ["R1", "R2"]


def test_bateria_continua_apos_excecao(banco_sintetico):
    """Uma pergunta que estoura exceção NÃO derruba a bateria: o erro é
    registrado e a pergunta seguinte roda normalmente."""
    sql_ok = SqlDoPasso(sql="SELECT COUNT(*) FROM pedidos", justificativa="conta")
    # Roteiro propositalmente INSUFICIENTE para a 1ª pergunta (1 análise só):
    # a 2ª pergunta estoura o roteiro do mock (AssertionError) e a bateria
    # precisa sobreviver e registrar o erro... então invertendo: 1ª estoura.
    llm = LlmRoteirizado({
        # Sem AnaliseDaPergunta para a 1ª → AssertionError na 1ª pergunta.
        AnaliseDaPergunta: [],
    })
    llm_2 = LlmRoteirizado({
        AnaliseDaPergunta: [_analise()],
        SqlDoPasso: [sql_ok],
        ParecerDoAuditor: [ParecerDoAuditor(aprovado=True)],
        RespostaDeNegocio: [RespostaDeNegocio(resposta="OK", premissas_destacadas=[])],
    })

    # 1ª chamada usa llm (estoura); para a 2ª, trocamos o roteiro por dentro:
    class LlmEmDuasFases:
        """1ª pergunta usa o roteiro vazio (estoura); depois, o roteiro bom."""
        def __init__(self):
            self.fase = 0
        def with_structured_output(self, schema):
            alvo = llm if self.fase == 0 else llm_2
            proxy = alvo.with_structured_output(schema)
            if schema is AnaliseDaPergunta and self.fase == 0:
                self.fase = 1   # a partir da próxima análise, roteiro bom
            return proxy

    saidas = executar_bateria(
        perguntas=["Quebra?", "Funciona?"],
        caminho_banco=banco_sintetico,
        llm=LlmEmDuasFases(),
    )
    assert len(saidas) == 2
    assert "erro_execucao" in saidas[0]
    assert saidas[1]["resposta"] == "OK"
