# -*- coding: utf-8 -*-
"""Testes do motor de fluxo headless (Marco 4, microatividade 2). Mockado;
o grafo, o Guardrail e o Executor são os REAIS contra o banco sintético."""
import pytest

from app.config import MAX_TENTATIVAS_SQL
from app.estado import (
    AnaliseDaPergunta,
    ParecerDoAuditor,
    PassoDoPlano,
    RespostaDeNegocio,
    SqlDoPasso,
)
from app.fluxo import criar_sessao, executar_em_fluxo, retomar_fluxo
from testes.llm_falso import LlmRoteirizado

pytestmark = pytest.mark.marco4

SQL_OK = SqlDoPasso(sql="SELECT COUNT(*) AS total FROM pedidos", justificativa="conta")
SQL_INVALIDO = SqlDoPasso(sql="SELECT x FROM tabela_fantasma", justificativa="errada")
APROVADO = ParecerDoAuditor(aprovado=True)
RESPOSTA = RespostaDeNegocio(resposta="Há 20 pedidos.", premissas_destacadas=["p1"])


def _analise(n=1):
    return AnaliseDaPergunta(
        precisa_esclarecimento=False,
        passos=[PassoDoPlano(objetivo=f"objetivo {i+1}") for i in range(n)],
    )


def _analise_ambigua():
    return AnaliseDaPergunta(
        precisa_esclarecimento=True,
        pergunta_de_esclarecimento="Qual período?",
        passos=[],
    )


def _roteiro_feliz():
    return {
        AnaliseDaPergunta: [_analise()],
        SqlDoPasso: [SQL_OK],
        ParecerDoAuditor: [APROVADO],
        RespostaDeNegocio: [RESPOSTA],
    }


def _consumir(gerador):
    eventos = list(gerador)
    return eventos, [e.tipo for e in eventos]


def test_fluxo_emite_trace_na_ordem(banco_sintetico):
    """Caminho feliz: 'trace' na MESMA ordem do trace final; exatamente um 'final'."""
    sessao = criar_sessao(llm=LlmRoteirizado(_roteiro_feliz()))
    eventos, tipos = _consumir(
        executar_em_fluxo(sessao, "Quantos pedidos?", banco_sintetico, "pre_setado")
    )
    assert tipos.count("final") == 1 and tipos[-1] == "final"
    emitidos = [e.payload.conteudo for e in eventos if e.tipo == "trace"]
    finais = [t.conteudo for t in eventos[-1].payload["trace"]]
    assert emitidos == finais          # streaming fiel ao trace consolidado
    assert len(emitidos) >= 7          # todos os nós registraram


def test_final_carrega_contrato_completo(banco_sintetico):
    """O payload do 'final' tem o formato de responder_pergunta (chaves idênticas)."""
    sessao = criar_sessao(llm=LlmRoteirizado(_roteiro_feliz()))
    eventos, _ = _consumir(
        executar_em_fluxo(sessao, "Quantos pedidos?", banco_sintetico, "pre_setado")
    )
    final = eventos[-1].payload
    assert set(final) == {"pergunta", "resposta", "premissas",
                          "impactos_e_acoes", "falha_graciosa",
                          "resultados", "trace", "chamadas_llm",
                          "especificacao_visual"}
    assert final["resposta"] == "Há 20 pedidos."
    assert final["premissas"] == ["p1"]


def test_interrupt_sinalizado_e_pausa(banco_sintetico):
    """Análise ambígua: evento 'interrupt' com a pergunta; o gerador PARA sem 'final'."""
    sessao = criar_sessao(llm=LlmRoteirizado({AnaliseDaPergunta: [_analise_ambigua()]}))
    eventos, tipos = _consumir(
        executar_em_fluxo(sessao, "Como foi?", banco_sintetico, "pre_setado")
    )
    assert tipos[-1] == "interrupt"
    assert "final" not in tipos
    assert eventos[-1].payload == "Qual período?"


def test_retomar_conclui_apos_interrupt(banco_sintetico):
    """retomar_fluxo: a resposta do usuário retoma e conclui; virou premissa."""
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise_ambigua(), _analise()],
        SqlDoPasso: [SQL_OK],
        ParecerDoAuditor: [APROVADO],
        RespostaDeNegocio: [RESPOSTA],
    })
    sessao = criar_sessao(llm=llm)
    _consumir(executar_em_fluxo(sessao, "Como foi?", banco_sintetico, "pre_setado"))
    eventos, tipos = _consumir(retomar_fluxo(sessao, "todo período"))
    assert tipos[-1] == "final"
    assert eventos[-1].payload["resposta"] == "Há 20 pedidos."
    # A resposta do usuário chegou à reanálise:
    assert "todo período" in llm.prompts_por_schema[AnaliseDaPergunta][1]


def test_mesma_sessao_duas_perguntas(banco_sintetico):
    """Duas perguntas na MESMA sessão: históricos isolados (thread novo por
    pergunta), orçamento zerado, traces não se misturam."""
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(), _analise()],
        SqlDoPasso: [SQL_OK, SQL_OK],
        ParecerDoAuditor: [APROVADO, APROVADO],
        RespostaDeNegocio: [
            RespostaDeNegocio(resposta="R1", premissas_destacadas=[]),
            RespostaDeNegocio(resposta="R2", premissas_destacadas=[]),
        ],
    })
    sessao = criar_sessao(llm=llm)
    eventos_1, _ = _consumir(
        executar_em_fluxo(sessao, "Pergunta A?", banco_sintetico, "pre_setado")
    )
    eventos_2, _ = _consumir(
        executar_em_fluxo(sessao, "Pergunta B?", banco_sintetico, "pre_setado")
    )
    final_1, final_2 = eventos_1[-1].payload, eventos_2[-1].payload
    assert (final_1["resposta"], final_2["resposta"]) == ("R1", "R2")
    assert final_2["chamadas_llm"] == 4                 # orçamento NÃO acumulou
    assert len(final_2["trace"]) == len(final_1["trace"])   # trace não misturou


def test_falha_graciosa_flui_como_final(banco_sintetico):
    """Teto estourado: 'final' com falha_graciosa preenchida — a UI nunca vê exceção."""
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise()],
        SqlDoPasso: [SQL_INVALIDO] * MAX_TENTATIVAS_SQL,
    })
    sessao = criar_sessao(llm=llm)
    eventos, tipos = _consumir(
        executar_em_fluxo(sessao, "Quantos?", banco_sintetico, "pre_setado")
    )
    assert tipos[-1] == "final"
    final = eventos[-1].payload
    assert final["resposta"] is None
    assert "tabela_fantasma" in final["falha_graciosa"]


def test_modo_visualizacao_chega_ao_no(banco_sintetico):
    """O modo passado a executar_em_fluxo chega à EspecificacaoVisual do 'final'."""
    sessao = criar_sessao(llm=LlmRoteirizado(_roteiro_feliz()))
    eventos, _ = _consumir(
        executar_em_fluxo(sessao, "Quantos pedidos?", banco_sintetico, "pre_setado")
    )
    espec = eventos[-1].payload["especificacao_visual"]
    assert espec is not None and espec.modo == "pre_setado"


def test_teto_de_esclarecimentos_encerra_com_falha_graciosa(banco_sintetico):
    """Correção crítica do fogo M4: um Analista que insiste em pedir
    esclarecimento não prende o usuário em loop — na 4ª tentativa (teto
    MAX_ESCLARECIMENTOS=3) o grafo encerra com a mensagem de recomeço."""
    from app.config import MAX_ESCLARECIMENTOS
    sempre_ambiguo = LlmRoteirizado(
        {AnaliseDaPergunta: [_analise_ambigua()] * (MAX_ESCLARECIMENTOS + 1)}
    )
    sessao = criar_sessao(llm=sempre_ambiguo)
    eventos, tipos = _consumir(
        executar_em_fluxo(sessao, "Qual foi o lucro de 2025?", banco_sintetico,
                          "pre_setado")
    )
    respostas = 0
    while tipos[-1] == "interrupt":
        respostas += 1
        eventos, tipos = _consumir(retomar_fluxo(sessao, f"resposta {respostas}"))
    assert tipos[-1] == "final"
    assert respostas == MAX_ESCLARECIMENTOS          # perguntou 3x, na 4ª cortou
    final = eventos[-1].payload
    assert "Não foi possível definir uma estratégia" in final["falha_graciosa"]
    assert "recomeça do zero" in final["falha_graciosa"]


def test_pedido_de_escrita_recusa_direta_sem_interrupt(banco_sintetico):
    """Correção V2: pedido de ALTERAÇÃO de dados (UPDATE) não vira ciclo de
    esclarecimento — recusa honesta DIRETA (somente leitura) e fim."""
    analise_escrita = AnaliseDaPergunta(
        precisa_esclarecimento=False,
        pedido_fora_de_escopo=True,
        pedido_de_escrita=True,
        motivo_fora_de_escopo="O usuário pediu para ATUALIZAR o estado do cliente 1.",
    )
    llm = LlmRoteirizado({AnaliseDaPergunta: [analise_escrita]})
    sessao = criar_sessao(llm=llm)
    eventos, tipos = _consumir(
        executar_em_fluxo(sessao, "Atualize o estado do cliente 1 para 'Bahia'.",
                          banco_sintetico, "pre_setado")
    )
    assert "interrupt" not in tipos                  # NÃO pergunta nada
    assert tipos[-1] == "final"
    final = eventos[-1].payload
    assert "SOMENTE LEITURA" in final["falha_graciosa"]
    assert "recomeça do zero" in final["falha_graciosa"]


def test_correcao_que_repete_o_sql_encerra_como_improdutiva(banco_sintetico):
    """Robustez V3.3 (caso do fogo: auditor exigia 946 linhas com teto de
    200): se a correção pós-devolução REPETE o SQL reprovado, o grafo corta
    o ciclo na hora com explicação honesta — sem queimar 15 devoluções."""
    reprova = ParecerDoAuditor(
        aprovado=False, problema="truncado",
        instrucao_de_correcao="retorne todas as linhas",
        indice_passo_a_refazer=0,
    )
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(1)],
        SqlDoPasso: [SQL_OK, SQL_OK],          # correção IDÊNTICA à reprovada
        ParecerDoAuditor: [reprova],
    })
    sessao = criar_sessao(llm=llm)
    eventos, tipos = _consumir(
        executar_em_fluxo(sessao, "Todas as compras?", banco_sintetico,
                          "pre_setado")
    )
    assert tipos[-1] == "final"
    final = eventos[-1].payload
    assert "Ciclo improdutivo" in final["falha_graciosa"]
    assert "AGREGADO" in final["falha_graciosa"]


PERGUNTA_DA_DISPERSAO = ("Existe relação entre o valor da compra e a "
                         "quantidade de itens? Mostre num gráfico de dispersão.")


def test_dado_inexistente_pergunta_e_segue_apos_resposta(banco_sintetico):
    """V3.5 — o COMPORTAMENTO ESPERADO da pergunta do fogo: 'quantidade de
    itens' não existe → o Analista PERGUNTA (interrupt) oferecendo
    alternativas reais; o usuário escolhe uma; a análise SEGUE até a
    resposta final — sem recusa direta e sem teto estourado."""
    esclarecimento = AnaliseDaPergunta(
        precisa_esclarecimento=True,
        pergunta_de_esclarecimento=(
            "O dado 'quantidade de itens' não existe no banco. A tabela "
            "itens tem as colunas preco, data_item e origem. Você quer ver "
            "a relação do preco com data_item ou do preco com origem?"
        ),
        passos=[],
    )
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [esclarecimento, _analise(1)],
        SqlDoPasso: [SQL_OK],
        ParecerDoAuditor: [ParecerDoAuditor(aprovado=True, problema=None,
                                            instrucao_de_correcao=None,
                                            indice_passo_a_refazer=None)],
        RespostaDeNegocio: [RespostaDeNegocio(
            resposta="Relação analisada por origem.",
            premissas_destacadas=[])],
    })
    sessao = criar_sessao(llm=llm)
    eventos, tipos = _consumir(
        executar_em_fluxo(sessao, PERGUNTA_DA_DISPERSAO, banco_sintetico,
                          "pre_setado")
    )
    assert tipos[-1] == "interrupt"            # perguntou, NÃO recusou
    pergunta_feita = str(eventos[-1].payload)
    assert "não existe" in pergunta_feita

    # ANCORAGEM VALIDADA CONTRA O BANCO: toda coluna oferecida como
    # alternativa EXISTE de fato no schema (PRAGMA) — o mecanismo que o
    # comportamento esperado exige.
    import sqlite3
    con = sqlite3.connect(banco_sintetico)
    colunas_reais = {
        nome
        for (tabela,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")
        for nome in [c[1] for c in con.execute(f"PRAGMA table_info({tabela})")]
    }
    con.close()
    for alternativa in ("preco", "data_item", "origem"):
        assert alternativa in pergunta_feita
        assert alternativa in colunas_reais

    # O usuário escolhe uma alternativa REAL e o fluxo SEGUE até o final:
    # (V3.6: o log registra o DIÁLOGO COMPLETO — pergunta E resposta)
    eventos2, tipos2 = _consumir(
        retomar_fluxo(sessao, "Quero a relação do preco com a origem"))
    assert tipos2[-1] == "final"
    final = eventos2[-1].payload
    assert final["falha_graciosa"] is None     # sem recusa, sem teto
    assert final["resposta"]
    # e a escolha do usuário chegou ao Analista (autoridade do esclarecimento):
    assert "preco com a origem" in llm.prompts[1]


def test_pergunta_do_usuario_abre_o_log(banco_sintetico):
    """V3.5: o PRIMEIRO evento de trace é a pergunta do usuário (papel
    'pergunta') — ela abre o log ao vivo, o terminal e o trace técnico."""
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(1)],
        SqlDoPasso: [SQL_OK],
        ParecerDoAuditor: [ParecerDoAuditor(aprovado=True, problema=None,
                                            instrucao_de_correcao=None,
                                            indice_passo_a_refazer=None)],
        RespostaDeNegocio: [RespostaDeNegocio(
            resposta="Temos 20 pedidos.", premissas_destacadas=[])],
    })
    sessao = criar_sessao(llm=llm)
    eventos, tipos = _consumir(
        executar_em_fluxo(sessao, "Quantos pedidos temos?", banco_sintetico,
                          "pre_setado")
    )
    primeiro = next(e for e in eventos if e.tipo == "trace")
    assert primeiro.payload.no == "pergunta"
    assert primeiro.payload.conteudo == "Quantos pedidos temos?"
    final = eventos[-1].payload
    assert final["trace"][0].no == "pergunta"  # preservada no trace técnico


def test_log_registra_o_dialogo_completo(banco_sintetico):
    """V3.6: o evento [esclarecimento] carrega o PAR (pergunta do Analista
    E resposta do usuário) — o diálogo deixa de ser unilateral no log."""
    esclarecimento = AnaliseDaPergunta(
        precisa_esclarecimento=True,
        pergunta_de_esclarecimento="Prefere preco × data_item ou × origem?",
        passos=[],
    )
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [esclarecimento, _analise(1)],
        SqlDoPasso: [SQL_OK],
        ParecerDoAuditor: [ParecerDoAuditor(aprovado=True, problema=None,
                                            instrucao_de_correcao=None,
                                            indice_passo_a_refazer=None)],
        RespostaDeNegocio: [RespostaDeNegocio(resposta="Ok.",
                                              premissas_destacadas=[])],
    })
    sessao = criar_sessao(llm=llm)
    _consumir(executar_em_fluxo(sessao, "Valor x quantidade de itens?",
                                banco_sintetico, "pre_setado"))
    eventos2, _ = _consumir(retomar_fluxo(sessao, "preco × origem"))
    final = eventos2[-1].payload
    evento_dialogo = next(e for e in final["trace"]
                          if e.no == "esclarecimento")
    assert "[Analista perguntou]" in evento_dialogo.conteudo
    assert "[Usuário respondeu] preco × origem" in evento_dialogo.conteudo
    # e o prompt da 2ª análise recebeu a PERGUNTA EFETIVA:
    assert "PERGUNTA EFETIVA" in llm.prompts[1]
    assert "preco × origem" in llm.prompts[1]


def test_auditor_aprova_apos_esclarecimento_sem_loop(banco_sintetico):
    """V3.6.1 — o caso EXATO do log do 'lucro': o usuário pede algo
    irrespondível (lucro), o Analista oferece alternativas, o usuário ESCOLHE
    a receita por categoria, e o Auditor APROVA a escolha — sem reprovar 14×
    contra a pergunta original e sem teto estourado.

    O auditor falso confirma que recebeu o diálogo: só aprova se o prompt
    tiver sido reframado para a escolha do usuário."""
    class AuditorQueRespeitaODialogo:
        """LLM falso: aprova SE o prompt do auditor foi reframado para a
        escolha do usuário (prova de que o diálogo chegou ao auditor)."""
        def __init__(self):
            self.prompts = []
        def with_structured_output(self, schema):
            externo = self
            class _Inv:
                def invoke(self, prompt):
                    externo.prompts.append((schema.__name__, prompt))
                    if schema is AnaliseDaPergunta:
                        # 1ª: esclarece; 2ª (com diálogo): plano de 1 passo
                        tem_dialogo = "DIÁLOGO DE ESCLARECIMENTO" in prompt
                        if not tem_dialogo:
                            return AnaliseDaPergunta(
                                precisa_esclarecimento=True,
                                pergunta_de_esclarecimento=(
                                    "Não há custos para lucro. Quer receita "
                                    "total, por categoria ou por canal?"),
                                passos=[])
                        return _analise(1)
                    if schema is SqlDoPasso:
                        return SQL_OK
                    if schema is ParecerDoAuditor:
                        # aprova SOMENTE se auditou a ESCOLHA do usuário:
                        auditou_escolha = "PERGUNTA A AUDITAR (efetiva)" in prompt \
                            and "categoria" in prompt
                        return ParecerDoAuditor(
                            aprovado=auditou_escolha,
                            problema=None if auditou_escolha else "lucro!=receita",
                            instrucao_de_correcao=None if auditou_escolha
                            else "calcule o lucro",
                            indice_passo_a_refazer=None if auditou_escolha else 0)
                    if schema is RespostaDeNegocio:
                        return RespostaDeNegocio(
                            resposta="Receita por categoria em 2025.",
                            premissas_destacadas=[])
                    raise AssertionError(schema.__name__)
            return _Inv()
    llm = AuditorQueRespeitaODialogo()
    sessao = criar_sessao(llm=llm)
    _consumir(executar_em_fluxo(sessao, "Qual foi o lucro da empresa em 2025?",
                                banco_sintetico, "pre_setado"))
    eventos2, tipos2 = _consumir(
        retomar_fluxo(sessao, "Receita por categoria de produto em 2025"))
    final = eventos2[-1].payload
    assert tipos2[-1] == "final"
    assert final["falha_graciosa"] is None        # SEM teto estourado
    assert final["resposta"]
    # e o prompt do auditor REALMENTE foi reframado para a escolha:
    prompts_auditor = [p for (nome, p) in llm.prompts
                       if nome == "ParecerDoAuditor"]
    assert prompts_auditor
    assert all("PERGUNTA A AUDITAR (efetiva)" in p for p in prompts_auditor)


def test_pedido_de_grafico_complexo_gera_plano_e_chega_ao_engenheiro(
        banco_sintetico):
    """V3.6.2 — o caso do log da Scatter Polynomial Regression: o tipo de
    gráfico exótico NÃO faz o Analista recusar. Como as colunas dos eixos
    existem, o fluxo segue: gera plano, o Engenheiro monta o SQL, o Executor
    roda — sem teto estourado e sem recusa de escopo."""
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(1)],          # plano de 1 passo (não recusa)
        SqlDoPasso: [SQL_OK],
        ParecerDoAuditor: [ParecerDoAuditor(aprovado=True, problema=None,
                                            instrucao_de_correcao=None,
                                            indice_passo_a_refazer=None)],
        RespostaDeNegocio: [RespostaDeNegocio(
            resposta="Pontos das compras do canal App.",
            premissas_destacadas=[])],
    })
    sessao = criar_sessao(llm=llm)
    eventos, tipos = _consumir(executar_em_fluxo(
        sessao,
        "Faça um Scatter Polynomial Regression das compras do canal App: "
        "eixo X a data, eixo Y o valor. Cada compra um ponto.",
        banco_sintetico, "pre_setado"))
    final = eventos[-1].payload
    assert tipos[-1] == "final"
    assert final["falha_graciosa"] is None         # NÃO recusou por escopo
    nos = {e.payload.no for e in eventos if e.tipo == "trace"}
    assert "engenheiro" in nos                      # o Engenheiro FOI chamado
    assert "executor" in nos


def test_palavra_tabela_forca_tabela_no_modo_agente(banco_sintetico):
    """V3.11 (interceptor determinístico): no modo AGENTE, a palavra 'tabela'
    (ou 'liste') força a tabela ANTES do Designer — o LLM de visualização
    nem é chamado. Resolve o bug das centenas de perguntas com 'liste'/'tabela'
    que falhavam por o Designer ignorar a instrução."""
    from app.estado import PropostaDoDesigner
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(1)],
        SqlDoPasso: [SQL_OK],
        ParecerDoAuditor: [ParecerDoAuditor(aprovado=True, problema=None,
                                            instrucao_de_correcao=None,
                                            indice_passo_a_refazer=None)],
        # NENHUM PropostaDoDesigner roteirizado de propósito: se o Designer
        # fosse chamado, o roteiro esgotaria e o teste falharia. Ele NÃO deve
        # ser chamado.
        RespostaDeNegocio: [RespostaDeNegocio(resposta="Pronto.",
                                              premissas_destacadas=[])],
    })
    sessao = criar_sessao(llm=llm)
    eventos, tipos = _consumir(executar_em_fluxo(
        sessao, "Liste os pedidos em tabela", banco_sintetico, "agente"))
    final = eventos[-1].payload
    assert tipos[-1] == "final"
    espec = final["especificacao_visual"]
    assert espec.tipo == "tabela"
    assert espec.linhas is not None               # dados reais embutidos
    # o evento confirma que foi DETERMINÍSTICO (sem LLM de visualização):
    evento_vis = next(e for e in final["trace"] if e.no == "visualizador")
    assert "determinístico" in evento_vis.conteudo.lower()


def test_modo_agente_sem_tabela_chama_o_designer(banco_sintetico):
    """V3.11: sem gatilho de tabela/lista, o modo agente segue normal — o
    Designer é chamado e autora o gráfico (o interceptor não interfere)."""
    from app.estado import PropostaDoDesigner
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(1)],
        SqlDoPasso: [SQL_OK],
        ParecerDoAuditor: [ParecerDoAuditor(aprovado=True, problema=None,
                                            instrucao_de_correcao=None,
                                            indice_passo_a_refazer=None)],
        PropostaDoDesigner: [PropostaDoDesigner(
            tipo_grafico="bar",
            option_json='{"series": [{"type": "bar", "data": [1]}]}',
            justificativa="Barras por categoria.")],
        RespostaDeNegocio: [RespostaDeNegocio(resposta="Pronto.",
                                              premissas_destacadas=[])],
    })
    sessao = criar_sessao(llm=llm)
    eventos, tipos = _consumir(executar_em_fluxo(
        sessao, "Qual a receita por canal?", banco_sintetico, "agente"))
    final = eventos[-1].payload
    assert tipos[-1] == "final"
    assert final["especificacao_visual"].tipo == "bar"   # Designer atuou


def test_recusa_contextual_sem_selo_de_crud(banco_sintetico):
    """V3.8: quando o Analista recusa por motivo CONTEXTUAL (não escrita),
    a mensagem é o motivo personalizado — SEM o selo 'SOMENTE LEITURA',
    que fica reservado à recusa de segurança do CRUD."""
    recusa = AnaliseDaPergunta(
        precisa_esclarecimento=False, passos=[],
        pedido_fora_de_escopo=True,
        pedido_de_escrita=False,                  # NÃO é escrita
        motivo_fora_de_escopo=(
            "A regressão polinomial pedida exige um recurso estatístico "
            "que não está disponível; posso entregar os pontos da dispersão."),
    )
    llm = LlmRoteirizado({AnaliseDaPergunta: [recusa]})
    sessao = criar_sessao(llm=llm)
    eventos, tipos = _consumir(executar_em_fluxo(
        sessao, "Scatter Polynomial Regression das compras",
        banco_sintetico, "pre_setado"))
    final = eventos[-1].payload
    assert tipos[-1] == "final"
    msg = final["falha_graciosa"]
    assert "SOMENTE LEITURA" not in msg            # selo só para CRUD
    assert "regressão polinomial" in msg           # motivo do contexto corrente
    assert "recomeça do zero" in msg


def test_conclusao_executiva_viaja_ao_payload(banco_sintetico):
    """V3.9: os 2 parágrafos de impactos_e_acoes do Redator chegam intactos
    ao payload final (impactos para o negócio + ações)."""
    llm = LlmRoteirizado({
        AnaliseDaPergunta: [_analise(1)],
        SqlDoPasso: [SQL_OK],
        ParecerDoAuditor: [ParecerDoAuditor(aprovado=True, problema=None,
                                            instrucao_de_correcao=None,
                                            indice_passo_a_refazer=None)],
        RespostaDeNegocio: [RespostaDeNegocio(
            resposta="Há 20 pedidos.",
            premissas_destacadas=["todo o histórico"],
            impactos_e_acoes=[
                "Impacto: o volume concentra-se em poucos canais, o que "
                "expõe a receita a um risco de dependência.",
                "Ação: diversificar a captação e monitorar o canal "
                "dominante para impulsionar resultados com menos risco.",
            ])],
    })
    sessao = criar_sessao(llm=llm)
    eventos, _ = _consumir(executar_em_fluxo(
        sessao, "Quantos pedidos?", banco_sintetico, "pre_setado"))
    final = eventos[-1].payload
    assert len(final["impactos_e_acoes"]) == 2
    assert "Impacto" in final["impactos_e_acoes"][0]
    assert "Ação" in final["impactos_e_acoes"][1]
