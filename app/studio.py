# -*- coding: utf-8 -*-
"""
studio.py — Ponto de entrada do grafo para o LangGraph Studio.

O LangGraph Studio ('langgraph dev') NÃO chama o nosso pipeline: ele importa
um grafo JÁ COMPILADO desta variável de módulo e o executa com a infraestrutura
DELE (servidor, checkpointer persistente, UI de inspeção). Por isso expomos
aqui um grafo compilado SEM o nosso MemorySaver — o Studio injeta o checkpointer
próprio (passar o nosso causaria conflito de persistência).

Apontado por langgraph.json: {"graphs": {"assistente": "./app/studio.py:grafo"}}.

Requisitos para funcionar:
- a GOOGLE_API_KEY do .env (o Studio carrega o .env apontado em langgraph.json);
- a CLI instalada: pip install "langgraph-cli[inmem]".
Rodar (da raiz do projeto): langgraph dev   (ou: langgraph dev --tunnel)
"""
from app.grafo import construir_grafo

# Grafo compilado para o Studio: checkpointer=False faz o construir_grafo NÃO
# anexar o MemorySaver — o Studio fornece o seu. (Veja a nota em grafo.py.)
grafo = construir_grafo(checkpointer=False)
