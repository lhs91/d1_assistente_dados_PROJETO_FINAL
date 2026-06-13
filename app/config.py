# -*- coding: utf-8 -*-
"""
config.py — Configuração central do projeto d1_assistente_dados.

Ponto único de verdade para modelos, limites e caminhos. Trocar o modelo,
o teto de linhas ou o limiar do detector se faz AQUI, e em nenhum outro lugar.

Decisões registradas na SPEC do Marco 1:
- gemini-2.5-pro para TODOS os agentes (custo não é restrição neste desafio).
- temperature=0 (reprodutibilidade).
- Os componentes determinísticos (Perfilador, Guardrail, Executor) funcionam
  SEM chave de API — a chave só é exigida quando o LLM é de fato usado.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Carrega o .env da raiz do projeto, se existir (silencioso se não existir).
load_dotenv()

# ── Modelos e agentes ────────────────────────────────────────────────────────
MODELO_AGENTES = "gemini-2.5-pro"   # modelo único para todos os agentes
TEMPERATURA = 0.0                   # reprodutibilidade

# ── Limites do Executor e do Perfilador ─────────────────────────────────────
LIMITE_CARDINALIDADE = 25           # camada 4: máx. de distintos p/ listar valores
LIMITE_AMOSTRAS = 5                 # camada 3: linhas de amostra por tabela

# ── Detector de denormalização (camada 6) ───────────────────────────────────
LIMIAR_DIVERGENCIA = 0.05           # fração mínima de linhas divergentes p/ alertar
TOLERANCIA_REAL = 0.01              # tolerância na comparação de valores REAL

# ── Caminhos ─────────────────────────────────────────────────────────────────
RAIZ_PROJETO = Path(__file__).resolve().parent.parent
CAMINHO_BANCO_PADRAO = RAIZ_PROJETO / "data" / "anexo_desafio_1.db"

# ── Visualização (Marco 3) ───────────────────────────────────────────────────
MODO_VISUALIZACAO_PADRAO = "agente"  # ou "pre_setado"; toggle de UI no M4
MAX_TENTATIVAS_VISUAL = 2            # 1ª proposta + 1 correção; depois tabela
LIMITE_TAMANHO_OPTION = 50_000       # caracteres do option_json
LIMITE_PROFUNDIDADE_OPTION = 12      # aninhamento máximo do JSON
MIN_PONTOS_LINHA = 3                 # série temporal vira linha com >= 3 pontos
MAX_CATEGORIAS_BARRA = 25            # acima disso, barra vira ruído -> tabela

# ── Interface (Marco 4) ──────────────────────────────────────────────────────
TITULO_DA_INTERFACE = "Assistente Virtual de Dados — Multiagêntico"
ALTURA_GRAFICO_UI = "480px"

# ── Observabilidade ──────────────────────────────────────────────────────────
PROJETO_LANGSMITH = "d1_franq"      # separado do d2_franq (traces não se misturam)


class ErroDeConfiguracao(Exception):
    """Erro de configuração do ambiente (ex.: chave de API ausente)."""


def carregar_chave_google() -> str:
    """Lê a GOOGLE_API_KEY do ambiente/.env.

    Levanta ErroDeConfiguracao com orientação clara se ausente. É chamada
    APENAS no momento de usar o LLM — os componentes determinísticos não
    dependem dela.
    """
    chave = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not chave:
        raise ErroDeConfiguracao(
            "GOOGLE_API_KEY não encontrada. Crie um arquivo .env na raiz do "
            "projeto (use o .env.exemplo como modelo) ou defina a variável de "
            "ambiente antes de usar o LLM."
        )
    return chave


def langsmith_esta_configurado() -> bool:
    """True se há chave do LangSmith no ambiente (tracing é opcional)."""
    return bool(
        os.environ.get("LANGSMITH_API_KEY", "").strip()
        or os.environ.get("LANGCHAIN_API_KEY", "").strip()
    )


def configurar_langsmith() -> bool:
    """Liga o tracing do LangSmith quando há chave no ambiente.

    Seta as DUAS gerações de variáveis (o SDK novo lê LANGSMITH_*; versões
    do langchain leem LANGCHAIN_*) — foi a ausência da dupla que deixava o
    painel em 'Waiting for traces'. setdefault respeita valores que o dev
    já tenha definido no .env. Os traces vão para o projeto d1_franq:
    no painel web, abra Projects > d1_franq (não o default).
    Retorna True se o tracing ficou ativo."""
    if not langsmith_esta_configurado():
        return False
    chave = (os.environ.get("LANGSMITH_API_KEY", "").strip()
             or os.environ.get("LANGCHAIN_API_KEY", "").strip())
    os.environ.setdefault("LANGSMITH_API_KEY", chave)
    os.environ.setdefault("LANGCHAIN_API_KEY", chave)
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", PROJETO_LANGSMITH)
    os.environ.setdefault("LANGCHAIN_PROJECT", PROJETO_LANGSMITH)
    return True


def criar_llm():
    """Fábrica única do LLM do projeto: MODELO_AGENTES + TEMPERATURA.

    O import é feito AQUI (tardio) de propósito: os módulos determinísticos
    importam config sem arrastar o SDK do LLM; e os testes determinísticos
    rodam sem chave de API.
    """
    chave = carregar_chave_google()  # falha clara ANTES de instanciar
    configurar_langsmith()
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=MODELO_AGENTES,
        temperature=TEMPERATURA,
        google_api_key=chave,
    )

# ── Tetos de contenção do grafo (Marco 2) ────────────────────────────────────
MAX_TENTATIVAS_SQL = 3              # gerações de SQL por passo (1ª + correções)
MAX_DEVOLUCOES_AUDITOR = 15         # ciclos de devolução semântica (decisão do dev)
MAX_ESCLARECIMENTOS = 3             # perguntas ao usuário por pergunta; na 4ª, falha graciosa
ORCAMENTO_GLOBAL_CHAMADAS_LLM = 40  # teto absoluto de chamadas LLM por pergunta
# (40 comporta o teto do auditor: 15 devoluções × ~2 chamadas + plano base +
#  visual. Regra de coerência testada: ORCAMENTO >= TENTATIVAS + DEVOLUCOES.)
