# -*- coding: utf-8 -*-
"""
cores.py — Cores do terminal (regra do projeto a partir do Marco 2).

Esquema (por papel, não por estética):
- Agentes de negócio em azul (analista) e ciano (engenheiro);
- Fiscalização salta aos olhos: guardrail amarelo, auditor magenta;
- Mecânica determinística discreta: executor verde, perfilador cinza;
- [ERRO] sempre vermelho; RESPOSTA em verde negrito; cabeçalhos em azul claro.

colorama garante compatibilidade com o PowerShell/Windows (init com autoreset:
cada print volta ao normal sozinho, sem vazar cor para a linha seguinte).
"""
from colorama import Fore, Style, init as _init_colorama

_init_colorama(autoreset=True)

COR_POR_NO = {
    "perfilador": Fore.LIGHTBLACK_EX,
    "analista": Fore.BLUE,
    "esclarecimento": Fore.LIGHTYELLOW_EX,
    "engenheiro": Fore.CYAN,
    "guardrail": Fore.YELLOW,
    "executor": Fore.GREEN,
    "auditor": Fore.MAGENTA,
    "redator": Fore.LIGHTGREEN_EX,
    "falha_graciosa": Fore.RED,
}

VERMELHO = Fore.RED
VERDE = Fore.GREEN
AMARELO = Fore.YELLOW
AZUL_CLARO = Fore.LIGHTBLUE_EX
NEGRITO = Style.BRIGHT
NORMAL = Style.RESET_ALL


# Nome de EXIBIÇÃO dos papéis (ids internos permanecem estáveis).
NOME_EXIBIDO = {"falha_graciosa": "teto estourado", "redator": "diretor"}


def rotulo_do_no(no: str) -> str:
    """O nome do papel como o usuário deve LER (ex.: 'teto estourado')."""
    return NOME_EXIBIDO.get(no, no)


def pintar_no(no: str) -> str:
    """O nome do nó/agente na cor do seu papel: '[analista]' azul etc."""
    cor = COR_POR_NO.get(no, "")
    return f"{cor}[{rotulo_do_no(no)}]{NORMAL}"


def pintar_erro(texto: str) -> str:
    """Linha de erro em vermelho."""
    return f"{VERMELHO}{texto}{NORMAL}"


def pintar_resposta(texto: str) -> str:
    """A entrega final em verde negrito."""
    return f"{NEGRITO}{VERDE}{texto}{NORMAL}"


def pintar_premissa(texto: str) -> str:
    """Premissas em amarelo (pedem a atenção do leitor)."""
    return f"{AMARELO}{texto}{NORMAL}"


def pintar_cabecalho(texto: str) -> str:
    """Cabeçalhos de navegação (trace, perguntas, resumo) em azul claro."""
    return f"{NEGRITO}{AZUL_CLARO}{texto}{NORMAL}"


def banner(texto: str, largura: int = 72) -> str:
    """Banner de 3 linhas em azul claro: moldura de '=' com o texto centrado."""
    miolo = f" {texto} "
    return pintar_cabecalho(
        "=" * largura + "\n" + miolo.center(largura, "=") + "\n" + "=" * largura
    )
