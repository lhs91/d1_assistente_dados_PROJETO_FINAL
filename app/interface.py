# -*- coding: utf-8 -*-
"""
interface.py — A interface Streamlit (Marcos 4 e 5): casca fina sobre o motor.

Rodar: streamlit run app/interface.py   (da raiz do projeto; .env com a chave)

ORDEM DE CADA MENSAGEM (decisão do M5 — o fluxo natural da informação):
  1. pergunta do usuário;
  2. ITERAÇÃO DOS AGENTES (raciocínio nó-a-nó, persistente, aberto);
  3. trace técnico (texto puro, fechado);
  4. resposta de negócio + premissas;
  5. GRÁFICO (st_echarts/métrica/tabela) — sempre APÓS a iteração;
  6. CAMINHO NO GRAFO (diagrama SVG + replay) — a visualização dinâmica do M5.

Tudo PERSISTE no histórico (mensagens, logs, gráficos e diagramas de TODAS as
perguntas anteriores) — re-renderizado a cada rerun a partir do session_state.

Identidade visual: sidebar na cor FRANQ (#6c7ce3) com a logo no topo.

Segurança herdada: st_echarts recebe DICT PURO (option validado pelo Guardrail
de Visualização); o SVG do grafo é markup estático nosso, sem <script>;
o mecanismo JsCode jamais é importado no projeto.
"""
import sys
import time
from pathlib import Path

# O 'streamlit run app/interface.py' coloca a pasta app/ no sys.path — não a
# raiz do projeto —, então 'from app import ...' falharia. Garantimos a raiz
# (o diretório-pai de app/) no path ANTES de importar o pacote.
_RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(_RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(_RAIZ_DO_PROJETO))

import streamlit as st

from app import fluxo
from app.config import (
    ALTURA_GRAFICO_UI,
    CAMINHO_BANCO_PADRAO,
    MODO_VISUALIZACAO_PADRAO,
    PROJETO_LANGSMITH,
    TITULO_DA_INTERFACE,
    configurar_langsmith,
)
from app.trace import renderizar_trace
from app.visualizacao.grafo_svg import (
    caminho_percorrido,
    montar_svg_do_grafo,
    total_de_passos,
)
from app.visualizacao.render_streamlit import decidir_renderizacao

# ── Identidade FRANQ ─────────────────────────────────────────────────────────
COR_FRANQ = "#6c7ce3"

_CSS_FRANQ = f"""
<style>
[data-testid="stSidebar"] {{ background-color: {COR_FRANQ}; }}
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label,
[data-testid="stSidebar"] span, [data-testid="stSidebar"] div,
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{ color: #ffffff; }}
[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.35); }}
[data-testid="stSidebar"] button {{
    background-color: #ffffff !important;
    border: 1px solid #ffffff !important;
}}
[data-testid="stSidebar"] button p {{
    color: {COR_FRANQ} !important;
    font-weight: 700;
}}
[class*="st-key-sql_btn"] button {{
    background-color: #FDECEA !important;
    border: 1px solid #F2B8B5 !important;
}}
[class*="st-key-sql_btn"] button p {{
    color: #A32D2D !important;
    font-weight: 600;
}}
</style>
"""

def _carregar_logo_oficial() -> str | None:
    """Lê a logo SVG oficial da FRANQ de app/recursos (enviada pelo dev)."""
    caminho = Path(__file__).resolve().parent / "recursos" / "franq-logo.svg"
    if not caminho.exists():
        return None
    svg = caminho.read_text(encoding="utf-8")
    return (
        '<div style="text-align:center;padding:6px 0 14px 0;">'
        '<div style="display:inline-block;border-radius:14px;overflow:hidden;'
        'line-height:0;">' + svg + "</div></div>"
    )


_LOGO_RESERVA = """
<div style="text-align:center;padding:6px 0 14px 0;">
<svg width="170" height="48" viewBox="0 0 170 48" xmlns="http://www.w3.org/2000/svg" role="img">
  <title>FRANQ</title>
  <g stroke="#ffffff" stroke-width="1.4" opacity="0.9">
    <line x1="14" y1="14" x2="30" y2="26"/><line x1="30" y1="26" x2="16" y2="36"/>
    <line x1="30" y1="26" x2="42" y2="12"/>
  </g>
  <g fill="#ffffff">
    <circle cx="14" cy="14" r="4"/><circle cx="30" cy="26" r="5.5"/>
    <circle cx="16" cy="36" r="3.5"/><circle cx="42" cy="12" r="3.5"/>
  </g>
  <text x="56" y="32" font-family="Arial, sans-serif" font-size="24"
        font-weight="700" fill="#ffffff" letter-spacing="2">FRANQ</text>
</svg>
</div>
"""
_LOGO_FRANQ = _carregar_logo_oficial() or _LOGO_RESERVA

# Papel → cor (mesma lógica do terminal, adaptada à paleta do Streamlit).
_COR_STREAMLIT = {
    "perfilador": "gray",
    "analista": "blue",
    "esclarecimento": "orange",
    "engenheiro": "violet",
    "guardrail": "orange",
    "executor": "green",
    "auditor": "red",
    "visualizador": "rainbow",
    "redator": "green",
    "falha_graciosa": "red",
}
_TIPOS_DE_ERRO = {"sql_reprovado", "sql_erro", "falha_graciosa", "visual_reprovado"}

# Âncoras de foco automático (V3.2): a tela rola sozinha para o ponto certo.
_ANCORA_INICIO = "inicio-da-iteracao"      # topo da iteração dos agentes
_ANCORA_GRAFICO = "grafico-da-resposta"    # o gráfico da resposta final


def _rolar_para(ancora: str) -> None:
    """Rola a janela suavemente até a âncora. Este JavaScript é NOSSO —
    estático, de controle da interface — e não tem relação com o option do
    ECharts, que segue proibido de conter qualquer código executável."""
    js = (
        f'<script>const alvo = window.parent.document.getElementById('
        f'"{ancora}"); if (alvo) {{ alvo.scrollIntoView('
        f'{{behavior: "smooth", block: "start"}}); }}</script>'
    )
    try:
        st.iframe(srcdoc=js, height=0)        # API nova (1.58+ depreciou o html)
    except (AttributeError, TypeError):
        import streamlit.components.v1 as components
        components.html(js, height=0)



def _ancora(nome: str) -> None:
    """Planta a âncora invisível no ponto atual da página."""
    st.markdown(f'<div id="{nome}"></div>', unsafe_allow_html=True)


def _cor_streamlit(no: str) -> str:
    """Cor da paleta do Streamlit para o nó (cinza para desconhecidos)."""
    return _COR_STREAMLIT.get(no, "gray")


def _linha_de_trace(evento) -> str:
    """Uma linha colorida de trace: nó na cor do papel; erro em vermelho."""
    cor = "red" if evento.tipo in _TIPOS_DE_ERRO else _cor_streamlit(evento.no)
    from app.cores import rotulo_do_no
    return f":{cor}[**[{rotulo_do_no(evento.no)}]**] {evento.conteudo}"


def _render_trace_ao_vivo(trace: list) -> None:
    """O raciocínio nó-a-nó colorido (reusado pelo histórico: PERSISTE)."""
    for evento in trace:
        st.markdown(_linha_de_trace(evento))


def _render_visual(especificacao, indice: int) -> None:
    """Executa o veredito da decisão pura de renderização (o GRÁFICO)."""
    veredito = decidir_renderizacao(especificacao)
    if veredito["aviso"]:
        st.warning(veredito["aviso"])
    if veredito["tipo"] == "echarts":
        from streamlit_echarts import st_echarts  # import tardio (só na UI real)
        st_echarts(options=veredito["option"], height=ALTURA_GRAFICO_UI,
                   key=f"echarts_{indice}")
    elif veredito["tipo"] == "metrica":
        st.metric(label=veredito["rotulo"], value=veredito["valor"])
    elif veredito["tipo"] == "tabela":
        import pandas as pd
        from app.analise_outliers import detectar_outliers

        colunas = veredito["colunas"]
        linhas = veredito["linhas"]
        df = pd.DataFrame(
            [dict(zip(colunas, linha)) for linha in linhas]
        )
        # Linhas com VALOR FORA DO PADRÃO (|z|>2) são pintadas: o mesmo
        # detector determinístico que alimenta o Diretor agora destaca a
        # linha na tabela, ligando análise e apresentação.
        achados = detectar_outliers(colunas, linhas)
        indices_outliers = set()
        if achados:
            rotulos_outliers = {a["rotulo"] for a in achados}
            primeira_coluna = colunas[0] if colunas else None
            for i, linha in enumerate(linhas):
                rotulo = str(linha[0]) if linha else ""
                if rotulo in rotulos_outliers:
                    indices_outliers.add(i)

        if indices_outliers:
            def _pintar_linha(linha_df):
                cor = ("background-color: #FDECEA; color: #A32D2D"
                       if linha_df.name in indices_outliers else "")
                return [cor] * len(linha_df)

            st.dataframe(
                df.style.apply(_pintar_linha, axis=1),
                use_container_width=True,
            )
            st.caption(
                ":red[As linhas destacadas contêm valores fora do padrão "
                "(|z| > 2) — pontos que mais merecem atenção.]"
            )
        else:
            st.dataframe(df, use_container_width=True)


def _render_caminho_no_grafo(item: dict, indice: int) -> None:
    """A visualização dinâmica do M5: diagrama SVG do caminho + REPLAY.
    Em repouso mostra a TRILHA completa; ao clicar em Reproduzir, anima do
    passo 1 ao último (modo 'ativo') e volta à trilha. O pedido é marcado
    pelo on_click (replay_pedido_{i}) e consumido neste mesmo ciclo — um
    clique basta, sem depender de rerun extra nem reentrância do placeholder."""
    trace = item.get("trace") or []
    total = total_de_passos(trace)
    if total == 0:
        return
    pedido = f"replay_pedido_{indice}"

    # O botão vem PRIMEIRO; o on_click marca o pedido antes do rerun.
    st.button(
        "Reproduzir", key=f"replay_play_{indice}",
        on_click=lambda chave=pedido: st.session_state.__setitem__(chave, True),
    )
    st.caption(f"Replay: {total} passos no total")

    # Placeholder ESTÁVEL para o diagrama (criado uma vez, depois do botão).
    painel = st.empty()

    if st.session_state.pop(pedido, False):
        # V3.5: anima NESTE mesmo ciclo, num painel já estável — do passo 1
        # ao último (modo "ativo": só o nó corrente colorido) e termina na
        # trilha completa. Como o pedido já foi consumido, o clique único
        # basta: não depende de rerun extra nem de reentrância do placeholder.
        for k in range(1, total + 1):
            painel.markdown(
                montar_svg_do_grafo(
                    caminho_percorrido(trace, ate_passo=k), modo="ativo"),
                unsafe_allow_html=True,
            )
            time.sleep(0.45)
        painel.markdown(
            montar_svg_do_grafo(caminho_percorrido(trace)),
            unsafe_allow_html=True,
        )
    else:
        # Estado em repouso: a trilha completa (todos os nós visitados).
        painel.markdown(
            montar_svg_do_grafo(caminho_percorrido(trace)),
            unsafe_allow_html=True,
        )


def _render_resposta(item: dict, indice: int) -> None:
    """Uma resposta completa, NA ORDEM DO M5:
    iteração dos agentes → trace técnico → resposta → gráfico → caminho."""
    if item.get("trace"):
        # 1. A iteração dos agentes (persistente, aberta).
        with st.expander("Raciocínio dos agentes (passo a passo)", expanded=True):
            _render_trace_ao_vivo(item["trace"])
        # 2. O trace técnico em texto puro (fechado), para auditoria/cópia.
        with st.expander("Trace técnico — como cheguei aqui"):
            st.code(renderizar_trace(item["trace"]), language=None)
        # 2b. AS CONSULTAS SQL (V3.4): botão em vermelho claro que alterna
        # a região com as consultas, copiáveis com um clique.
        if item.get("resultados"):
            aberto = f"sql_aberto_{indice}"
            st.button(
                "Consultas SQL executadas no banco",
                key=f"sql_btn_{indice}",
                on_click=lambda chave=aberto: st.session_state.__setitem__(
                    chave, not st.session_state.get(chave, False)),
            )
            if st.session_state.get(aberto):
                for n, resultado in enumerate(item["resultados"], start=1):
                    st.caption(f"Passo {n}: {resultado.get('objetivo', '')}")
                    st.code(resultado.get("sql", ""), language="sql")
    # 3. A resposta de negócio (ou a falha honesta).
    if item.get("falha_graciosa"):
        _ancora(f"{_ANCORA_GRAFICO}-{indice}")
        st.error(item["falha_graciosa"])
    else:
        # Resposta como TEXTO PURO: evita que valores monetários (R$, números
        # com . e ,) sejam interpretados como código markdown e fiquem verdes.
        st.text(item["resposta"])
        if item.get("premissas"):
            premissas = "  \n".join(f":orange[• {p}]" for p in item["premissas"])
            st.markdown(f"**Premissas assumidas:**  \n{premissas}")
        # Conclusão executiva (V3.10): título em negrito; cada parágrafo com
        # o PREFIXO em negrito e o corpo em texto normal (negrito seletivo de
        # frases-chave fica a cargo do Redator, via **markdown**).
        if item.get("impactos_e_acoes"):
            st.markdown(
                "**IMPACTOS PARA O NEGÓCIO E AÇÕES A SEREM REALIZADAS PARA "
                "AMENIZAR OS CONSEQUÊNCIAS NEGATIVAS AO NEGÓCIO E IMPULSIONAR "
                "OS RESULTADOS DO NEGÓCIO**"
            )
            for paragrafo in item["impactos_e_acoes"]:
                st.markdown(paragrafo)
        # 4. O GRÁFICO — sempre APÓS a iteração (fluxo natural da informação).
        _ancora(f"{_ANCORA_GRAFICO}-{indice}")
        _render_visual(item.get("especificacao_visual"), indice)
    if st.session_state.get("focar_no_grafico"):
        # V3.2: a resposta acabou de chegar — foca o gráfico UMA vez
        # (a flag é consumida; reruns posteriores, como o replay, não rolam).
        st.session_state.focar_no_grafico = False
        _rolar_para(f"{_ANCORA_GRAFICO}-{indice}")
    # 5. O caminho no grafo (M5), com replay — persiste por mensagem.
    if item.get("trace"):
        with st.expander("Caminho no grafo (replay)", expanded=True):
            _render_caminho_no_grafo(item, indice)


def _consumir_gerador(gerador) -> None:
    """Consome o motor: trace ao vivo no st.status + GRAFO AO VIVO abaixo
    (o diagrama acende nó a nó conforme os eventos chegam); interrupt/final
    vão para a sessão e o rerun re-renderiza tudo a partir do histórico."""
    final, interrupcao = None, None
    trace_parcial = []
    # SPLIT HORIZONTAL AO VIVO (decisão V2): diagrama à esquerda em modo
    # "ativo" (só o nó corrente colorido, resto cinza), log à direita.
    # V3.3: o foco ao enviar cai NA REGIÃO DA ITERAÇÃO (o split ao vivo).
    _ancora(_ANCORA_INICIO)
    _rolar_para(_ANCORA_INICIO)
    col_grafo, col_log = st.columns(2)
    painel_grafo = col_grafo.empty()
    painel_grafo.markdown(
        montar_svg_do_grafo(caminho_percorrido([]), modo="ativo"),
        unsafe_allow_html=True,
    )
    with col_log:
        with st.status("Agentes trabalhando…", expanded=True) as status:
            for evento in gerador:
                if evento.tipo == "trace":
                    st.markdown(_linha_de_trace(evento.payload))
                    trace_parcial.append(evento.payload)
                    # O nó que acabou de falar acende; o resto apaga.
                    painel_grafo.markdown(
                        montar_svg_do_grafo(
                            caminho_percorrido(trace_parcial,
                                               em_execucao=True),
                            modo="ativo"),
                        unsafe_allow_html=True,
                    )
                elif evento.tipo == "interrupt":
                    interrupcao = evento.payload
                elif evento.tipo == "final":
                    final = evento.payload
            if interrupcao:
                status.update(label="Aguardando seu esclarecimento…",
                              state="complete")
            else:
                status.update(label="Concluído.", state="complete")
    # Ao terminar, o painel mostra a TRILHA completa (visitados tingidos).
    if trace_parcial:
        painel_grafo.markdown(
            montar_svg_do_grafo(caminho_percorrido(trace_parcial)),
            unsafe_allow_html=True,
        )
    if interrupcao:
        st.session_state.interrupt_pendente = interrupcao
    elif final is not None:
        final["pergunta"] = st.session_state.pergunta_em_andamento
        st.session_state.historico.append(final)
        st.session_state.interrupt_pendente = None
        st.session_state.focar_no_grafico = True   # V3.2: rerun foca o gráfico
    st.rerun()


def principal() -> None:
    """Monta a página inteira (sidebar FRANQ + chat) a cada rerun."""
    st.set_page_config(page_title=TITULO_DA_INTERFACE, layout="wide")
    st.markdown(_CSS_FRANQ, unsafe_allow_html=True)

    # ── Estado da sessão ─────────────────────────────────────────────────
    if "sessao" not in st.session_state:
        st.session_state.sessao = fluxo.criar_sessao()
        st.session_state.historico = []
        st.session_state.interrupt_pendente = None
        st.session_state.pergunta_em_andamento = None
        st.session_state.pergunta_pendente = None
        st.session_state.focar_no_grafico = False
        st.session_state.replay = {}

    # ── Sidebar (cor FRANQ + logo no topo) ───────────────────────────────
    with st.sidebar:
        st.markdown(_LOGO_FRANQ, unsafe_allow_html=True)
        st.title(TITULO_DA_INTERFACE)
        indice_padrao = 0 if MODO_VISUALIZACAO_PADRAO == "agente" else 1
        modo = st.radio(
            "Autor do visual",
            options=["agente", "pre_setado"],
            index=indice_padrao,
            help=("agente: o Designer de Visualização autora o gráfico ECharts. "
                  "pre_setado: heurística determinística (custo LLM zero)."),
        )
        if configurar_langsmith():
            st.success(f"LangSmith ATIVO — projeto {PROJETO_LANGSMITH}")
        else:
            st.info("LangSmith inativo (LANGSMITH_API_KEY ausente no .env)")

    st.title(TITULO_DA_INTERFACE)

    # ── Histórico (TUDO persiste: logs, respostas, gráficos e caminhos) ──
    for indice, item in enumerate(st.session_state.historico):
        with st.chat_message("user"):
            st.write(item["pergunta"])
        with st.chat_message("assistant"):
            _render_resposta(item, indice)

    # ── Interrupt pendente: a pergunta do Analista no chat ───────────────
    if st.session_state.interrupt_pendente:
        with st.chat_message("assistant"):
            st.info(f"Preciso de um esclarecimento: "
                    f"{st.session_state.interrupt_pendente}")

    # ── Entrada (pergunta nova OU resposta ao esclarecimento) ────────────
    dica = ("Responda ao esclarecimento acima…"
            if st.session_state.interrupt_pendente
            else "Pergunte aos dados (ex.: reclamações não resolvidas por canal)")
    entrada = st.chat_input(dica)
    if entrada:
        if st.session_state.interrupt_pendente:
            # Resposta ao esclarecimento: mesma pergunta, NÃO limpa a tela.
            with st.chat_message("user"):
                st.write(entrada)
            with st.chat_message("assistant"):
                _consumir_gerador(
                    fluxo.retomar_fluxo(st.session_state.sessao, entrada))
        else:
            # PERGUNTA NOVA (decisão V3.1): a conversa anterior é apagada
            # AUTOMATICAMENTE — mensagens, gráficos e diagramas. A pergunta
            # fica pendente e o rerun processa numa tela limpa.
            st.session_state.historico = []
            st.session_state.replay = {}
            st.session_state.pergunta_pendente = entrada
            st.rerun()

    if st.session_state.pergunta_pendente:
        pergunta = st.session_state.pergunta_pendente
        st.session_state.pergunta_pendente = None
        with st.chat_message("user"):
            st.write(pergunta)
        with st.chat_message("assistant"):
            st.session_state.pergunta_em_andamento = pergunta
            _consumir_gerador(fluxo.executar_em_fluxo(
                st.session_state.sessao, pergunta, CAMINHO_BANCO_PADRAO, modo))


principal()
