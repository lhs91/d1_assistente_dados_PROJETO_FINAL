# -*- coding: utf-8 -*-
"""Testes da interface Streamlit via AppTest, com o MOTOR MOCKADO
(monkeypatch de app.fluxo) — sem navegador, sem Gemini (Marco 4)."""
import pytest

from app.estado import EspecificacaoVisual
from app.fluxo import EventoDeFluxo, SessaoDeFluxo
from app.trace import EventoTrace

pytestmark = pytest.mark.marco4

CAMINHO_APP = "app/interface.py"


def _espec_metrica():
    return EspecificacaoVisual(
        modo="pre_setado", tipo="metrica", option=None,
        valor_metrica="20", rotulo_metrica="total",
        colunas=None, linhas=None, justificativa="um valor",
    )


def _espec_tabela_com_outlier():
    return EspecificacaoVisual(
        modo="pre_setado", tipo="tabela", option=None,
        valor_metrica=None, rotulo_metrica=None,
        colunas=["estado", "receita"],
        linhas=[["SP", 141665], ["SC", 9670], ["PR", 6807],
                ["MG", 5200], ["BA", 4900], ["RS", 5100]],
        justificativa="receita por estado",
    )


def _final(resposta="Há 20 pedidos.", premissas=None):
    return {
        "pergunta": None, "resposta": resposta,
        "premissas": premissas if premissas is not None else ["premissa x"],
        "impactos_e_acoes": ["impacto de teste no negócio",
                             "acao de teste para o negocio"],
        "falha_graciosa": None,
        "resultados": [{"objetivo": "contar pedidos",
                        "sql": "SELECT COUNT(*) AS total FROM pedidos",
                        "colunas": ["total"], "linhas": [[20]],
                        "n_linhas": 1, "truncado": False}],
        "trace": [EventoTrace(no="analista", tipo="plano", conteudo="plano ok")],
        "chamadas_llm": 4, "especificacao_visual": _espec_metrica(),
    }


def _instalar_motor_falso(monkeypatch, roteiro_execucao, roteiro_retomada=None):
    """Substitui o motor: cada chamada consome o próximo roteiro (lista de
    EventoDeFluxo). Registra as chamadas para asserts."""
    import app.fluxo as fluxo_mod
    chamadas = {"executar": [], "retomar": []}

    monkeypatch.setattr(
        fluxo_mod, "criar_sessao",
        lambda llm=None: SessaoDeFluxo(grafo=None, configuracao={}),
    )

    def executar_falso(sessao, pergunta, caminho_banco, modo):
        chamadas["executar"].append({"pergunta": pergunta, "modo": modo})
        yield from roteiro_execucao.pop(0)

    def retomar_falso(sessao, resposta_do_usuario):
        chamadas["retomar"].append(resposta_do_usuario)
        yield from (roteiro_retomada or [[]]).pop(0)

    monkeypatch.setattr(fluxo_mod, "executar_em_fluxo", executar_falso)
    monkeypatch.setattr(fluxo_mod, "retomar_fluxo", retomar_falso)
    return chamadas


def _texto_da_pagina(app) -> str:
    """Concatena os textos visíveis (markdown, texto, erro, info) da página."""
    pedacos = []
    for colecao in (app.markdown, app.text, app.error, app.info, app.caption):
        pedacos.extend(str(elemento.value) for elemento in colecao)
    return "\n".join(pedacos)


def test_app_carrega_com_sidebar(monkeypatch):
    """O app sobe sem erro; título presente; radio com 'agente' e 'pre_setado'."""
    from streamlit.testing.v1 import AppTest
    _instalar_motor_falso(monkeypatch, roteiro_execucao=[])
    app = AppTest.from_file(CAMINHO_APP).run()
    assert not app.exception
    assert any("Assistente Virtual de Dados" in str(t.value) for t in app.title)
    assert app.radio[0].options == ["agente", "pre_setado"]


def test_pergunta_renderiza_resposta_e_premissas(monkeypatch):
    """chat_input → motor mockado emite trace+final → resposta e premissas na tela."""
    from streamlit.testing.v1 import AppTest
    roteiro = [[
        EventoDeFluxo("trace", EventoTrace(no="analista", tipo="plano",
                                           conteudo="plano com 1 passo")),
        EventoDeFluxo("final", _final()),
    ]]
    chamadas = _instalar_motor_falso(monkeypatch, roteiro)
    app = AppTest.from_file(CAMINHO_APP).run()
    app.chat_input[0].set_value("Quantos pedidos?").run()
    texto = _texto_da_pagina(app)
    assert "Há 20 pedidos." in texto
    assert "premissa x" in texto
    assert chamadas["executar"][0]["pergunta"] == "Quantos pedidos?"


def test_interrupt_vira_mensagem_e_proximo_input_retoma(monkeypatch):
    """Motor emite 'interrupt' → a pergunta vira mensagem; o próximo input
    chama retomar_fluxo (não nova pergunta) e conclui."""
    from streamlit.testing.v1 import AppTest
    roteiro_execucao = [[EventoDeFluxo("interrupt", "Qual período?")]]
    roteiro_retomada = [[EventoDeFluxo("final", _final("Concluído após esclarecer."))]]
    chamadas = _instalar_motor_falso(monkeypatch, roteiro_execucao, roteiro_retomada)

    app = AppTest.from_file(CAMINHO_APP).run()
    app.chat_input[0].set_value("Como foi o desempenho?").run()
    assert "Qual período?" in _texto_da_pagina(app)      # a pergunta do Analista

    app.chat_input[0].set_value("todo período").run()
    assert chamadas["retomar"] == ["todo período"]       # foi RESUME, não pergunta
    assert len(chamadas["executar"]) == 1
    assert "Concluído após esclarecer." in _texto_da_pagina(app)


def test_nova_pergunta_apaga_a_conversa_anterior(monkeypatch):
    """V3.1 (decisão do dev): ao enviar uma PERGUNTA NOVA, tudo da conversa
    anterior é apagado automaticamente — só a pergunta corrente fica na tela."""
    from streamlit.testing.v1 import AppTest
    roteiro = [
        [EventoDeFluxo("final", _final("Resposta UM."))],
        [EventoDeFluxo("final", _final("Resposta DOIS."))],
    ]
    _instalar_motor_falso(monkeypatch, roteiro)
    app = AppTest.from_file(CAMINHO_APP).run()
    app.chat_input[0].set_value("Pergunta A?").run()
    app.chat_input[0].set_value("Pergunta B?").run()
    texto = _texto_da_pagina(app)
    assert "Resposta DOIS." in texto
    assert "Resposta UM." not in texto          # a anterior foi apagada
    assert "Pergunta A?" not in texto


def test_expander_tecnico_presente(monkeypatch):
    """Após a resposta, existe o expander 'como cheguei aqui' com o trace."""
    from streamlit.testing.v1 import AppTest
    _instalar_motor_falso(monkeypatch, [[EventoDeFluxo("final", _final())]])
    app = AppTest.from_file(CAMINHO_APP).run()
    app.chat_input[0].set_value("Quantos pedidos?").run()
    rotulos = [str(e.label) for e in app.expander]
    assert any("como cheguei aqui" in r for r in rotulos)
    conteudos = "\n".join(str(c.value) for e in app.expander for c in e.code)
    assert "plano ok" in conteudos


def test_trace_persiste_no_historico_apos_rerun(monkeypatch):
    """O raciocínio nó-a-nó PERSISTE junto da resposta no histórico (não some
    após o rerun): o conteúdo dos eventos do trace aparece na tela mesmo depois
    de uma SEGUNDA pergunta ter sido feita."""
    from streamlit.testing.v1 import AppTest
    roteiro = [
        [EventoDeFluxo("final", _final("Resposta UM."))],
        [EventoDeFluxo("final", _final("Resposta DOIS."))],
    ]
    _instalar_motor_falso(monkeypatch, roteiro)
    app = AppTest.from_file(CAMINHO_APP).run()
    app.chat_input[0].set_value("Pergunta A?").run()
    app.chat_input[0].set_value("Pergunta B?").run()
    # 'plano ok' é o conteúdo do EventoTrace de cada resposta; deve aparecer
    # renderizado (markdown colorido) para AMBAS, vindo do histórico.
    texto = _texto_da_pagina(app)
    assert texto.count("plano ok") >= 2
    rotulos = [str(e.label) for e in app.expander]
    assert any("passo a passo" in r for r in rotulos)


def test_caminho_do_grafo_apenas_da_pergunta_corrente(monkeypatch):
    """V3.1: o diagrama do caminho existe para a pergunta CORRENTE; com a
    limpeza automática, a pergunta nova apaga o diagrama da anterior."""
    from streamlit.testing.v1 import AppTest
    roteiro = [
        [EventoDeFluxo("final", _final("Resposta UM."))],
        [EventoDeFluxo("final", _final("Resposta DOIS."))],
    ]
    _instalar_motor_falso(monkeypatch, roteiro)
    app = AppTest.from_file(CAMINHO_APP).run()
    app.chat_input[0].set_value("Pergunta A?").run()
    app.chat_input[0].set_value("Pergunta B?").run()
    rotulos = [str(e.label) for e in app.expander]
    assert sum("Caminho no grafo" in r for r in rotulos) == 1
    assert 'data-no="analista"' in _texto_da_pagina(app)


def test_ordem_iteracao_resposta_e_diagrama(monkeypatch):
    """Garantia do M5 (fluxo natural): a ITERAÇÃO dos agentes vem ANTES da
    resposta, e o diagrama do caminho vem DEPOIS dela."""
    from streamlit.testing.v1 import AppTest
    _instalar_motor_falso(monkeypatch, [[EventoDeFluxo("final", _final())]])
    app = AppTest.from_file(CAMINHO_APP).run()
    app.chat_input[0].set_value("Quantos pedidos?").run()
    pagina = _texto_da_pagina(app)
    # a resposta (st.text), o log do agente e o diagrama estão todos na página
    assert "Há 20 pedidos." in pagina           # resposta renderizada
    assert "plano ok" in pagina                 # log da iteração
    # a ordem visual essencial: o gráfico (SVG) vem DEPOIS do log do agente
    markdown = "\n".join(str(m.value) for m in app.markdown)
    assert markdown.index("plano ok") < markdown.index("<svg")


def test_v3_sem_botoes_limpar_e_proximo(monkeypatch):
    """V3/V3.4: 'Limpar conversa', 'Próximo' e 'Reiniciar' foram EXCLUÍDOS;
    o replay tem só o Reproduzir (anima no PRIMEIRO clique, via on_click)."""
    from streamlit.testing.v1 import AppTest
    _instalar_motor_falso(monkeypatch, [[EventoDeFluxo("final", _final())]])
    app = AppTest.from_file(CAMINHO_APP).run()
    app.chat_input[0].set_value("Quantos pedidos?").run()
    rotulos = [str(b.label) for b in app.button]
    chaves = [str(b.key) for b in app.button]
    assert not any("Limpar" in r for r in rotulos)
    assert not any("Próximo" in r for r in rotulos)
    assert not any("replay_prox" in c for c in chaves)
    assert not any("replay_zero" in c for c in chaves)   # V3.4: Reiniciar excluído
    assert any("replay_play" in c for c in chaves)


def test_v3_reproduzir_anima_sem_erro(monkeypatch):
    """V3: o Reproduzir anima o caminho (modo ativo) e termina na trilha
    completa, sem exceção."""
    from streamlit.testing.v1 import AppTest
    _instalar_motor_falso(monkeypatch, [[EventoDeFluxo("final", _final())]])
    app = AppTest.from_file(CAMINHO_APP).run()
    app.chat_input[0].set_value("Quantos pedidos?").run()
    botao = next(b for b in app.button if b.key == "replay_play_0")
    botao.click().run()
    assert not app.exception
    assert "<svg" in _texto_da_pagina(app)


def test_v3_logo_oficial_na_sidebar(monkeypatch):
    """V3: a logo OFICIAL (app/recursos/franq-logo.svg) está embutida na
    sidebar — reconhecida por uma assinatura única do arquivo."""
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    oficial = (Path(CAMINHO_APP).parent / "recursos" / "franq-logo.svg")
    assert oficial.exists()
    assinatura = 'width="81" height="80"'        # dimensões únicas da oficial
    assert assinatura in oficial.read_text(encoding="utf-8")
    _instalar_motor_falso(monkeypatch, [[EventoDeFluxo("final", _final())]])
    app = AppTest.from_file(CAMINHO_APP).run()
    sidebar_md = " ".join(str(m.value) for m in app.sidebar.markdown)
    assert assinatura in sidebar_md


def test_v35_reproduzir_anima_no_primeiro_clique_sem_pendencia(monkeypatch):
    """V3.5 (bug dos múltiplos cliques): UM clique no Reproduzir consome o
    pedido NO MESMO ciclo (nada fica pendente para um próximo rerun) e o
    diagrama é renderizado — sem depender de cliques extras."""
    from streamlit.testing.v1 import AppTest
    _instalar_motor_falso(monkeypatch, [[EventoDeFluxo("final", _final())]])
    app = AppTest.from_file(CAMINHO_APP).run()
    app.chat_input[0].set_value("Quantos pedidos?").run()
    botao = next(b for b in app.button if b.key == "replay_play_0")
    botao.click().run()                       # UM clique
    assert not app.exception
    # o pedido foi consumido NESTE ciclo — a chave não persiste no estado:
    assert "replay_pedido_0" not in app.session_state
    assert "<svg" in _texto_da_pagina(app)


def test_v32_ancora_do_grafico_e_flag_consumida(monkeypatch):
    """V3.2: a resposta final planta a âncora do gráfico e a flag de foco é
    CONSUMIDA no mesmo rerun (rola uma vez só)."""
    from streamlit.testing.v1 import AppTest
    _instalar_motor_falso(monkeypatch, [[EventoDeFluxo("final", _final())]])
    app = AppTest.from_file(CAMINHO_APP).run()
    app.chat_input[0].set_value("Quantos pedidos?").run()
    assert 'id="grafico-da-resposta-0"' in _texto_da_pagina(app)
    assert app.session_state["focar_no_grafico"] is False


def test_v32_replay_nao_refoca_o_grafico(monkeypatch):
    """V3.2: reruns posteriores (ex.: replay) NÃO rolam de novo — a flag
    permanece consumida e nada quebra."""
    from streamlit.testing.v1 import AppTest
    _instalar_motor_falso(monkeypatch, [[EventoDeFluxo("final", _final())]])
    app = AppTest.from_file(CAMINHO_APP).run()
    app.chat_input[0].set_value("Quantos pedidos?").run()
    botao = next(b for b in app.button if b.key == "replay_play_0")
    botao.click().run()
    assert not app.exception
    assert app.session_state["focar_no_grafico"] is False


def test_v33_foco_na_regiao_da_iteracao():
    """V3.3 (correção do pedido): a âncora do foco é plantada NA REGIÃO DA
    ITERAÇÃO (dentro de _consumir_gerador, antes do split) e a rolagem vem
    em seguida — travado na fonte (o run intermediário é descartado)."""
    from pathlib import Path
    fonte = Path(CAMINHO_APP).read_text(encoding="utf-8")
    consumidor = fonte.index("def _consumir_gerador")
    ancora = fonte.index("_ancora(_ANCORA_INICIO)")
    rolagem = fonte.index("_rolar_para(_ANCORA_INICIO)")
    split = fonte.index("col_grafo, col_log = st.columns(2)")
    assert consumidor < ancora < rolagem < split
    assert "scrollIntoView" in fonte




def test_v34_botao_sql_alterna_as_consultas(monkeypatch):
    """V3.4: o botão 'Consultas SQL' (vermelho claro via CSS st-key) alterna
    a região; após UM clique as consultas aparecem, copiáveis."""
    from streamlit.testing.v1 import AppTest
    _instalar_motor_falso(monkeypatch, [[EventoDeFluxo("final", _final())]])
    app = AppTest.from_file(CAMINHO_APP).run()
    app.chat_input[0].set_value("Quantos pedidos?").run()
    botao = next(b for b in app.button if b.key == "sql_btn_0")
    assert "Consultas SQL" in str(botao.label)
    botao.click().run()
    codigos = " ".join(str(c.value) for c in app.code)
    assert "SELECT COUNT(*) AS total FROM pedidos" in codigos
    # e o CSS do vermelho claro está aplicado na fonte:
    from pathlib import Path
    fonte = Path(CAMINHO_APP).read_text(encoding="utf-8")
    assert "st-key-sql_btn" in fonte and "#FDECEA" in fonte




def test_v310_conclusao_titulo_negrito_corpo_sem_caps(monkeypatch):
    """V3.10: o TÍTULO da conclusão aparece (em negrito); os parágrafos são
    renderizados como o Redator os escreveu — SEM forçar CAIXA ALTA no corpo
    (o .upper() foi removido)."""
    from streamlit.testing.v1 import AppTest
    _instalar_motor_falso(monkeypatch, [[EventoDeFluxo("final", _final())]])
    app = AppTest.from_file(CAMINHO_APP).run()
    app.chat_input[0].set_value("Quantos pedidos?").run()
    pagina = _texto_da_pagina(app)
    assert "IMPACTOS PARA O NEGÓCIO E AÇÕES A SEREM REALIZADAS" in pagina
    # o corpo do parágrafo NÃO é mais forçado a maiúsculas:
    assert "impacto de teste no negócio" in pagina
    assert "IMPACTO DE TESTE NO NEGÓCIO" not in pagina


def test_v312_tabela_destaca_linha_de_outlier(monkeypatch):
    """V3.12: numa tabela com um valor fora do padrão (|z|>2), a interface
    pinta a linha do outlier e exibe a legenda explicativa — sem exceção."""
    from streamlit.testing.v1 import AppTest
    final = _final()
    final["especificacao_visual"] = _espec_tabela_com_outlier()
    _instalar_motor_falso(monkeypatch, [[EventoDeFluxo("final", final)]])
    app = AppTest.from_file(CAMINHO_APP).run()
    app.chat_input[0].set_value("Receita por estado em tabela").run()
    assert not app.exception
    pagina = _texto_da_pagina(app)
    assert "fora do padrão" in pagina            # legenda do destaque


def test_v312_tabela_sem_outlier_nao_mostra_legenda(monkeypatch):
    """V3.12: tabela com dados equilibrados não pinta nada nem mostra a
    legenda de outlier (sem falso positivo)."""
    from streamlit.testing.v1 import AppTest
    final = _final()
    final["especificacao_visual"] = EspecificacaoVisual(
        modo="pre_setado", tipo="tabela", option=None,
        valor_metrica=None, rotulo_metrica=None,
        colunas=["mes", "vendas"],
        linhas=[["jan", 100], ["fev", 102], ["mar", 98],
                ["abr", 101], ["mai", 99]],
        justificativa="vendas por mês",
    )
    _instalar_motor_falso(monkeypatch, [[EventoDeFluxo("final", final)]])
    app = AppTest.from_file(CAMINHO_APP).run()
    app.chat_input[0].set_value("Vendas por mês em tabela").run()
    assert not app.exception
    assert "fora do padrão" not in _texto_da_pagina(app)
