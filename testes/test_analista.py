# -*- coding: utf-8 -*-
"""Testes do Analista de Negócios (Marco 2, microatividade 3). Gemini mockado."""
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


# ── Analista de Negócios ─────────────────────────────────────────────────────

def test_analisar_devolve_plano_estruturado():
    """A saída do Analista vira AnaliseDaPergunta com passos de objetivo claro."""
    analise = AnaliseDaPergunta(
        precisa_esclarecimento=False,
        premissas=["maio = 2025"],
        passos=[PassoDoPlano(objetivo="contar clientes por estado")],
    )
    llm = LlmRoteirizado({AnaliseDaPergunta: [analise]})
    saida = analisar("pergunta", DOSSIE, llm=llm)
    assert isinstance(saida, AnaliseDaPergunta)
    assert saida.passos[0].objetivo == "contar clientes por estado"


def test_prompt_do_analista_contem_dossie_e_regra_de_ambiguidade():
    """O prompt carrega o dossiê e manda verificar a âncora ANTES de declarar ambiguidade."""
    analise = AnaliseDaPergunta(precisa_esclarecimento=False, passos=[])
    llm = LlmRoteirizado({AnaliseDaPergunta: [analise]})
    analisar("qual o total de maio?", DOSSIE, llm=llm)
    prompt = llm.prompts[0]
    assert "ÂNCORA TEMPORAL" in prompt
    assert "NÃO é ambíguo" in prompt
    assert "todo o histórico" in prompt        # período ausente = premissa, não interrupt
    assert "qual o total de maio?" in prompt


def test_ambiguidade_material_pede_esclarecimento():
    """precisa_esclarecimento=True vem acompanhado da pergunta ao usuário."""
    analise = AnaliseDaPergunta(
        precisa_esclarecimento=True,
        pergunta_de_esclarecimento="Desempenho de quê: vendas, suporte ou campanhas?",
        passos=[],
    )
    llm = LlmRoteirizado({AnaliseDaPergunta: [analise]})
    saida = analisar("como foi o desempenho?", DOSSIE, llm=llm)
    assert saida.precisa_esclarecimento is True
    assert "vendas" in saida.pergunta_de_esclarecimento


def test_esclarecimentos_entram_no_prompt_sem_nova_pergunta():
    """Esclarecimentos já dados entram no prompt com a ordem de não perguntar de novo."""
    analise = AnaliseDaPergunta(precisa_esclarecimento=False, passos=[])
    llm = LlmRoteirizado({AnaliseDaPergunta: [analise]})
    analisar("como foi?", DOSSIE, esclarecimentos=["quero vendas de 2025"], llm=llm)
    prompt = llm.prompts[0]
    assert "quero vendas de 2025" in prompt
    assert "AUTORIDADE MÁXIMA" in prompt


def test_redigir_resposta_usa_apenas_resultados():
    """O prompt da redação contém os resultados e proíbe inventar números."""
    analise = AnaliseDaPergunta(precisa_esclarecimento=False, premissas=["x"], passos=[])
    resposta = RespostaDeNegocio(resposta="Chat lidera com 18.", premissas_destacadas=["x"])
    llm = LlmRoteirizado({RespostaDeNegocio: [resposta]})
    redigir_resposta("pergunta", analise, [RESULTADO_EXEMPLO], DOSSIE, llm=llm)
    prompt = llm.prompts[0]
    assert "('Chat', 18)" in prompt
    assert "PROIBIDO" in prompt and "inventar" in prompt


def test_redigir_resposta_destaca_premissas():
    """As premissas da análise chegam ao prompt e voltam destacadas na resposta."""
    analise = AnaliseDaPergunta(
        precisa_esclarecimento=False, premissas=["maio = 2025 (único na base)"], passos=[]
    )
    resposta = RespostaDeNegocio(
        resposta="...", premissas_destacadas=["maio = 2025 (único na base)"]
    )
    llm = LlmRoteirizado({RespostaDeNegocio: [resposta]})
    saida = redigir_resposta("pergunta", analise, [RESULTADO_EXEMPLO], DOSSIE, llm=llm)
    assert "maio = 2025 (único na base)" in llm.prompts[0]
    assert saida.premissas_destacadas == ["maio = 2025 (único na base)"]




def test_prompt_da_autoridade_ao_esclarecimento():
    """A resposta do usuário tem autoridade: redefine a pergunta efetiva e
    proíbe repetir esclarecimento já feito (correção do loop do fogo M4)."""
    analise = AnaliseDaPergunta(
        precisa_esclarecimento=False,
        passos=[PassoDoPlano(objetivo="somar receita de 2025")],
    )
    llm = LlmRoteirizado({AnaliseDaPergunta: [analise]})
    analisar("qual o lucro?", DOSSIE, esclarecimentos=["quero a receita de 2025"], llm=llm)
    prompt = llm.prompts[0]
    assert "NOVA PERGUNTA EFETIVA" in prompt
    assert "PROIBIDO repetir" in prompt


def test_prompt_classifica_escrita_como_fora_de_escopo():
    """A regra 0 do prompt: pedido de escrita não vira esclarecimento."""
    analise = AnaliseDaPergunta(precisa_esclarecimento=False, passos=[])
    llm = LlmRoteirizado({AnaliseDaPergunta: [analise]})
    analisar("Atualize o cliente 1", DOSSIE, llm=llm)
    prompt = llm.prompts[0]
    assert "PEDIDO DE ESCRITA NÃO É AMBIGUIDADE" in prompt
    assert "pedido_fora_de_escopo" in prompt
    assert "SOMENTE" in prompt and "LEITURA" in prompt


def test_prompt_dado_inexistente_vira_esclarecimento_ancorado():
    """V3.5 (correção do fogo): dado inexistente NÃO é recusa direta — a
    regra 0a manda perguntar (interrupt) oferecendo 2 a 3 alternativas que
    EXISTEM no dossiê; fora_de_escopo fica restrito a escrita ou a nenhum
    dado relacionado."""
    analise = AnaliseDaPergunta(precisa_esclarecimento=False, passos=[])
    llm = LlmRoteirizado({AnaliseDaPergunta: [analise]})
    analisar(
        "Existe relação entre o valor da compra e a quantidade de itens? "
        "Mostre num gráfico de dispersão.",
        DOSSIE, llm=llm,
    )
    prompt = llm.prompts[0]
    assert "ESCLARECIMENTO ANCORADO NO SCHEMA, NUNCA RECUSA DIRETA" in prompt
    assert "2 a 3 alternativas" in prompt
    assert "APENAS para pedidos de ESCRITA" in prompt
    assert "PROIBIDO sugerir dados" in prompt          # regra 0b preservada
    assert "ANCORADA NO SCHEMA" in prompt


def test_prompt_com_dialogo_reframa_a_pergunta_efetiva():
    """V3.6 (correção do loop): o prompt apresenta o DIÁLOGO em PARES
    (pergunta do Analista ↔ resposta do usuário), promove a última resposta
    a PERGUNTA EFETIVA e PROÍBE reperguntar a mesma dúvida."""
    analise = AnaliseDaPergunta(precisa_esclarecimento=False, passos=[])
    llm = LlmRoteirizado({AnaliseDaPergunta: [analise]})
    dialogo = [{
        "pergunta_do_analista": "Não há 'quantidade de itens'. Prefere "
                                "preco × data_item ou preco × origem?",
        "resposta_do_usuario": "A distribuição do preco ao longo do tempo",
    }]
    analisar("Existe relação entre o valor e a quantidade de itens?",
             DOSSIE, dialogo=dialogo, llm=llm)
    prompt = llm.prompts[0]
    assert "[Você perguntou]" in prompt
    assert "[Usuário respondeu]" in prompt
    assert "PERGUNTA EFETIVA DO DIRETOR" in prompt
    assert "A distribuição do preco ao longo do tempo" in prompt
    assert "PROIBIDO REPERGUNTAR" in prompt
    # a pergunta original foi REBAIXADA a contexto:
    assert "já superado pelo diálogo" in prompt


def test_prompt_proibe_recusar_por_tipo_de_grafico():
    """V3.6.2: a regra 00 deixa explícito que o tipo/técnica de gráfico não é
    da alçada do Analista — se as colunas dos eixos existem, há plano; é
    PROIBIDO recusar por causa de regressão/tipo de gráfico."""
    analise = AnaliseDaPergunta(precisa_esclarecimento=False, passos=[])
    llm = LlmRoteirizado({AnaliseDaPergunta: [analise]})
    analisar("Scatter Polynomial Regression das compras do canal App",
             DOSSIE, llm=llm)
    prompt = llm.prompts[0]
    assert "TIPO DE GRÁFICO NÃO É DA SUA ALÇADA" in prompt
    assert "Designer" in prompt
    assert "regressão" in prompt.lower()


def test_prompt_do_diretor_injeta_outliers():
    """V3.11: o prompt de redação inclui o bloco de outliers (z>2) e a regra
    6 que manda destacá-los na conclusão executiva."""
    from app.agentes.analista_negocios import _prompt_de_redacao
    resultados = [{
        "objetivo": "receita por estado", "sql": "SELECT ...",
        "colunas": ["estado", "receita"],
        "linhas": [["SP", 141665], ["SC", 9670], ["PR", 6807],
                   ["MG", 5200], ["BA", 4900], ["RS", 5100]],
        "n_linhas": 6, "truncado": False,
    }]
    analise = AnaliseDaPergunta(precisa_esclarecimento=False, passos=[])
    prompt = _prompt_de_redacao("Receita por estado?", analise, resultados, "d")
    assert "VALORES FORA DO PADRÃO" in prompt
    assert "SP" in prompt
    assert "VALORES FORA DO PADRÃO" in prompt  # regra 6 + bloco
