# -*- coding: utf-8 -*-
"""
guardrail_sql.py — Guardrail SQL: só passa UM SELECT (ou CTE) por vez.

Hierarquia de segurança (documentada com honestidade):
- Este Guardrail é a PRIMEIRA linha de defesa: barra cedo, com mensagens
  claras que alimentam o trace e o loop de correção dos agentes.
- A garantia FINAL é o mode=ro do Executor (executor.py): mesmo que algo
  atravesse esta barreira, o SQLite recusa qualquer escrita.
- Defesa em profundidade: a segurança do sistema NUNCA depende de prompt.

Limite conhecido (registrado): a checagem de statement único não interpreta
';' dentro de literais de string. Para o nosso caso (só SELECT de leitura,
com o mode=ro atrás), o efeito é no máximo um falso REPROVADO — falha segura.
"""
import re
from dataclasses import dataclass

# Comandos que jamais têm motivo de existir numa consulta de leitura.
PALAVRAS_PROIBIDAS = frozenset(
    {
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE",
        "PRAGMA", "ATTACH", "DETACH", "VACUUM", "REINDEX", "TRIGGER",
    }
)


@dataclass
class ResultadoValidacao:
    """Veredito do Guardrail sobre um SQL proposto."""
    aprovado: bool
    motivo: str | None      # explicação clara quando reprovado


def _remover_comentarios(sql: str) -> str:
    """Remove `-- ...` e `/* ... */` e normaliza espaços.

    Comentários são removidos ANTES de qualquer análise: eles não podem
    esconder comandos (ex.: 'SELECT 1 /* */; DROP TABLE x').
    """
    sem_bloco = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sem_linha = re.sub(r"--[^\n]*", " ", sem_bloco)
    return re.sub(r"\s+", " ", sem_linha).strip()


def _e_statement_unico(sql_limpo: str) -> bool:
    """True se não há ';' separando múltiplos statements.

    Um ';' ao FINAL é tolerado (hábito comum e inofensivo).
    """
    corpo = sql_limpo.rstrip()
    if corpo.endswith(";"):
        corpo = corpo[:-1]
    return ";" not in corpo


def _palavra_proibida_presente(sql_limpo: str) -> str | None:
    """Retorna a primeira palavra da blocklist encontrada, ou None.

    Comparação por TOKEN (identificadores completos), não por substring:
    uma coluna 'created_at' não pode disparar 'CREATE' (falso positivo
    também é risco).
    """
    tokens = {t.upper() for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", sql_limpo)}
    encontradas = tokens & PALAVRAS_PROIBIDAS
    if encontradas:
        return sorted(encontradas)[0]
    return None


def validar(sql) -> ResultadoValidacao:
    """Valida um SQL proposto pelos agentes. Pipeline, nesta ordem:

    1. Reprova vazio/não-string.
    2. Remove comentários (não escondem comandos).
    3. Exige statement único (nenhum ';' interno).
    4. Exige que comece com SELECT ou WITH (CTEs são legítimas).
    5. Blocklist de comandos perigosos, case-insensitive, por token.
    """
    if not isinstance(sql, str) or not sql.strip():
        return ResultadoValidacao(
            aprovado=False,
            motivo="Consulta vazia ou inválida: era esperado um SELECT.",
        )

    sql_limpo = _remover_comentarios(sql)
    if not sql_limpo:
        return ResultadoValidacao(
            aprovado=False,
            motivo="Consulta vazia após remover comentários.",
        )

    if not _e_statement_unico(sql_limpo):
        return ResultadoValidacao(
            aprovado=False,
            motivo=(
                "Múltiplos statements detectados (';' interno). "
                "Apenas UMA consulta SELECT é permitida por vez."
            ),
        )

    primeira_palavra = sql_limpo.split(None, 1)[0].upper().rstrip(";")
    if primeira_palavra not in {"SELECT", "WITH"}:
        return ResultadoValidacao(
            aprovado=False,
            motivo=(
                f"A consulta começa com '{primeira_palavra}'. "
                "Apenas SELECT (ou WITH ... SELECT) é permitido."
            ),
        )

    proibida = _palavra_proibida_presente(sql_limpo)
    if proibida:
        return ResultadoValidacao(
            aprovado=False,
            motivo=(
                f"Comando proibido detectado: '{proibida}'. "
                "Este sistema é somente-leitura: apenas SELECT é permitido."
            ),
        )

    return ResultadoValidacao(aprovado=True, motivo=None)
