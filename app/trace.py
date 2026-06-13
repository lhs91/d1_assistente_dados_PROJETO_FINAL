# -*- coding: utf-8 -*-
"""
trace.py — O trace estruturado: a matéria-prima da transparência.

Todo nó do grafo registra eventos por aqui (formato único). No Marco 4, o
streaming em tempo real e o "expander técnico" da UI leem exatamente esta
estrutura — nada precisa ser reconstruído.

Nota de implementação (desvio registrado da SPEC): no LangGraph, nós devolvem
ATUALIZAÇÕES de estado (não mutam o estado recebido). Por isso `registrar`
anexa a uma lista local de eventos do nó, e o nó devolve {"trace": eventos};
o campo `trace` do estado usa reducer de concatenação (Annotated[list, add]).
"""
import time
from dataclasses import dataclass, field


@dataclass
class EventoTrace:
    """Um evento do raciocínio do sistema."""
    no: str                  # 'perfilador' | 'analista' | 'esclarecimento' |
                             # 'engenheiro' | 'guardrail' | 'executor' |
                             # 'auditor' | 'redator' | 'falha_graciosa'
    tipo: str                # 'info' | 'plano' | 'premissa' | 'interrupcao' |
                             # 'sql_proposto' | 'sql_reprovado' | 'sql_erro' |
                             # 'resultado' | 'devolucao' | 'parecer' |
                             # 'resposta' | 'falha_graciosa'
    conteudo: str            # texto legível (expander técnico do M4)
    dados: dict = field(default_factory=dict)   # payload estruturado
    tempo_ms: float | None = None
    tokens: int | None = None        # total de tokens das chamadas do nó


def registrar(
    eventos: list,
    no: str,
    tipo: str,
    conteudo: str,
    dados: dict | None = None,
    tempo_ms: float | None = None,
    tokens: int | None = None,
) -> None:
    """Função ÚNICA de registro: anexa um EventoTrace à lista do nó.

    Centralizar aqui garante formato uniforme — o streaming do M4 sai de
    graça. Imprime também o [INFO]/[ERRO] no padrão do projeto (CLI do M2)."""
    eventos.append(
        EventoTrace(no=no, tipo=tipo, conteudo=conteudo,
                    dados=dados or {}, tempo_ms=tempo_ms, tokens=tokens)
    )
    from app.cores import pintar_erro, pintar_no
    eh_erro = tipo in {"sql_reprovado", "sql_erro", "falha_graciosa"}
    prefixo = pintar_erro("[ERRO]") if eh_erro else "[INFO]"
    if no == "pergunta":
        print("\n" * 4)        # 5 quebras separam cada pergunta no terminal
    print(f"{prefixo} {pintar_no(no)} {conteudo}")


def cronometro() -> float:
    """Marco de tempo (perf_counter) para medir duração de etapas."""
    return time.perf_counter()


def decorrido_ms(inicio: float) -> float:
    """Milissegundos desde o marco `inicio`."""
    return (time.perf_counter() - inicio) * 1000


def renderizar_trace(trace: list) -> str:
    """Versão legível do trace completo — o 'expander técnico' em texto puro:
    plano, premissas, cada SQL com tentativas (antes/depois das correções),
    pareceres do Auditor e a conclusão."""
    linhas = ["=== TRACE TÉCNICO (como cheguei aqui) ==="]
    for evento in trace:
        tempo = f" ({evento.tempo_ms:.0f} ms)" if evento.tempo_ms is not None else ""
        from app.cores import rotulo_do_no
        linhas.append(
            f"[{rotulo_do_no(evento.no)}] {evento.tipo}{tempo}: "
            f"{evento.conteudo}")
        if evento.tipo in {"sql_proposto", "sql_reprovado", "sql_erro"} and evento.dados.get("sql"):
            linhas.append(f"    SQL: {evento.dados['sql']}")
        if evento.dados.get("motivo"):
            linhas.append(f"    motivo: {evento.dados['motivo']}")
        if evento.dados.get("instrucao"):
            linhas.append(f"    instrução: {evento.dados['instrucao']}")
    return "\n".join(linhas)
