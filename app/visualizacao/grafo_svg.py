# -*- coding: utf-8 -*-
"""
grafo_svg.py — A visualização dinâmica do grafo (Marco 5, versão 2).

Três responsabilidades, todas SEM Streamlit (testáveis puras):
1. A TOPOLOGIA FIXA do grafo (nós com posição + arestas + rótulos das
   CONDICIONAIS), espelhando a estrutura real compilada — um teste casa as
   duas e impede divergência silenciosa.
2. caminho_percorrido(trace, ate_passo): função PURA que deriva do trace a
   sequência de nós visitados (com REPETIÇÃO nos loops) e o nó atual.
3. montar_svg_do_grafo(caminho, modo): o SVG (string), em DOIS modos:
   - "trilha": nós visitados tingidos + ativo com halo (replay completo);
   - "ativo": SÓ o nó corrente colorido, todo o resto cinza (tempo real).
   As ARESTAS DE RETORNO (loops de correção) são SEMPRE desenhadas em
   AMARELO MOSTARDA — são a assinatura visual da autocorreção do sistema.
   Markup estático montado por nós — JAMAIS contém <script>.

Nomenclatura: idêntica à do trace/projeto (perfilador, analista, esclarecer,
engenheiro, guardrail, executor, auditor, visualizador, redator). O nó de
falha exibe o rótulo "teto estourado". O Guardrail de Visualização é INTERNO
ao nó visualizador (Designer+Guardrail em loop dentro do nó) e aparece como
anotação tracejada — não é nó do grafo.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class NoDoGrafo:
    id: str          # nome como aparece no TRACE (EventoTrace.no)
    rotulo: str
    x: int
    y: int


@dataclass(frozen=True)
class ArestaDoGrafo:
    origem: str
    destino: str
    condicao: str = ""       # rótulo da condicional (vazio = aresta direta)
    retorno: bool = False    # loop de correção → amarelo mostarda, sempre
    canal_x: int = 0         # >0: rota LATERAL (sobe/desce por um canal à direita)


@dataclass
class CaminhoNoGrafo:
    sequencia_nos: list
    arestas: list
    no_atual: str | None
    tempos_ms: dict = None       # nó -> soma dos tempo_ms dos seus eventos
    tokens: dict = None          # nó -> soma dos tokens das suas chamadas


# ── Topologia compacta (2 colunas; cabe numa janela maximizada) ──────────────
LARGURA_NO, ALTURA_NO = 138, 40
NOS_DO_GRAFO = (
    NoDoGrafo("perfilador", "perfilador", 36, 12),
    NoDoGrafo("analista", "analista", 36, 70),
    NoDoGrafo("esclarecimento", "esclarecer (interrupt)", 300, 70),
    NoDoGrafo("engenheiro", "engenheiro", 36, 128),
    NoDoGrafo("guardrail", "guardrail", 36, 186),
    NoDoGrafo("executor", "executor", 36, 244),
    NoDoGrafo("auditor", "auditor", 36, 302),
    NoDoGrafo("visualizador", "visualizador", 36, 360),
    NoDoGrafo("redator", "diretor", 36, 418),
    NoDoGrafo("falha_graciosa", "teto estourado", 300, 302),
)
ARESTAS_DO_GRAFO = (
    ArestaDoGrafo("perfilador", "analista"),
    ArestaDoGrafo("analista", "esclarecimento", "ambígua?"),
    ArestaDoGrafo("esclarecimento", "analista", "resposta", retorno=True),
    ArestaDoGrafo("analista", "engenheiro", "plano ok"),
    ArestaDoGrafo("analista", "falha_graciosa", "escopo/teto", canal_x=284),
    ArestaDoGrafo("engenheiro", "guardrail", "sql proposto"),
    ArestaDoGrafo("guardrail", "engenheiro", "reprovado", retorno=True,
                  canal_x=212),
    ArestaDoGrafo("guardrail", "executor", "aprovado"),
    ArestaDoGrafo("guardrail", "falha_graciosa", "", canal_x=284),
    ArestaDoGrafo("executor", "engenheiro", "erro/próx. passo", retorno=True,
                  canal_x=236),
    ArestaDoGrafo("executor", "auditor", "plano completo"),
    ArestaDoGrafo("executor", "falha_graciosa", "", canal_x=284),
    ArestaDoGrafo("auditor", "engenheiro", "devolvido", retorno=True,
                  canal_x=260),
    ArestaDoGrafo("auditor", "visualizador", "aprovado"),
    ArestaDoGrafo("auditor", "falha_graciosa", "teto"),
    ArestaDoGrafo("visualizador", "redator"),
)
_IDS_VALIDOS = {n.id for n in NOS_DO_GRAFO}
_ARESTAS_VALIDAS = {(a.origem, a.destino) for a in ARESTAS_DO_GRAFO}

COR_MOSTARDA = "#C9A227"   # amarelo mostarda: a cor dos RETORNOS (autocorreção)

# Flag conceitual (V3.4): AGENTE = cargo do MESMO LLM com decisão em loop;
# DETERMINÍSTICO = código Python puro; HUMANO = o interrupt do usuário.
FLAG_DO_NO = {
    "perfilador": "DETERMINÍSTICO",
    "analista": "AGENTE · LLM",
    "esclarecimento": "HUMANO · interrupt",
    "engenheiro": "AGENTE · LLM",
    "guardrail": "DETERMINÍSTICO",
    "executor": "DETERMINÍSTICO",
    "auditor": "AGENTE · LLM",
    "visualizador": "AGENTE · LLM",
    "redator": "AGENTE · LLM",
    "falha_graciosa": "DETERMINÍSTICO",
}

_COR_PAPEL = {
    "perfilador": "#5F5E5A", "analista": "#185FA5",
    "esclarecimento": "#BA7517", "engenheiro": "#534AB7",
    "guardrail": "#BA7517", "executor": "#3B6D11",
    "auditor": "#993C1D", "visualizador": "#0F6E56",
    "redator": "#185FA5", "falha_graciosa": "#A32D2D",
}
_FUNDO_PAPEL = {
    "perfilador": "#F1EFE8", "analista": "#E6F1FB",
    "esclarecimento": "#FAEEDA", "engenheiro": "#EEEDFE",
    "guardrail": "#FAEEDA", "executor": "#EAF3DE",
    "auditor": "#FAECE7", "visualizador": "#E1F5EE",
    "redator": "#E6F1FB", "falha_graciosa": "#FCEBEB",
}


def _no_em_execucao(trace: list) -> str | None:
    """Inferência DETERMINÍSTICA de quem está RODANDO AGORA: os eventos só
    chegam quando um nó CONCLUI (stream updates do LangGraph) — então, ao
    vivo, o nó ativo é o SUCESSOR do último concluído, decidido pelas mesmas
    condições das arestas do grafo (V3.8)."""
    import re
    ultimo = next((e for e in reversed(trace)
                   if getattr(e, "no", None)), None)
    if ultimo is None:
        return None
    no = ultimo.no
    conteudo = (getattr(ultimo, "conteudo", "") or "")
    if no == "pergunta":
        return "perfilador"
    if no == "perfilador":
        return "analista"
    if no == "analista":
        if "perguntando ao usuário" in conteudo:
            return "esclarecimento"
        return "engenheiro"            # plano/premissas → engenheiro
    if no == "esclarecimento":
        return "analista"
    if no == "engenheiro":
        return "guardrail"
    if no == "guardrail":
        return "executor" if "aprovada" in conteudo.lower() else "engenheiro"
    if no == "executor":
        # próximo passo do plano → engenheiro; plano completo → auditor
        plano = next((e for e in reversed(trace)
                      if e.no == "analista" and "Plano com" in (e.conteudo or "")),
                     None)
        achado = re.search(r"Plano com (\d+)", plano.conteudo) if plano else None
        total = int(achado.group(1)) if achado else 1
        feitos = sum(1 for e in trace
                     if e.no == "executor" and "concluído" in (e.conteudo or ""))
        return "auditor" if feitos >= max(total, 1) else "engenheiro"
    if no == "auditor":
        return "visualizador" if "APROVADA" in conteudo else "engenheiro"
    if no == "visualizador":
        return "redator"
    return None                        # redator/falha: o fluxo terminou


def caminho_percorrido(trace: list, ate_passo: int | None = None,
                       em_execucao: bool = False) -> CaminhoNoGrafo:
    """Deriva do trace o caminho no grafo. PURA. Eventos CONSECUTIVOS do mesmo
    nó = UM passo; loops = repetição; `ate_passo` é a base do replay; nós
    desconhecidos são ignorados."""
    passos = []
    tempos = {}
    tokens = {}
    for evento in trace:
        no = getattr(evento, "no", None)
        if no not in _IDS_VALIDOS:
            continue
        if not passos or passos[-1] != no:
            passos.append(no)
        tempo = getattr(evento, "tempo_ms", None)
        if tempo:
            tempos[no] = tempos.get(no, 0.0) + tempo
        usados = getattr(evento, "tokens", None)
        if usados:
            tokens[no] = tokens.get(no, 0) + usados
    if ate_passo is not None:
        passos = passos[: max(0, ate_passo)]
    arestas = []
    for origem, destino in zip(passos, passos[1:]):
        if (origem, destino) in _ARESTAS_VALIDAS:
            arestas.append((origem, destino))
    atual = passos[-1] if passos else None
    if em_execucao:
        # Ao vivo: destaque em quem está RODANDO (sucessor do concluído);
        # o concluído permanece visitado (cinza, com tempo/tokens).
        rodando = _no_em_execucao(trace)
        if rodando:
            atual = rodando
    return CaminhoNoGrafo(
        sequencia_nos=passos,
        arestas=arestas,
        no_atual=atual,
        tempos_ms=tempos,
        tokens=tokens,
    )


def total_de_passos(trace: list) -> int:
    """Quantos passos distintos de nó o caminho completo tem (p/ o replay)."""
    return len(caminho_percorrido(trace).sequencia_nos)


def _centro(no: NoDoGrafo) -> tuple:
    return no.x + LARGURA_NO / 2, no.y + ALTURA_NO / 2


def _ancora(origem: NoDoGrafo, destino: NoDoGrafo) -> tuple:
    ox, oy = _centro(origem)
    dx, dy = _centro(destino)
    if abs(dx - ox) > abs(dy - oy):
        if dx > ox:
            return (origem.x + LARGURA_NO, oy, destino.x, dy)
        return (origem.x, oy, destino.x + LARGURA_NO, dy)
    if dy > oy:
        return (ox, origem.y + ALTURA_NO, dx, destino.y)
    return (ox, origem.y, dx, destino.y + ALTURA_NO)


def montar_svg_do_grafo(caminho: CaminhoNoGrafo, largura: int = 560,
                        modo: str = "trilha") -> str:
    """O SVG do grafo no estado do `caminho`.
    modo="trilha": visitados tingidos, ativo com halo (replay/completo).
    modo="ativo":  SÓ o nó corrente colorido; o resto TODO cinza (tempo real).
    Retornos SEMPRE em amarelo mostarda. SEM <script>."""
    nos_por_id = {n.id: n for n in NOS_DO_GRAFO}
    visitados = set(caminho.sequencia_nos)
    percorridas = set(caminho.arestas)
    pulsando = caminho.arestas[-1] if caminho.arestas else None
    altura = max(n.y for n in NOS_DO_GRAFO) + ALTURA_NO + 14

    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" '
        f'viewBox="0 0 {largura} {altura}" role="img" '
        f'style="max-height:78vh">',
        '<title>Caminho percorrido no grafo multiagêntico</title>',
        '<defs><marker id="seta" viewBox="0 0 10 10" refX="8" refY="5" '
        'markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse">'
        '<path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" '
        'stroke-width="1.5" stroke-linecap="round"/></marker></defs>',
    ]
    for aresta in ARESTAS_DO_GRAFO:
        origem, destino = nos_por_id[aresta.origem], nos_por_id[aresta.destino]
        chave = (aresta.origem, aresta.destino)
        mesma_linha = origem.y == destino.y
        if mesma_linha and not aresta.canal_x:
            # Par ida/volta na MESMA linha (analista ↔ esclarecer): a ida
            # corre acima do centro, a volta (retorno) abaixo — como no ASCII.
            desloca = -6 if not aresta.retorno else +7
            if destino.x > origem.x:
                x1, x2 = origem.x + LARGURA_NO, destino.x
            else:
                x1, x2 = origem.x, destino.x + LARGURA_NO
            y1 = y2 = _centro(origem)[1] + desloca
        else:
            x1, y1, x2, y2 = _ancora(origem, destino)
        if aresta.retorno:
            # Retornos (autocorreção): amarelo mostarda SEMPRE visível.
            cor = COR_MOSTARDA
            if chave == pulsando:
                espessura, tracejado, classe = 3, "", ' class="aresta-pulsando"'
            elif chave in percorridas:
                espessura, tracejado, classe = 2, "", ""
            else:
                espessura, tracejado, classe = 1.2, ' stroke-dasharray="5 3"', ""
        elif chave == pulsando:
            cor, espessura, tracejado = _COR_PAPEL[aresta.destino], 3, ""
            classe = ' class="aresta-pulsando"'
        elif chave in percorridas:
            cor, espessura, tracejado = _COR_PAPEL[aresta.destino], 1.8, ""
            classe = ""
        else:
            cor, espessura = "#C9C7BE", 0.8
            tracejado, classe = ' stroke-dasharray="4 4"', ""
        if aresta.canal_x:
            # ROTA LATERAL (padrão do diagrama ASCII): sai pela direita do nó,
            # corre pelo canal vertical e entra pela direita do destino.
            oy = _centro(origem)[1]
            dy = _centro(destino)[1]
            borda_o = origem.x + LARGURA_NO
            borda_d = destino.x + LARGURA_NO if destino.x == origem.x else destino.x
            pontos = (f"{borda_o},{oy} {aresta.canal_x},{oy} "
                      f"{aresta.canal_x},{dy} {borda_d},{dy}")
            partes.append(
                f'<polyline points="{pontos}" stroke="{cor}" '
                f'stroke-width="{espessura}"{tracejado}{classe} '
                f'marker-end="url(#seta)" fill="none"/>'
            )
            if aresta.condicao:
                # Rótulo junto à SAÍDA do nó de origem. Canais mais à direita
                # ancoram o texto à ESQUERDA (evita invadir as caixas da
                # coluna direita: esclarecer e teto estourado).
                if aresta.canal_x >= 250:
                    pos_x, lado = aresta.canal_x - 5, "end"
                else:
                    pos_x, lado = aresta.canal_x + 4, "start"
                partes.append(
                    f'<text x="{pos_x}" y="{oy - 4}" '
                    f'text-anchor="{lado}" font-family="Arial, sans-serif" '
                    f'font-size="9" font-style="italic" fill="#7A786E">'
                    f'{aresta.condicao}</text>'
                )
            continue
        partes.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{cor}" '
            f'stroke-width="{espessura}"{tracejado}{classe} '
            f'marker-end="url(#seta)" fill="none"/>'
        )
        if aresta.condicao:
            # O rótulo da CONDICIONAL: a decisão escrita sobre a aresta.
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 4
            if abs(y2 - y1) > abs(x2 - x1):           # vertical: desloca p/ lado
                mx += 8
                my = (y1 + y2) / 2
                ancora_texto = "start"
            else:
                ancora_texto = "middle"
            partes.append(
                f'<text x="{mx}" y="{my}" text-anchor="{ancora_texto}" '
                f'font-family="Arial, sans-serif" font-size="9" '
                f'fill="#7A786E" font-style="italic">{aresta.condicao}</text>'
            )
    for no in NOS_DO_GRAFO:
        cor = _COR_PAPEL[no.id]
        ativo = no.id == caminho.no_atual
        visitado = no.id in visitados
        if ativo:
            fundo, borda, espessura = _FUNDO_PAPEL[no.id], cor, 2.5
            halo = (f'<rect x="{no.x - 4}" y="{no.y - 4}" '
                    f'width="{LARGURA_NO + 8}" height="{ALTURA_NO + 8}" rx="10" '
                    f'fill="none" stroke="{cor}" stroke-width="1" '
                    f'stroke-opacity="0.45" class="halo-ativo"/>')
            cor_texto, marca = cor, "no-ativo"
        elif visitado and modo == "trilha":
            fundo, borda, espessura = _FUNDO_PAPEL[no.id], cor, 1.2
            halo, cor_texto, marca = "", cor, "no-visitado"
        else:
            # modo "ativo": tudo que não é o nó corrente fica CINZA.
            fundo, borda, espessura = "#F7F6F2", "#C9C7BE", 0.8
            halo, cor_texto = "", "#9A988F"
            marca = "no-visitado-cinza" if (visitado and modo == "ativo") else "no-inativo"
        partes.append(halo)
        partes.append(
            f'<g class="{marca}" data-no="{no.id}">'
            f'<rect x="{no.x}" y="{no.y}" width="{LARGURA_NO}" '
            f'height="{ALTURA_NO}" rx="7" fill="{fundo}" stroke="{borda}" '
            f'stroke-width="{espessura}"/>'
            f'<text x="{no.x + LARGURA_NO / 2}" y="{no.y + 15}" '
            f'text-anchor="middle" dominant-baseline="central" '
            f'font-family="Arial, sans-serif" font-size="12" '
            f'font-weight="600" fill="{cor_texto}">{no.rotulo}</text>'
            f'<text x="{no.x + 6}" y="{no.y + ALTURA_NO - 6}" '
            f'text-anchor="start" font-family="Arial, sans-serif" '
            f'font-size="6.5" letter-spacing="0.4" class="flag-do-no" '
            f'fill="{cor_texto}" opacity="0.75">{FLAG_DO_NO[no.id]}</text></g>'
        )
        # Contador de tempo do agente (V3.3): aparece quando o nó conclui
        # (o tempo_ms chega no evento de conclusão de cada chamada).
        tempo = (caminho.tempos_ms or {}).get(no.id)
        usados = (caminho.tokens or {}).get(no.id)
        if (tempo or usados) and (ativo or visitado):
            pedacos = []
            if tempo:
                pedacos.append(f"{tempo:.0f}ms" if tempo < 1000
                               else f"{tempo / 1000:.1f}s")
            if usados:
                pedacos.append(f"{usados} tk")
            partes.append(
                f'<text x="{no.x + LARGURA_NO - 6}" y="{no.y + ALTURA_NO - 6}" '
                f'text-anchor="end" font-family="Arial, sans-serif" '
                f'font-size="7.5" fill="{cor_texto}" class="tempo-do-no" '
                f'opacity="0.9">{" · ".join(pedacos)}</text>'
            )
    # Anotação: o Guardrail de Visualização é INTERNO ao visualizador.
    vis = nos_por_id["visualizador"]
    # Centro da anotação (altura 36) ALINHADO ao centro da caixa (altura 40):
    ax, ay = 300, vis.y + (ALTURA_NO - 36) / 2
    partes.append(
        f'<g class="anotacao-guardrail-visual">'
        f'<rect x="{ax}" y="{ay}" width="200" height="36" rx="7" '
        f'fill="none" stroke="#9A988F" stroke-width="0.9" '
        f'stroke-dasharray="4 3"/>'
        f'<text x="{ax + 100}" y="{ay + 13}" text-anchor="middle" '
        f'font-family="Arial, sans-serif" font-size="9.5" fill="#7A786E">'
        f'guardrail de visualização</text>'
        f'<text x="{ax + 100}" y="{ay + 26}" text-anchor="middle" '
        f'font-family="Arial, sans-serif" font-size="9" font-style="italic" '
        f'fill="#9A988F">(interno: Designer + validação em loop)</text></g>'
    )
    partes.append(
        f'<line x1="{vis.x + LARGURA_NO}" y1="{vis.y + ALTURA_NO / 2}" '
        f'x2="{ax}" y2="{vis.y + ALTURA_NO / 2}" stroke="#9A988F" stroke-width="0.8" '
        f'stroke-dasharray="3 3"/>'
    )
    partes.append("</svg>")
    return "".join(p for p in partes if p)
