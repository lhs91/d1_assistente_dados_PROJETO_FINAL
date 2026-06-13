# -*- coding: utf-8 -*-
"""
estado.py — O estado do grafo e as saídas estruturadas dos agentes.

O estado é o contrato central do roteamento clássico multiagêntico: as
arestas condicionais (funções Python puras) decidem o caminho lendo APENAS
estes campos. Campos com reducer `add` acumulam entre nós (trace,
esclarecimentos, contadores).
"""
import operator
from dataclasses import dataclass
from typing import Annotated, TypedDict

from pydantic import BaseModel, Field


# ── Saídas estruturadas dos agentes (contratos com o LLM) ───────────────────

class PassoDoPlano(BaseModel):
    """Um passo do plano de análise (uma consulta a ser feita)."""
    objetivo: str = Field(description="O que este passo descobre, em linguagem clara.")


class AnaliseDaPergunta(BaseModel):
    """Saída do Analista de Negócios (entrada do fluxo)."""
    precisa_esclarecimento: bool = Field(
        description="True APENAS se a ambiguidade mudaria materialmente a resposta."
    )
    pergunta_de_esclarecimento: str | None = Field(
        default=None, description="A pergunta ao usuário, se precisar esclarecer."
    )
    premissas: list[str] = Field(
        default_factory=list,
        description="Tudo que foi assumido (ex.: 'maio = 2025, único na base').",
    )
    passos: list[PassoDoPlano] = Field(
        default_factory=list, description="1..N consultas planejadas, em ordem."
    )
    pedido_fora_de_escopo: bool = Field(
        default=False,
        description=("True se a pergunta pede ALTERAR dados (UPDATE/INSERT/"
                     "DELETE/criar/apagar) — fora do escopo somente-leitura. "
                     "NUNCA peça esclarecimento nesse caso."),
    )
    motivo_fora_de_escopo: str | None = Field(
        default=None,
        description="Explicação curta do que foi pedido e por que está fora do escopo.",
    )
    pedido_de_escrita: bool = Field(
        default=False,
        description=("True SOMENTE se o fora-de-escopo for por ESCRITA "
                     "(UPDATE/INSERT/DELETE/criar/apagar). False para "
                     "qualquer outra recusa — a mensagem ao usuário muda."),
    )


class SqlDoPasso(BaseModel):
    """Saída do Engenheiro de Dados para um passo."""
    sql: str = Field(description="A consulta SQL (apenas UM SELECT).")
    justificativa: str = Field(description="Por que esta consulta cumpre o objetivo.")


class ParecerDoAuditor(BaseModel):
    """Saída do Auditor de Dados (autocorreção nível 2)."""
    aprovado: bool
    problema: str | None = Field(
        default=None, description="O que está errado, se reprovado."
    )
    instrucao_de_correcao: str | None = Field(
        default=None, description="Como o Engenheiro deve corrigir."
    )
    indice_passo_a_refazer: int | None = Field(
        default=None, description="Índice (0-based) do passo a regenerar."
    )


class PropostaDoDesigner(BaseModel):
    """Saída do Designer de Visualização (4º agente, Marco 3)."""
    tipo_grafico: str = Field(
        description="Tipo do gráfico proposto (ex.: barra, linha, pizza, "
                    "dispersao, heatmap). Informativo."
    )
    option_json: str = Field(
        description="O option ECharts COMPLETO como string JSON PURA — "
                    "dados embutidos; PROIBIDO function/arrow/eval/JsCode."
    )
    justificativa: str = Field(
        description="Por que este gráfico serve a esta pergunta (1-2 frases)."
    )


@dataclass
class EspecificacaoVisual:
    """O que o renderizador (preview no M3; st_echarts no M4) consome."""
    modo: str                       # 'pre_setado' | 'agente'
    tipo: str                       # 'metrica' | 'tabela' | 'linha' | 'barra' | livre
    option: dict | None             # option ECharts VALIDADO (None p/ metrica/tabela)
    valor_metrica: str | None       # p/ tipo 'metrica'
    rotulo_metrica: str | None      # p/ tipo 'metrica'
    colunas: list | None            # p/ tipo 'tabela'
    linhas: list | None             # p/ tipo 'tabela'
    justificativa: str
    fallback_usado: bool = False
    motivo_fallback: str | None = None


class RespostaDeNegocio(BaseModel):
    """Saída final (Analista de Negócios, 2ª função: redator)."""
    resposta: str = Field(description="Resposta em linguagem de diretor, sem jargão.")
    premissas_destacadas: list[str] = Field(
        default_factory=list, description="O que foi assumido, em destaque."
    )
    impactos_e_acoes: list[str] = Field(
        default_factory=list,
        description=("Conclusão executiva: 2 parágrafos sobre IMPACTOS PARA O "
                     "NEGÓCIO e AÇÕES para amenizar consequências negativas e "
                     "impulsionar resultados, derivados DOS DADOS desta "
                     "resposta. Cada item é um parágrafo."),
    )


# ── Estado do grafo ──────────────────────────────────────────────────────────

class ResultadoDoPasso(TypedDict):
    """Um passo do plano já executado com sucesso."""
    objetivo: str
    sql: str
    justificativa: str
    colunas: list
    linhas: list
    n_linhas: int
    truncado: bool
    tentativas: int          # quantas gerações de SQL este passo consumiu


class EstadoDoAssistente(TypedDict, total=False):
    # entrada
    pergunta: str
    caminho_banco: str
    modo_visualizacao: str                       # default "agente"; usado no M3+
    # contexto determinístico
    dossie: str
    # plano e execução
    analise: AnaliseDaPergunta | None
    esclarecimentos: Annotated[list, operator.add]   # respostas aos interrupts
    dialogo: Annotated[list, operator.add]           # PARES {pergunta_do_analista, resposta_do_usuario}
    sql_devolvido_pelo_auditor: str | None       # SQL da versão reprovada
    correcao_repetida: bool                      # Engenheiro repetiu o SQL pós-devolução
    indice_passo_atual: int
    resultados: list                              # list[ResultadoDoPasso]
    sql_proposto: SqlDoPasso | None               # em trânsito p/ guardrail/executor
    erro_para_corrigir: str | None                # motivo (Guardrail/SQLite) p/ retry
    tentativas_no_passo: int
    devolucoes_auditor: int
    instrucao_do_auditor: str | None
    chamadas_llm: Annotated[int, operator.add]    # orçamento global (acumula)
    # saída
    especificacao_visual: EspecificacaoVisual | None
    resposta: RespostaDeNegocio | None
    falha_graciosa: str | None
    trace: Annotated[list, operator.add]          # list[EventoTrace] — só cresce
