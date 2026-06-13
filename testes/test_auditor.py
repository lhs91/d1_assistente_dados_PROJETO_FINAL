# -*- coding: utf-8 -*-
"""Testes do Auditor de Dados (Marco 2, microatividade 5). Gemini mockado."""
import pytest

from app.agentes.analista_negocios import analisar, redigir_resposta
from app.agentes.auditor_dados import auditar
from app.agentes.engenheiro_dados import gerar_sql
from app.estado import (
    AnaliseDaPergunta,
    ParecerDoAuditor,
    PassoDoPlano,
    RespostaDeNegocio,
    SqlDoPasso,
)
from testes.llm_falso import LlmRoteirizado

pytestmark = pytest.mark.marco2

DOSSIE = (
    "=== DOSSIÊ === ÂNCORA TEMPORAL: os dados terminam em 2025-07-22. "
    "ALERTAS DE QUALIDADE: prefira a fonte transacional."
)

RESULTADO_EXEMPLO = {
    "objetivo": "contar reclamações",
    "sql": "SELECT canal, COUNT(*) FROM suporte GROUP BY canal",
    "justificativa": "agrupa por canal",
    "colunas": ["canal", "total"],
    "linhas": [("Chat", 18), ("E-mail", 14)],
    "n_linhas": 2,
    "truncado": False,
    "tentativas": 1,
}


# ── Auditor de Dados ─────────────────────────────────────────────────────────

def test_auditar_devolve_parecer():
    """A saída do Auditor vira ParecerDoAuditor."""
    parecer = ParecerDoAuditor(aprovado=True)
    llm = LlmRoteirizado({ParecerDoAuditor: [parecer]})
    analise = AnaliseDaPergunta(precisa_esclarecimento=False, passos=[])
    saida = auditar("pergunta", analise, [RESULTADO_EXEMPLO], DOSSIE, llm=llm)
    assert isinstance(saida, ParecerDoAuditor)
    assert saida.aprovado is True


def test_prompt_do_auditor_cobre_os_6_pontos():
    """O prompt manda checar: fonte, âncora, domínios, vazio, truncamento e empates no corte."""
    llm = LlmRoteirizado({ParecerDoAuditor: [ParecerDoAuditor(aprovado=True)]})
    analise = AnaliseDaPergunta(precisa_esclarecimento=False, passos=[])
    auditar("pergunta", analise, [RESULTADO_EXEMPLO], DOSSIE, llm=llm)
    prompt = llm.prompts[0]
    assert "FONTE TRANSACIONAL" in prompt
    assert "ÂNCORA TEMPORAL" in prompt
    assert "DOMÍNIOS CATEGÓRICOS" in prompt
    assert "RESULTADO VAZIO" in prompt
    assert "RECORTE DE EXIBIÇÃO" in prompt
    assert "EMPATES NO CORTE" in prompt


def test_prompt_do_auditor_rotula_recorte_de_exibicao():
    """O recorte de linhas no prompt é rotulado como exibição (não truncamento) e informa o total real."""
    llm = LlmRoteirizado({ParecerDoAuditor: [ParecerDoAuditor(aprovado=True)]})
    analise = AnaliseDaPergunta(precisa_esclarecimento=False, passos=[])
    resultado_longo = dict(RESULTADO_EXEMPLO)
    resultado_longo["linhas"] = [("x", i) for i in range(38)]
    resultado_longo["n_linhas"] = 38
    auditar("pergunta", analise, [resultado_longo], DOSSIE, llm=llm)
    prompt = llm.prompts[0]
    assert "38 no total" in prompt
    assert "recorte" in prompt and "EXIBIÇÃO" in prompt
    assert "não truncamento" in prompt


def test_reprovacao_exige_instrucao():
    """Parecer reprovado carrega problema + instrução + índice do passo a refazer."""
    parecer = ParecerDoAuditor(
        aprovado=False,
        problema="usou a coluna denormalizada do pai",
        instrucao_de_correcao="some os valores da tabela transacional",
        indice_passo_a_refazer=0,
    )
    llm = LlmRoteirizado({ParecerDoAuditor: [parecer]})
    analise = AnaliseDaPergunta(precisa_esclarecimento=False, passos=[])
    saida = auditar("pergunta", analise, [RESULTADO_EXEMPLO], DOSSIE, llm=llm)
    assert saida.aprovado is False
    assert saida.problema and saida.instrucao_de_correcao
    assert saida.indice_passo_a_refazer == 0


def test_prompt_nao_devolve_por_quantidade_de_linhas():
    """V3.6 (truncamento REMOVIDO): a regra 5 explica que as linhas no
    prompt são só RECORTE de exibição — o resultado completo já está com o
    sistema — e PROÍBE devolver pedindo 'mais linhas'."""
    from app.agentes.auditor_dados import _prompt_do_auditor
    prompt = _prompt_do_auditor(
        "p", AnaliseDaPergunta(precisa_esclarecimento=False, passos=[]),
        [{"objetivo": "o", "sql": "s", "colunas": ["c"], "linhas": [[1]],
          "n_linhas": 1, "truncado": False}], "dossie",
    )
    assert "RECORTE" in prompt
    assert "JÁ estão completas" in prompt
    assert "INSUPERÁVEL" not in prompt          # a regra antiga saiu




def test_auditor_audita_a_escolha_do_usuario_nao_a_original():
    """V3.6.1 (correção do loop do 'lucro'): havendo diálogo, o prompt do
    Auditor apresenta os pares, define a PERGUNTA A AUDITAR como a escolha do
    usuário e PROÍBE reprovar por divergência da pergunta original."""
    from app.agentes.auditor_dados import _prompt_do_auditor
    dialogo = [{
        "pergunta_do_analista": "Não há custos para calcular lucro. Quer a "
                                "receita total, por categoria ou por canal?",
        "resposta_do_usuario": "Receita por categoria de produto em 2025",
    }]
    prompt = _prompt_do_auditor(
        "Qual foi o lucro da empresa em 2025?",
        AnaliseDaPergunta(precisa_esclarecimento=False, passos=[]),
        [{"objetivo": "receita por categoria", "sql": "SELECT ...",
          "colunas": ["categoria", "total"], "linhas": [["A", 10]],
          "n_linhas": 6, "truncado": False}],
        "dossie",
        dialogo=dialogo,
    )
    assert "PERGUNTA A AUDITAR (efetiva): Receita por categoria" in prompt
    assert "AUTORIDADE MÁXIMA" in prompt
    assert "PROIBIDO reprovar alegando" in prompt
    assert "[Analista perguntou]" in prompt
    # a original aparece só como contexto do diálogo, não como alvo:
    assert "PERGUNTA DO DIRETOR: Qual foi o lucro" not in prompt
