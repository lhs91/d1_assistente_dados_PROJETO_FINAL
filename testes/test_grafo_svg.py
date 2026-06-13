# -*- coding: utf-8 -*-
"""Testes da visualização dinâmica do grafo (Marco 5) — caminho_percorrido
é PURA; o SVG é string. Tudo sem Streamlit e sem Gemini."""
import pytest

from app.trace import EventoTrace
from app.visualizacao.grafo_svg import (
    ARESTAS_DO_GRAFO,
    NOS_DO_GRAFO,
    caminho_percorrido,
    montar_svg_do_grafo,
    total_de_passos,
)

pytestmark = pytest.mark.marco5


def _ev(no, conteudo="x"):
    return EventoTrace(no=no, tipo="info", conteudo=conteudo)


CAMINHO_RETO = [
    _ev("perfilador"), _ev("analista"), _ev("engenheiro"), _ev("guardrail"),
    _ev("executor"), _ev("auditor"), _ev("visualizador"), _ev("redator"),
]


def test_caminho_reto():
    """Caminho feliz: a sequência segue o trilho principal, sem repetições."""
    caminho = caminho_percorrido(CAMINHO_RETO)
    assert caminho.sequencia_nos == [
        "perfilador", "analista", "engenheiro", "guardrail",
        "executor", "auditor", "visualizador", "redator",
    ]
    assert ("perfilador", "analista") in caminho.arestas
    assert ("visualizador", "redator") in caminho.arestas


def test_caminho_com_loop_sintatico():
    """Duas reprovas do guardrail: o engenheiro REPETE na sequência e a
    aresta de retorno guardrail→engenheiro consta como percorrida."""
    trace = [
        _ev("perfilador"), _ev("analista"),
        _ev("engenheiro"), _ev("guardrail"),     # reprova 1
        _ev("engenheiro"), _ev("guardrail"),     # reprova 2
        _ev("engenheiro"), _ev("guardrail"), _ev("executor"),
    ]
    caminho = caminho_percorrido(trace)
    assert caminho.sequencia_nos.count("engenheiro") == 3
    assert ("guardrail", "engenheiro") in caminho.arestas


def test_caminho_com_interrupt():
    """O ramo analista→esclarecimento→analista aparece na sequência."""
    trace = [
        _ev("perfilador"), _ev("analista"), _ev("esclarecimento"),
        _ev("analista"), _ev("engenheiro"),
    ]
    caminho = caminho_percorrido(trace)
    assert caminho.sequencia_nos[:4] == [
        "perfilador", "analista", "esclarecimento", "analista",
    ]
    assert ("analista", "esclarecimento") in caminho.arestas
    assert ("esclarecimento", "analista") in caminho.arestas


def test_caminho_com_falha_graciosa():
    """Trace que termina em falha: falha_graciosa é o nó atual; sem redator."""
    trace = [_ev("perfilador"), _ev("analista"), _ev("falha_graciosa")]
    caminho = caminho_percorrido(trace)
    assert caminho.no_atual == "falha_graciosa"
    assert "redator" not in caminho.sequencia_nos


def test_no_atual_e_o_ultimo():
    """no_atual reflete o último nó do trace (parcial ao vivo)."""
    caminho = caminho_percorrido(CAMINHO_RETO[:5])
    assert caminho.no_atual == "executor"


def test_ate_passo_limita_o_caminho():
    """ate_passo=k corta o caminho nos k primeiros passos (base do replay)."""
    caminho = caminho_percorrido(CAMINHO_RETO, ate_passo=3)
    assert caminho.sequencia_nos == ["perfilador", "analista", "engenheiro"]
    assert caminho.no_atual == "engenheiro"
    assert caminho_percorrido(CAMINHO_RETO, ate_passo=0).no_atual is None


def test_eventos_repetidos_do_mesmo_no_contam_uma_vez():
    """Vários eventos seguidos do mesmo nó = UM passo (nós registram N eventos)."""
    trace = [_ev("analista"), _ev("analista", "premissa"), _ev("analista", "plano"),
             _ev("engenheiro")]
    caminho = caminho_percorrido(trace)
    assert caminho.sequencia_nos == ["analista", "engenheiro"]
    assert total_de_passos(trace) == 2


def test_svg_marca_no_ativo_e_visitados():
    """O SVG do passo atual marca 'no-ativo' no nó certo, 'no-visitado' nos
    anteriores e 'no-inativo' nos não-alcançados."""
    caminho = caminho_percorrido(CAMINHO_RETO, ate_passo=3)
    svg = montar_svg_do_grafo(caminho)
    assert 'class="no-ativo" data-no="engenheiro"' in svg
    assert 'class="no-visitado" data-no="analista"' in svg
    assert 'class="no-inativo" data-no="redator"' in svg
    assert 'class="aresta-pulsando"' in svg          # a aresta do passo atual


def test_svg_nao_contem_script():
    """Markup estático seguro: o SVG jamais contém script ou handlers."""
    svg = montar_svg_do_grafo(caminho_percorrido(CAMINHO_RETO))
    assert "<script" not in svg.lower()
    assert "onclick" not in svg.lower()
    assert "javascript:" not in svg.lower()


def test_topologia_casa_com_grafo_real():
    """TODO nó da topologia existe no grafo compilado e vice-versa (impede
    divergência silenciosa se o grafo mudar). 'esclarecimento' (nome do
    trace) traduz para o nó 'esclarecer' do grafo."""
    from app.grafo import construir_grafo
    traducao = {"esclarecimento": "esclarecer"}
    ids_topologia = {traducao.get(n.id, n.id) for n in NOS_DO_GRAFO}
    grafo = construir_grafo(llm=object())          # estrutura; LLM nunca chamado
    ids_reais = {n for n in grafo.get_graph().nodes if not n.startswith("__")}
    assert ids_topologia == ids_reais
    # E toda aresta da topologia liga nós existentes:
    for aresta in ARESTAS_DO_GRAFO:
        assert traducao.get(aresta.origem, aresta.origem) in ids_reais
        assert traducao.get(aresta.destino, aresta.destino) in ids_reais


def test_retornos_sempre_em_amarelo_mostarda():
    """As arestas de RETORNO (autocorreção) aparecem em mostarda mesmo
    quando NÃO percorridas — são a assinatura visual do sistema."""
    from app.visualizacao.grafo_svg import COR_MOSTARDA
    svg = montar_svg_do_grafo(caminho_percorrido([_ev("perfilador")]))
    assert svg.count(COR_MOSTARDA) >= 4          # 4 retornos na topologia


def test_modo_ativo_deixa_visitados_cinza():
    """No modo 'ativo' (tempo real), SÓ o nó corrente fica colorido; os já
    visitados ficam cinza (marcados como visitado-cinza)."""
    caminho = caminho_percorrido(CAMINHO_RETO, ate_passo=3)
    svg = montar_svg_do_grafo(caminho, modo="ativo")
    assert 'class="no-ativo" data-no="engenheiro"' in svg
    assert 'class="no-visitado-cinza" data-no="analista"' in svg
    assert 'class="no-visitado"' not in svg.replace("no-visitado-cinza", "")


def test_rotulos_teto_estourado_condicionais_e_guardrail_interno():
    """O diagrama usa a nomenclatura do projeto: 'teto estourado' (não
    'falha graciosa'), rótulos das condicionais nas arestas e a anotação do
    guardrail de visualização interno ao visualizador."""
    svg = montar_svg_do_grafo(caminho_percorrido([_ev("perfilador")]))
    assert "teto estourado" in svg
    assert "falha graciosa" not in svg
    for condicao in ("ambígua?", "reprovado", "aprovado", "devolvido"):
        assert condicao in svg
    assert "guardrail de visualização" in svg


def test_v3_retornos_sao_linhas_laterais():
    """V3 (padrão do diagrama ASCII): os retornos correm por CANAIS laterais
    (polilinhas), não por linhas retas sobrepostas ao fluxo principal."""
    svg = montar_svg_do_grafo(caminho_percorrido([_ev("perfilador")]))
    assert svg.count("<polyline") >= 4           # 3 retornos + ramo do teto


def test_v3_diagrama_compacto_cabe_na_janela():
    """V3: o viewBox é compacto (altura <= 480) e o SVG limita a própria
    altura (max-height) — cabe integralmente numa janela maximizada."""
    svg = montar_svg_do_grafo(caminho_percorrido([_ev("perfilador")]))
    import re
    altura = int(re.search(r'viewBox="0 0 \d+ (\d+)"', svg).group(1))
    assert altura <= 480
    assert "max-height" in svg


def test_v3_docstring_do_grafo_revisada():
    """V3 (item 8): o diagrama ASCII do grafo.py foi corrigido — inclui o
    visualizador (faltava) e o teto estourado."""
    import app.grafo as modulo
    assert "visualizador" in modulo.__doc__
    assert "teto estourado" in modulo.__doc__


def test_v33_aresta_engenheiro_guardrail_tem_sinalizador():
    """V3.3: a saída do engenheiro para o guardrail é rotulada 'sql proposto'."""
    svg = montar_svg_do_grafo(caminho_percorrido([_ev("perfilador")]))
    assert "sql proposto" in svg


def test_v33_tempo_por_agente_somado_e_exibido():
    """V3.3: caminho_percorrido soma os tempo_ms por nó e o SVG exibe o
    contador (ex.: '1.5s') junto dos nós visitados."""
    trace = [
        EventoTrace(no="perfilador", tipo="info", conteudo="x", tempo_ms=300.0),
        EventoTrace(no="analista", tipo="plano", conteudo="x", tempo_ms=1000.0),
        EventoTrace(no="analista", tipo="premissa", conteudo="x", tempo_ms=500.0),
        EventoTrace(no="engenheiro", tipo="sql_proposto", conteudo="x"),
    ]
    caminho = caminho_percorrido(trace)
    assert caminho.tempos_ms["analista"] == 1500.0
    svg = montar_svg_do_grafo(caminho)
    assert "1.5s" in svg and "300ms" in svg
    assert 'class="tempo-do-no"' in svg


def test_v34_flags_conceituais_dentro_das_caixas():
    """V3.4: cada caixa carrega a flag do que ela é — AGENTE · LLM,
    DETERMINÍSTICO ou HUMANO · interrupt."""
    svg = montar_svg_do_grafo(caminho_percorrido([_ev("perfilador")]))
    assert svg.count("AGENTE · LLM") == 5          # analista, engenheiro,
    assert svg.count("DETERMINÍSTICO") == 4        # auditor, visualizador,
    assert "HUMANO · interrupt" in svg             # redator
    assert 'class="flag-do-no"' in svg


def test_v34_tokens_somados_e_exibidos_na_caixa():
    """V3.4: caminho_percorrido soma os tokens por nó e o SVG exibe
    'Xs · Y tk' dentro da caixa."""
    trace = [
        EventoTrace(no="analista", tipo="plano", conteudo="x",
                    tempo_ms=1500.0, tokens=312),
        EventoTrace(no="engenheiro", tipo="sql_proposto", conteudo="x",
                    tokens=88),
    ]
    caminho = caminho_percorrido(trace)
    assert caminho.tokens == {"analista": 312, "engenheiro": 88}
    svg = montar_svg_do_grafo(caminho)
    assert "1.5s · 312 tk" in svg
    assert "88 tk" in svg


def test_v35_anotacao_alinhada_com_o_visualizador():
    """V3.5: a linha entre o visualizador e a anotação do guardrail de
    visualização é HORIZONTAL (y1 == y2) e os centros coincidem."""
    import re
    svg = montar_svg_do_grafo(caminho_percorrido([_ev("perfilador")]))
    anotacao = svg.split('class="anotacao-guardrail-visual"')[1]
    ret = re.search(r'<rect x="([\d.]+)" y="([\d.]+)" width="200" '
                    r'height="36"', anotacao)
    linha = re.search(r'<line x1="[\d.]+" y1="([\d.]+)" x2="[\d.]+" '
                      r'y2="([\d.]+)"', svg.split("anotacao-guardrail")[1])
    assert linha.group(1) == linha.group(2)              # horizontal
    centro_anotacao = float(ret.group(2)) + 18
    assert abs(centro_anotacao - float(linha.group(1))) < 0.01


def _ev2(no, conteudo, tipo="info"):
    return EventoTrace(no=no, tipo=tipo, conteudo=conteudo)


def test_v38_ao_vivo_destaca_quem_esta_rodando_nao_quem_concluiu():
    """V3.8 (caso da imagem do fogo): auditor APROVOU e o visualizador está
    rodando → ao vivo, o ATIVO é o visualizador; o auditor fica visitado
    (cinza), mantendo tempo/tokens na caixa."""
    trace = [
        _ev2("perfilador", "Dossiê pronto"),
        _ev2("analista", "Plano com 1 passo(s): obter compras", tipo="plano"),
        _ev2("engenheiro", "Passo 1, tentativa 1", tipo="sql_proposto"),
        _ev2("guardrail", "Consulta aprovada pelo Guardrail."),
        _ev2("executor", "Passo 1 concluído: 946 linha(s).", tipo="resultado"),
        EventoTrace(no="auditor", tipo="parecer",
                    conteudo="Auditoria APROVADA: os resultados respondem.",
                    tempo_ms=6900.0),
    ]
    caminho = caminho_percorrido(trace, em_execucao=True)
    assert caminho.no_atual == "visualizador"          # quem RODA agora
    assert "auditor" in caminho.sequencia_nos          # concluído: visitado
    svg = montar_svg_do_grafo(caminho, modo="ativo")
    assert "6.9s" in svg                               # tempo segue na caixa
    # sem em_execucao (replay/histórico), o comportamento antigo permanece:
    assert caminho_percorrido(trace).no_atual == "auditor"


def test_v38_inferencia_cobre_as_condicionais_do_grafo():
    """V3.8: a inferência do nó em execução segue as MESMAS condições das
    arestas — aprovações avançam, reprovações voltam ao engenheiro, plano
    com passos restantes volta ao engenheiro."""
    from app.visualizacao.grafo_svg import _no_em_execucao
    aprovou = _ev2("guardrail", "Consulta aprovada pelo Guardrail.")
    reprovou_g = _ev2("guardrail", "Consulta REPROVADA: DDL proibido.")
    assert _no_em_execucao([aprovou]) == "executor"
    assert _no_em_execucao([reprovou_g]) == "engenheiro"
    devolveu = EventoTrace(no="auditor", tipo="parecer",
                           conteudo="Auditoria REPROVADA (devolução 1): x")
    assert _no_em_execucao([devolveu]) == "engenheiro"
    # plano de 2 passos, 1 concluído → engenheiro; 2 concluídos → auditor
    plano2 = _ev2("analista", "Plano com 2 passo(s): a; b", tipo="plano")
    passo1 = _ev2("executor", "Passo 1 concluído: 5 linha(s).")
    passo2 = _ev2("executor", "Passo 2 concluído: 3 linha(s).")
    assert _no_em_execucao([plano2, passo1]) == "engenheiro"
    assert _no_em_execucao([plano2, passo1, passo2]) == "auditor"
    assert _no_em_execucao([_ev2("pergunta", "Qual...")]) == "perfilador"
    assert _no_em_execucao([_ev2("visualizador", "Option aprovado")]) == "redator"


def test_v311_diagrama_exibe_diretor():
    """V3.11: a caixa do nó redator exibe 'Diretor' (rótulo), com id interno
    'redator' preservado na topologia."""
    svg = montar_svg_do_grafo(caminho_percorrido([_ev("perfilador")]))
    assert ">diretor<" in svg
    # id interno permanece nas arestas/cores (topologia intacta):
    from app.visualizacao.grafo_svg import ARESTAS_DO_GRAFO
    assert any(a.destino == "redator" for a in ARESTAS_DO_GRAFO)
