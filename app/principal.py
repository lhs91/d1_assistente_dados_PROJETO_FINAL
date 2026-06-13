# -*- coding: utf-8 -*-
"""
principal.py — CLI do assistente / motor headless.

Marco 2: o CLI invoca o GRAFO multiagêntico (responder_pergunta). Se o
Analista pedir esclarecimento, o grafo pausa (interrupt) e `responder_interrupt`
é chamado — no CLI é input(); nos testes, uma função roteirizada; no M4, a UI.

O fluxo POC do Marco 1 fica preservado em responder_pergunta_poc (baseline
histórico; coberto pelos testes do marco1).

Uso: python -m app.principal "sua pergunta" [--banco caminho/banco.db]
"""
import argparse
import uuid
from pathlib import Path

from langgraph.types import Command

from app.config import CAMINHO_BANCO_PADRAO
from app.executor import executar
from app.gerador_sql_poc import gerar_sql
from app.guardrail_sql import validar
from app.perfilador import perfilar, renderizar_para_prompt
from app.trace import renderizar_trace


def responder_pergunta(
    pergunta: str,
    caminho_banco: Path = CAMINHO_BANCO_PADRAO,
    llm=None,
    responder_interrupt=None,
    modo_visualizacao: str = "agente",
) -> dict:
    """Motor headless do Marco 2: invoca o grafo compilado.

    `responder_interrupt`: callable(pergunta_de_esclarecimento) → resposta do
    usuário. Obrigatório quando o grafo pedir esclarecimento (o CLI passa
    input(); os testes, uma função roteirizada).
    Retorna {resposta, premissas, falha_graciosa, trace, resultados}.
    """
    from app.grafo import construir_grafo  # import local: o CLI POC não paga o grafo

    grafo = construir_grafo(llm=llm)
    configuracao = {"configurable": {"thread_id": str(uuid.uuid4())}}
    estado_inicial = {
        "pergunta": pergunta,
        "caminho_banco": str(caminho_banco),
        "modo_visualizacao": modo_visualizacao,
        "indice_passo_atual": 0,
        "resultados": [],
        "tentativas_no_passo": 0,
        "devolucoes_auditor": 0,
        "chamadas_llm": 0,
        "esclarecimentos": [],
        "trace": [],
    }

    estado = grafo.invoke(estado_inicial, configuracao)
    while "__interrupt__" in estado:
        pergunta_de_esclarecimento = estado["__interrupt__"][0].value
        if responder_interrupt is None:
            raise RuntimeError(
                "O grafo pediu esclarecimento, mas nenhum responder_interrupt "
                "foi fornecido."
            )
        resposta_do_usuario = responder_interrupt(pergunta_de_esclarecimento)
        estado = grafo.invoke(Command(resume=resposta_do_usuario), configuracao)

    resposta = estado.get("resposta")
    return {
        "especificacao_visual": estado.get("especificacao_visual"),
        "pergunta": pergunta,
        "resposta": resposta.resposta if resposta else None,
        "premissas": resposta.premissas_destacadas if resposta else [],
        "impactos_e_acoes": resposta.impactos_e_acoes if resposta else [],
        "falha_graciosa": estado.get("falha_graciosa"),
        "resultados": estado.get("resultados", []),
        "trace": estado.get("trace", []),
        "chamadas_llm": estado.get("chamadas_llm", 0),
    }


def responder_pergunta_poc(
    pergunta: str,
    caminho_banco: Path = CAMINHO_BANCO_PADRAO,
    llm=None,
) -> dict:
    """Fluxo POC do Marco 1 (baseline histórico): perfilar → gerar_sql →
    Guardrail → Executor. Mantido para regressão e como referência no
    Comparador (M5)."""
    print(f"[INFO] Pergunta recebida: {pergunta}")

    print("[INFO] Etapa 1/4 — perfilando o banco (dossiê em 6 camadas)...")
    perfil = perfilar(caminho_banco)
    dossie = renderizar_para_prompt(perfil)
    print(
        f"[INFO] Dossiê pronto: {len(perfil.estrutura)} tabelas, "
        f"{len(perfil.alertas_qualidade)} alerta(s) de qualidade."
    )

    print("[INFO] Etapa 2/4 — gerando SQL com o Gemini...")
    gerado = gerar_sql(pergunta, dossie, llm=llm)
    print(f"[INFO] SQL proposto: {gerado.sql}")

    print("[INFO] Etapa 3/4 — validando no Guardrail SQL...")
    veredito = validar(gerado.sql)
    if not veredito.aprovado:
        print(f"[ERRO] Guardrail reprovou a consulta: {veredito.motivo}")
        return {
            "pergunta": pergunta,
            "sql": gerado.sql,
            "justificativa": gerado.justificativa,
            "aprovado_guardrail": False,
            "erro": f"Guardrail: {veredito.motivo}",
            "resultado": None,
        }
    print("[INFO] Guardrail aprovou a consulta.")

    print("[INFO] Etapa 4/4 — executando (somente-leitura)...")
    resultado = executar(gerado.sql, caminho_banco)
    if resultado.erro:
        print(f"[ERRO] Execução falhou: {resultado.erro}")
        return {
            "pergunta": pergunta,
            "sql": gerado.sql,
            "justificativa": gerado.justificativa,
            "aprovado_guardrail": True,
            "erro": f"Execução: {resultado.erro}",
            "resultado": None,
        }
    aviso = " (TRUNCADO)" if resultado.truncado else ""
    print(
        f"[INFO] Consulta executada: {resultado.n_linhas} linha(s){aviso} "
        f"em {resultado.tempo_ms:.1f} ms."
    )
    return {
        "pergunta": pergunta,
        "sql": gerado.sql,
        "justificativa": gerado.justificativa,
        "aprovado_guardrail": True,
        "erro": None,
        "resultado": resultado,
    }


def _perguntar_no_terminal(pergunta_de_esclarecimento: str) -> str:
    """responder_interrupt do CLI: pergunta no terminal e devolve a resposta."""
    print(f"\n[?] O assistente precisa de um esclarecimento:")
    print(f"    {pergunta_de_esclarecimento}")
    return input("    Sua resposta: ").strip()


def principal() -> None:
    """Ponto de entrada do CLI (Marco 2: grafo completo)."""
    parser = argparse.ArgumentParser(
        description="Assistente Virtual de Dados — grafo multiagêntico (Marco 2)."
    )
    parser.add_argument("pergunta", help="A pergunta em linguagem natural.")
    parser.add_argument(
        "--banco",
        type=Path,
        default=CAMINHO_BANCO_PADRAO,
        help="Caminho do banco SQLite (padrão: data/anexo_desafio_1.db).",
    )
    parser.add_argument(
        "--modo",
        choices=["agente", "pre_setado"],
        default=None,
        help="Autor do visual (padrão: config.MODO_VISUALIZACAO_PADRAO).",
    )
    parser.add_argument(
        "--preview",
        nargs="?",
        const="preview_visual.html",
        default=None,
        help="Gera o preview HTML do visual (padrão: preview_visual.html).",
    )
    argumentos = parser.parse_args()

    from app.config import ErroDeConfiguracao, configurar_langsmith
    from app.cores import banner, pintar_cabecalho, pintar_premissa, pintar_resposta
    from app.executor import ErroDeBanco
    if configurar_langsmith():
        print("[INFO] LangSmith ATIVO — traces no projeto 'd1_franq' "
              "(no painel: Projects > d1_franq).")
    else:
        print("[INFO] LangSmith inativo (LANGSMITH_API_KEY ausente no .env).")
    print(banner("TRACE TÉCNICO — acompanhe o raciocínio dos agentes"))
    try:
        from app.config import MODO_VISUALIZACAO_PADRAO
        saida = responder_pergunta(
            argumentos.pergunta,
            argumentos.banco,
            responder_interrupt=_perguntar_no_terminal,
            modo_visualizacao=argumentos.modo or MODO_VISUALIZACAO_PADRAO,
        )
    except (ErroDeConfiguracao, ErroDeBanco) as excecao:
        print(f"[ERRO] {excecao}")
        return

    print("\n" + pintar_cabecalho("=" * 72))
    if saida["falha_graciosa"]:
        print(pintar_cabecalho("RESPOSTA (com ressalvas):"))
        print(saida["falha_graciosa"])
    else:
        print(pintar_cabecalho("RESPOSTA:"))
        print(pintar_resposta(saida["resposta"]))
        if saida["premissas"]:
            print("\nPremissas assumidas:")
            for premissa in saida["premissas"]:
                print(pintar_premissa(f"  - {premissa}"))
    print(pintar_cabecalho("=" * 72))

    if argumentos.preview and saida.get("especificacao_visual"):
        from app.visualizacao.preview_html import gerar_preview_html
        caminho = gerar_preview_html(
            saida["especificacao_visual"], argumentos.pergunta,
            saida["resposta"], Path(argumentos.preview),
        )
        print(f"[INFO] Preview do visual gravado em: {caminho} (abra no navegador)")


if __name__ == "__main__":
    principal()
