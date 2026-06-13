# -*- coding: utf-8 -*-
"""
grafo.py — O grafo LangGraph: roteamento clássico multiagêntico.

A tese do projeto em código: as ARESTAS são funções Python puras sobre o
estado (determinismo no plano de controle); a inteligência vive DENTRO dos
nós (agência onde há incerteza). Três camadas de contenção garantem que
nenhum caminho patológico roda para sempre: teto por passo, teto de
devoluções do Auditor e orçamento global de chamadas LLM.

Diagrama (retornos = linhas laterais, em amarelo mostarda na interface):
    START → perfilador → analista ──(ambígua?)──→ esclarecer (interrupt) ─┐
                            ▲ ◄──────── resposta do usuário (retorno) ────┘
                            ├──(fora de escopo / teto)──→ teto estourado → END
                            ▼ plano ok
                       engenheiro ◄──────────────┬──────────────────┐
                            ▼                    │ retry c/ erro    │ devolução
                        guardrail ── reprovou ───┤                  │ c/ instrução
                            ▼ aprovou            │                  │
                        executor ──── erro ──────┘                  │
                            │ ok                                    │
                            ├── há próximo passo → engenheiro       │
                            ▼ plano completo                        │
                         auditor ── reprovou ───────────────────────┘
                            ▼ aprovou
                      visualizador (Designer + guardrail de visualização INTERNOS)
                            ▼
                         redator → END   (qualquer teto → teto estourado → END)
"""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agentes.analista_negocios import analisar, redigir_resposta
from app.agentes.auditor_dados import auditar
from app.agentes.designer_visualizacao import propor_visualizacao
from app.agentes.engenheiro_dados import gerar_sql
from app.config import (
    MAX_ESCLARECIMENTOS,
    criar_llm,
    MAX_DEVOLUCOES_AUDITOR,
    MAX_TENTATIVAS_SQL,
    MAX_TENTATIVAS_VISUAL,
    MODO_VISUALIZACAO_PADRAO,
    ORCAMENTO_GLOBAL_CHAMADAS_LLM,
)
from app.estado import (
    AnaliseDaPergunta,
    EspecificacaoVisual,
    EstadoDoAssistente,
    ParecerDoAuditor,
    PassoDoPlano,
    PropostaDoDesigner,
    RespostaDeNegocio,
    SqlDoPasso,
)
from app.executor import executar
from app.guardrail_sql import validar
from app.perfilador import perfilar, renderizar_para_prompt
from app.trace import EventoTrace, cronometro, decorrido_ms, registrar
from app.visualizacao.guardrail_visualizacao import validar_option
from app.visualizacao.templates import (
    _especificacao_tabela,
    _pediu_tabela_explicitamente,
    montar_especificacao_pre_setada,
)


# Tipos customizados que vivem no estado e atravessam o checkpoint no
# ciclo interrupt/resume. Registrá-los na allowlist do serializador elimina
# o aviso "Deserializing unregistered type ..." (e nos blinda contra a
# versão futura do langgraph que BLOQUEARÁ tipos não registrados).
_TIPOS_DO_ESTADO = (
    EventoTrace,
    AnaliseDaPergunta,
    PassoDoPlano,
    SqlDoPasso,
    ParecerDoAuditor,
    RespostaDeNegocio,
    PropostaDoDesigner,
    EspecificacaoVisual,
)


def _criar_checkpointer():
    """MemorySaver com os tipos do estado REGISTRADOS no serializador."""
    return MemorySaver(
        serde=JsonPlusSerializer(allowed_msgpack_modules=list(_TIPOS_DO_ESTADO))
    )




class _ContadorDeTokens:
    """Callback que soma o usage_metadata de cada resposta do modelo."""

    def __init__(self):
        self.total = 0

    def on_llm_end(self, resposta, **_kw):          # API do BaseCallbackHandler
        for geracoes in getattr(resposta, "generations", []):
            for geracao in geracoes:
                mensagem = getattr(geracao, "message", None)
                uso = getattr(mensagem, "usage_metadata", None) or {}
                self.total += int(uso.get("total_tokens", 0) or 0)


class _LlmContado:
    """Envelopa o LLM e CONTA os tokens de cada rodada de nó (V3.4).
    Transparente para os agentes (só expõe with_structured_output) e para o
    mock dos testes (se o invoke não aceitar config, conta zero)."""

    def __init__(self, llm):
        self._llm = llm
        self.tokens_da_rodada = 0

    def zerar(self) -> None:
        self.tokens_da_rodada = 0

    def with_structured_output(self, schema):
        interno = self._llm.with_structured_output(schema)
        externo = self

        class _Invocador:
            def invoke(self, prompt):
                from langchain_core.callbacks import BaseCallbackHandler

                class _Handler(BaseCallbackHandler, _ContadorDeTokens):
                    def __init__(self):
                        BaseCallbackHandler.__init__(self)
                        _ContadorDeTokens.__init__(self)

                contador = _Handler()
                try:
                    resultado = interno.invoke(
                        prompt, config={"callbacks": [contador]})
                except TypeError:               # mock dos testes: sem config
                    resultado = interno.invoke(prompt)
                externo.tokens_da_rodada += contador.total
                return resultado

        return _Invocador()


def construir_grafo(llm=None, checkpointer=None):
    """Monta e compila o grafo. `llm` propagado a todos os agentes (mock nos
    testes; None → Gemini real). `checkpointer` default = MemorySaver
    (necessário ao interrupt)."""
    llm = _LlmContado(llm if llm is not None else criar_llm())

    # ── Nós ──────────────────────────────────────────────────────────────────

    def no_perfilador(estado: EstadoDoAssistente) -> dict:
        """Determinístico: perfila o banco (cache do M1) e injeta o dossiê."""
        eventos = []
        inicio = cronometro()
        llm.zerar()
        perfil = perfilar(estado["caminho_banco"])
        dossie = renderizar_para_prompt(perfil)
        registrar(
            eventos, "perfilador", "info",
            f"Dossiê pronto: {len(perfil.estrutura)} tabelas, "
            f"{len(perfil.alertas_qualidade)} alerta(s) de qualidade.",
            dados={"alertas": [a.mensagem for a in perfil.alertas_qualidade]},
            tempo_ms=decorrido_ms(inicio),
            tokens=llm.tokens_da_rodada,
        )
        return {"dossie": dossie, "trace": eventos}

    def no_analista(estado: EstadoDoAssistente) -> dict:
        """LLM: decompõe a pergunta (com os esclarecimentos já dados)."""
        eventos = []
        inicio = cronometro()
        llm.zerar()
        analise = analisar(
            estado["pergunta"],
            estado["dossie"],
            esclarecimentos=estado.get("esclarecimentos", []),
            dialogo=estado.get("dialogo") or [],
            llm=llm,
        )
        if analise.precisa_esclarecimento:
            registrar(
                eventos, "analista", "interrupcao",
                f"Ambiguidade material — perguntando ao usuário: "
                f"{analise.pergunta_de_esclarecimento}",
                tempo_ms=decorrido_ms(inicio),
            )
        else:
            objetivos = "; ".join(p.objetivo for p in analise.passos)
            registrar(
                eventos, "analista", "plano",
                f"Plano com {len(analise.passos)} passo(s): {objetivos}",
                dados={"premissas": analise.premissas},
                tempo_ms=decorrido_ms(inicio),
            )
            for premissa in analise.premissas:
                registrar(eventos, "analista", "premissa", premissa)
        return {"analise": analise, "chamadas_llm": 1, "trace": eventos}

    def no_esclarecer(estado: EstadoDoAssistente) -> dict:
        """Interrupt: pergunta ao usuário e registra a resposta como
        esclarecimento. Nó dedicado SÓ para o interrupt: na retomada o nó
        re-executa, e aqui não há chamada de LLM para re-executar."""
        pergunta = estado["analise"].pergunta_de_esclarecimento
        resposta_do_usuario = interrupt(pergunta)
        eventos = []
        # V3.6: o DIÁLOGO COMPLETO (par pergunta↔resposta) vai para o log de
        # baixo nível, para a interface e para o estado — a causa do loop
        # era o diálogo unilateral (só as respostas eram guardadas).
        registrar(
            eventos, "esclarecimento", "info",
            f"[Analista perguntou] {pergunta} → "
            f"[Usuário respondeu] {resposta_do_usuario}",
            dados={"pergunta": pergunta, "resposta": resposta_do_usuario},
        )
        par = {"pergunta_do_analista": pergunta,
               "resposta_do_usuario": resposta_do_usuario}
        return {"esclarecimentos": [resposta_do_usuario],
                "dialogo": [par], "trace": eventos}

    def no_engenheiro(estado: EstadoDoAssistente) -> dict:
        """LLM: gera/corrige o SQL do passo atual."""
        eventos = []
        inicio = cronometro()
        llm.zerar()
        indice = estado.get("indice_passo_atual", 0)
        passo = estado["analise"].passos[indice]
        tentativa = estado.get("tentativas_no_passo", 0) + 1
        proposta = gerar_sql(
            objetivo_do_passo=passo.objetivo,
            pergunta_original=estado["pergunta"],
            dossie=estado["dossie"],
            resultados_anteriores=estado.get("resultados", []),
            erro_para_corrigir=estado.get("erro_para_corrigir"),
            instrucao_do_auditor=estado.get("instrucao_do_auditor"),
            llm=llm,
        )
        registrar(
            eventos, "engenheiro", "sql_proposto",
            f"Passo {indice + 1}, tentativa {tentativa}: {proposta.justificativa}",
            dados={"sql": proposta.sql, "passo": indice, "tentativa": tentativa},
            tempo_ms=decorrido_ms(inicio),
            tokens=llm.tokens_da_rodada,
        )
        # Detector de ciclo improdutivo: se isto é uma CORREÇÃO pós-devolução
        # e o SQL proposto é IDÊNTICO ao reprovado, repetir não muda nada
        # (caso clássico: o Auditor pediu mais linhas que o teto permite).
        repetida = bool(
            estado.get("instrucao_do_auditor")
            and proposta.sql.strip()
            == (estado.get("sql_devolvido_pelo_auditor") or "").strip()
        )
        if repetida:
            registrar(eventos, "engenheiro", "info",
                      "Correção repetiu a consulta reprovada — ciclo "
                      "improdutivo; o grafo encerrará com explicação honesta.")
        return {
            "sql_proposto": proposta,
            "correcao_repetida": repetida,
            "tentativas_no_passo": tentativa,
            "erro_para_corrigir": None,      # consumido nesta geração
            "instrucao_do_auditor": None,    # consumida nesta geração
            "chamadas_llm": 1,
            "trace": eventos,
        }

    def no_guardrail(estado: EstadoDoAssistente) -> dict:
        """Determinístico: valida o SQL. Reprovação realimenta o loop."""
        eventos = []
        proposta = estado["sql_proposto"]
        veredito = validar(proposta.sql)
        if veredito.aprovado:
            registrar(eventos, "guardrail", "info", "Consulta aprovada pelo Guardrail.")
            return {"trace": eventos}
        registrar(
            eventos, "guardrail", "sql_reprovado",
            "Guardrail reprovou a consulta — devolvendo ao Engenheiro.",
            dados={"sql": proposta.sql, "motivo": veredito.motivo},
        )
        return {"erro_para_corrigir": f"Guardrail: {veredito.motivo}", "trace": eventos}

    def no_executor(estado: EstadoDoAssistente) -> dict:
        """Determinístico: executa em somente-leitura; sucesso anexa o passo."""
        eventos = []
        proposta = estado["sql_proposto"]
        resultado = executar(proposta.sql, estado["caminho_banco"])
        if resultado.erro:
            registrar(
                eventos, "executor", "sql_erro",
                "Execução falhou — devolvendo ao Engenheiro.",
                dados={"sql": proposta.sql, "motivo": resultado.erro},
                tempo_ms=resultado.tempo_ms,
            )
            return {"erro_para_corrigir": resultado.erro, "trace": eventos}

        indice = estado.get("indice_passo_atual", 0)
        aviso = " (TRUNCADO)" if resultado.truncado else ""
        registrar(
            eventos, "executor", "resultado",
            f"Passo {indice + 1} concluído: {resultado.n_linhas} linha(s){aviso}.",
            dados={"n_linhas": resultado.n_linhas, "truncado": resultado.truncado},
            tempo_ms=resultado.tempo_ms,
        )
        passo_concluido = {
            "objetivo": estado["analise"].passos[indice].objetivo,
            "sql": proposta.sql,
            "justificativa": proposta.justificativa,
            "colunas": resultado.colunas,
            "linhas": resultado.linhas,
            "n_linhas": resultado.n_linhas,
            "truncado": resultado.truncado,
            "tentativas": estado.get("tentativas_no_passo", 1),
        }
        return {
            "resultados": estado.get("resultados", []) + [passo_concluido],
            "indice_passo_atual": indice + 1,
            "tentativas_no_passo": 0,
            "trace": eventos,
        }

    def no_auditor(estado: EstadoDoAssistente) -> dict:
        """LLM: autocorreção nível 2 sobre TODOS os resultados."""
        eventos = []
        inicio = cronometro()
        llm.zerar()
        parecer = auditar(
            estado["pergunta"], estado["analise"],
            estado.get("resultados", []), estado["dossie"],
            dialogo=estado.get("dialogo") or [], llm=llm,
        )
        if parecer.aprovado:
            registrar(eventos, "auditor", "parecer",
                      "Auditoria APROVADA: os resultados respondem a pergunta.",
                      tempo_ms=decorrido_ms(inicio),
                      tokens=llm.tokens_da_rodada)
            return {"chamadas_llm": 1, "trace": eventos}

        indice_refazer = parecer.indice_passo_a_refazer or 0
        devolucoes = estado.get("devolucoes_auditor", 0) + 1
        registrar(
            eventos, "auditor", "devolucao",
            f"Auditoria REPROVADA (devolução {devolucoes}): {parecer.problema}",
            dados={"instrucao": parecer.instrucao_de_correcao,
                   "passo_a_refazer": indice_refazer},
            tempo_ms=decorrido_ms(inicio),
            tokens=llm.tokens_da_rodada,
        )
        return {
            # Refaz do passo indicado em diante (passos posteriores dependem dele).
            "resultados": estado.get("resultados", [])[:indice_refazer],
            "indice_passo_atual": indice_refazer,
            "tentativas_no_passo": 0,
            "devolucoes_auditor": devolucoes,
            "instrucao_do_auditor": parecer.instrucao_de_correcao,
            "sql_devolvido_pelo_auditor": estado["sql_proposto"].sql,
            "chamadas_llm": 1,
            "trace": eventos,
        }

    def no_visualizador(estado: EstadoDoAssistente) -> dict:
        """Após a auditoria aprovar: produz a EspecificacaoVisual do ÚLTIMO
        passo (o que materializa a resposta). modo 'pre_setado' = 0 LLM;
        modo 'agente' = Designer + Guardrail em loop de até
        MAX_TENTATIVAS_VISUAL. NUNCA derruba o fluxo: qualquer falha degrada
        para tabela com motivo no trace."""
        eventos = []
        resultados = estado.get("resultados", [])
        if not resultados:
            espec = _especificacao_tabela(
                [], [], "Sem resultados a visualizar.",
                fallback=True, motivo="Plano sem resultados.",
            )
            registrar(eventos, "visualizador", "visual_fallback",
                      "Sem resultados — tabela vazia de segurança.")
            return {"especificacao_visual": espec, "trace": eventos}

        ultimo = resultados[-1]
        modo = estado.get("modo_visualizacao") or MODO_VISUALIZACAO_PADRAO

        # INTERCEPTOR DETERMINÍSTICO (V3.11): se o usuário pediu TABELA/LISTA,
        # a tabela é FORÇADA aqui — em QUALQUER modo, ANTES do Designer. Tira
        # a decisão do LLM (que ignorava a instrução) e a entrega ao código.
        if _pediu_tabela_explicitamente(estado["pergunta"]):
            espec = _especificacao_tabela(
                ultimo["colunas"], ultimo["linhas"],
                "Você pediu o resultado em tabela.",
            )
            registrar(
                eventos, "visualizador", "visual_pronto",
                "Pedido explícito de tabela — tabela nativa (determinístico, "
                "sem LLM).",
                dados={"modo": modo, "tipo": "tabela"},
            )
            return {"especificacao_visual": espec, "trace": eventos,
                    "chamadas_llm": 0}

        chamadas = 0
        try:
            if modo == "pre_setado":
                inicio = cronometro()
                llm.zerar()
                espec = montar_especificacao_pre_setada(
                    ultimo["colunas"], ultimo["linhas"], estado["pergunta"]
                )
                registrar(
                    eventos, "visualizador", "visual_pronto",
                    f"Visual pré-setado: {espec.tipo} — {espec.justificativa}",
                    dados={"modo": modo, "tipo": espec.tipo},
                    tempo_ms=decorrido_ms(inicio),
                )
                return {"especificacao_visual": espec, "trace": eventos,
                        "chamadas_llm": 0}

            # modo "agente": Designer autora; Guardrail valida; retry com motivo.
            motivo = None
            espec = None
            for tentativa in range(1, MAX_TENTATIVAS_VISUAL + 1):
                inicio = cronometro()
                llm.zerar()
                proposta = propor_visualizacao(
                    estado["pergunta"], ultimo, ultimo["justificativa"],
                    motivo_da_reprova=motivo, llm=llm,
                )
                chamadas += 1
                registrar(
                    eventos, "visualizador", "visual_proposto",
                    f"Tentativa {tentativa}: Designer propôs "
                    f"'{proposta.tipo_grafico}' — {proposta.justificativa}",
                    dados={"tipo": proposta.tipo_grafico},
                    tempo_ms=decorrido_ms(inicio),
                )
                # V3.7: tabela pedida pelo Designer é renderizada nativamente
                # (não tem 'series'; não passa pelo guardrail de option).
                if str(proposta.tipo_grafico).lower() == "tabela":
                    espec = _especificacao_tabela(
                        ultimo["colunas"], ultimo["linhas"],
                        proposta.justificativa or "Resultado em tabela.",
                    )
                    espec.modo = "agente"
                    registrar(eventos, "visualizador", "visual_pronto",
                              "Tabela escolhida pelo Designer.",
                              dados={"modo": "agente", "tipo": "tabela"})
                    break
                veredito = validar_option(proposta.option_json)
                if veredito.aprovado:
                    from app.estado import EspecificacaoVisual
                    espec = EspecificacaoVisual(
                        modo="agente", tipo=proposta.tipo_grafico,
                        option=veredito.option,
                        valor_metrica=None, rotulo_metrica=None,
                        colunas=None, linhas=None,
                        justificativa=proposta.justificativa,
                    )
                    registrar(eventos, "visualizador", "visual_pronto",
                              "Option aprovado pelo Guardrail de Visualização.",
                              dados={"modo": modo, "tipo": espec.tipo})
                    break
                motivo = veredito.motivo
                registrar(eventos, "visualizador", "visual_reprovado",
                          f"Guardrail de Visualização reprovou (tentativa {tentativa}).",
                          dados={"motivo": motivo})
            if espec is None:
                espec = _especificacao_tabela(
                    ultimo["colunas"], ultimo["linhas"],
                    "Tabela de segurança (fallback).",
                    fallback=True,
                    motivo=f"Option reprovado após {MAX_TENTATIVAS_VISUAL} "
                           f"tentativa(s): {motivo}",
                )
                registrar(eventos, "visualizador", "visual_fallback",
                          "Fallback para tabela — a resposta segue intacta.",
                          dados={"motivo": motivo})
        except Exception as excecao:  # noqa: BLE001 — visual nunca derruba resposta
            espec = _especificacao_tabela(
                ultimo["colunas"], ultimo["linhas"],
                "Tabela de segurança (fallback).",
                fallback=True, motivo=f"Exceção no visualizador: {excecao}",
            )
            registrar(eventos, "visualizador", "visual_fallback",
                      f"Exceção no visualizador — fallback tabela: {excecao}")
        return {"especificacao_visual": espec, "trace": eventos,
                "chamadas_llm": chamadas}

    def no_redator(estado: EstadoDoAssistente) -> dict:
        """LLM: o Analista (2ª função) redige a resposta de negócio."""
        eventos = []
        inicio = cronometro()
        llm.zerar()
        resposta = redigir_resposta(
            estado["pergunta"], estado["analise"],
            estado.get("resultados", []), estado["dossie"], llm=llm,
        )
        registrar(eventos, "redator", "resposta", resposta.resposta,
                  dados={"premissas": resposta.premissas_destacadas},
                  tempo_ms=decorrido_ms(inicio),
                      tokens=llm.tokens_da_rodada)
        return {"resposta": resposta, "chamadas_llm": 1, "trace": eventos}

    def no_falha_graciosa(estado: EstadoDoAssistente) -> dict:
        """Determinístico: explicação honesta do que foi tentado."""
        eventos = []
        tentativas = estado.get("tentativas_no_passo", 0)
        devolucoes = estado.get("devolucoes_auditor", 0)
        chamadas = estado.get("chamadas_llm", 0)
        ultimo_erro = estado.get("erro_para_corrigir")
        ultima_instrucao = estado.get("instrucao_do_auditor")
        analise = estado.get("analise")
        esclarecimentos = estado.get("esclarecimentos", [])
        if estado.get("correcao_repetida"):
            # Caso específico: Engenheiro repetiu o SQL após a devolução —
            # tipicamente o Auditor pediu o impossível (mais que o teto).
            explicacao = (
                "Ciclo improdutivo detectado: após a devolução do Auditor, o "
                "Engenheiro propôs exatamente a mesma consulta — repetir não "
                "muda o resultado. Reformule a pergunta (ex.: peça um "
                "AGREGADO, como total por mês ou por canal, ou critérios "
                "mais específicos) e envie de novo — o fluxo recomeça do zero."
            )
            registrar(eventos, "falha_graciosa", "falha_graciosa", explicacao)
            return {"falha_graciosa": explicacao, "trace": eventos}
        if analise is not None and analise.pedido_fora_de_escopo:
            # Caso específico: pedido de ESCRITA (fora do escopo somente-leitura).
            motivo = analise.motivo_fora_de_escopo or ""
            if getattr(analise, "pedido_de_escrita", False):
                # Recusa de SEGURANÇA (CRUD): mantém o selo somente-leitura.
                explicacao = (
                    "Este assistente é SOMENTE LEITURA: consulta e analisa os "
                    "dados, mas não os altera. "
                    + (f"{motivo} " if motivo else "")
                    + "Reformule como uma CONSULTA e envie de novo — o fluxo "
                    "recomeça do zero."
                )
            else:
                # Recusa CONTEXTUAL do Analista: a mensagem é o próprio
                # motivo (personalizado ao caso), sem o selo de CRUD.
                explicacao = (
                    (f"{motivo} " if motivo else
                     "Não foi possível montar um plano para esta pergunta "
                     "com os dados disponíveis. ")
                    + "Reformule a pergunta com base nos dados do banco e "
                    "envie de novo — o fluxo recomeça do zero."
                )
            registrar(eventos, "falha_graciosa", "falha_graciosa", explicacao)
            return {"falha_graciosa": explicacao, "trace": eventos}
        if (analise is not None and analise.precisa_esclarecimento
                and len(esclarecimentos) >= MAX_ESCLARECIMENTOS):
            # Caso específico: o teto do ciclo de esclarecimento estourou.
            explicacao = (
                "Não foi possível definir uma estratégia de resposta para a sua "
                f"pergunta, mesmo após {len(esclarecimentos)} esclarecimento(s). "
                "Reformule a pergunta (ex.: diga diretamente a métrica e o "
                "período desejados) e envie de novo — o fluxo recomeça do zero."
            )
            registrar(eventos, "falha_graciosa", "falha_graciosa", explicacao)
            return {"falha_graciosa": explicacao, "trace": eventos}
        partes = [
            "Não consegui chegar a uma resposta confiável dentro dos limites "
            "de segurança do sistema."
        ]
        if ultimo_erro:
            partes.append(
                f"Tentei corrigir a consulta {tentativas} vez(es); o último "
                f"erro foi: {ultimo_erro}"
            )
        if ultima_instrucao:
            partes.append(
                f"O Auditor devolveu o trabalho {devolucoes} vez(es); a última "
                f"instrução foi: {ultima_instrucao}"
            )
        partes.append(
            f"({chamadas} chamada(s) ao modelo; o trace técnico tem cada tentativa.)"
        )
        explicacao = " ".join(partes)
        registrar(eventos, "falha_graciosa", "falha_graciosa", explicacao)
        return {"falha_graciosa": explicacao, "trace": eventos}

    # ── Arestas condicionais (o roteamento clássico: funções puras) ─────────

    def _estourou_orcamento(estado) -> bool:
        return estado.get("chamadas_llm", 0) >= ORCAMENTO_GLOBAL_CHAMADAS_LLM

    def decidir_apos_analista(estado: EstadoDoAssistente) -> str:
        if _estourou_orcamento(estado):
            return "falha_graciosa"
        if estado["analise"].pedido_fora_de_escopo:
            return "falha_graciosa"        # escrita: recusa direta, sem perguntar
        if estado["analise"].precisa_esclarecimento:
            # Teto DEDICADO do ciclo analista↔esclarecer (correção crítica do
            # fogo do M4: sem este teto, um Analista que insiste em reanalisar
            # a pergunta original prende o usuário em loop de esclarecimentos).
            if len(estado.get("esclarecimentos", [])) >= MAX_ESCLARECIMENTOS:
                return "falha_graciosa"
            return "esclarecer"
        return "engenheiro"

    def decidir_apos_guardrail(estado: EstadoDoAssistente) -> str:
        if estado.get("correcao_repetida"):
            return "falha_graciosa"        # ciclo improdutivo: repetir é inútil
        if estado.get("erro_para_corrigir") is None:
            return "executor"
        if (estado.get("tentativas_no_passo", 0) >= MAX_TENTATIVAS_SQL
                or _estourou_orcamento(estado)):
            return "falha_graciosa"
        return "engenheiro"

    def decidir_apos_executor(estado: EstadoDoAssistente) -> str:
        if estado.get("erro_para_corrigir") is not None:
            if (estado.get("tentativas_no_passo", 0) >= MAX_TENTATIVAS_SQL
                    or _estourou_orcamento(estado)):
                return "falha_graciosa"
            return "engenheiro"
        if _estourou_orcamento(estado):
            return "falha_graciosa"
        if estado["indice_passo_atual"] < len(estado["analise"].passos):
            return "engenheiro"            # próximo passo do plano
        return "auditor"                   # plano completo

    def decidir_apos_auditor(estado: EstadoDoAssistente) -> str:
        if estado.get("instrucao_do_auditor") is None:
            return "visualizador"          # aprovado → visual antes da redação
        if (estado.get("devolucoes_auditor", 0) > MAX_DEVOLUCOES_AUDITOR
                or _estourou_orcamento(estado)):
            return "falha_graciosa"
        return "engenheiro"                # devolução

    # ── Montagem ─────────────────────────────────────────────────────────────
    grafo = StateGraph(EstadoDoAssistente)
    grafo.add_node("perfilador", no_perfilador)
    grafo.add_node("analista", no_analista)
    grafo.add_node("esclarecer", no_esclarecer)
    grafo.add_node("engenheiro", no_engenheiro)
    grafo.add_node("guardrail", no_guardrail)
    grafo.add_node("executor", no_executor)
    grafo.add_node("auditor", no_auditor)
    grafo.add_node("visualizador", no_visualizador)
    grafo.add_node("redator", no_redator)
    grafo.add_node("falha_graciosa", no_falha_graciosa)

    grafo.add_edge(START, "perfilador")
    grafo.add_edge("perfilador", "analista")
    grafo.add_conditional_edges(
        "analista", decidir_apos_analista,
        {"esclarecer": "esclarecer", "engenheiro": "engenheiro",
         "falha_graciosa": "falha_graciosa"},
    )
    grafo.add_edge("esclarecer", "analista")
    grafo.add_edge("engenheiro", "guardrail")
    grafo.add_conditional_edges(
        "guardrail", decidir_apos_guardrail,
        {"executor": "executor", "engenheiro": "engenheiro",
         "falha_graciosa": "falha_graciosa"},
    )
    grafo.add_conditional_edges(
        "executor", decidir_apos_executor,
        {"engenheiro": "engenheiro", "auditor": "auditor",
         "falha_graciosa": "falha_graciosa"},
    )
    grafo.add_conditional_edges(
        "auditor", decidir_apos_auditor,
        {"visualizador": "visualizador", "engenheiro": "engenheiro",
         "falha_graciosa": "falha_graciosa"},
    )
    grafo.add_edge("visualizador", "redator")
    grafo.add_edge("redator", END)
    grafo.add_edge("falha_graciosa", END)

    # checkpointer=False → compila SEM checkpointer (o LangGraph Studio injeta
    # o dele). checkpointer=None → nosso MemorySaver com allowlist (uso normal).
    if checkpointer is False:
        return grafo.compile()
    return grafo.compile(checkpointer=checkpointer or _criar_checkpointer())
