# -*- coding: utf-8 -*-
"""
executor.py — Executor Somente-Leitura.

A garantia FÍSICA de que nenhuma consulta escreve no banco: toda conexão é
aberta via URI `file:{caminho}?mode=ro`. O Guardrail SQL (guardrail_sql.py) é
a primeira linha de defesa (mensagens claras + trace); este módulo é a última
— mesmo que um comando de escrita chegue até aqui, o SQLite o recusa.

Decisões da SPEC:
- Erro de EXECUÇÃO não levanta exceção: volta no campo `erro` do resultado.
  É o combustível do loop de correção sintática do Engenheiro de Dados (M2).
- SEM truncamento (decisão V3.6): TODAS as linhas do resultado são
  devolvidas — o gráfico recebe o conjunto completo. Os prompts continuam
  enxutos porque cada agente exibe apenas um RECORTE das linhas.
"""
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path



class ErroDeBanco(Exception):
    """Erro de acesso ao banco (ex.: arquivo inexistente)."""


@dataclass
class ResultadoConsulta:
    """Resultado de uma consulta executada (ou da tentativa de executá-la)."""
    colunas: list           # nomes das colunas retornadas
    linhas: list            # dados (já truncados se necessário)
    n_linhas: int           # linhas APÓS truncamento
    truncado: bool          # True se havia mais que max_linhas
    tempo_ms: float         # duração da execução
    erro: str | None        # mensagem do SQLite se falhou (None = sucesso)


def _abrir_somente_leitura(caminho_banco: Path) -> sqlite3.Connection:
    """Abre o banco em modo SOMENTE-LEITURA via URI.

    Levanta ErroDeBanco com mensagem clara se o arquivo não existir.
    O `mode=ro` jamais cria arquivo novo nem permite escrita — é a garantia
    física do projeto.
    """
    caminho_banco = Path(caminho_banco)
    if not caminho_banco.exists():
        raise ErroDeBanco(
            f"Banco de dados não encontrado: {caminho_banco}. "
            "Confira o caminho (o padrão é data/anexo_desafio_1.db)."
        )
    return sqlite3.connect(f"file:{caminho_banco}?mode=ro", uri=True)


def executar(
    sql: str,
    caminho_banco: Path,
) -> ResultadoConsulta:
    """Executa UMA consulta contra o banco em modo somente-leitura.

    - Sucesso: colunas + TODAS as linhas (`truncado` é sempre False).
    - Falha de execução (SQL inválido, tentativa de escrita barrada pelo
      mode=ro etc.): retorna `erro` preenchido — NÃO levanta exceção.
    """
    conexao = _abrir_somente_leitura(caminho_banco)
    inicio = time.perf_counter()
    try:
        cursor = conexao.execute(sql)
        # Busca uma linha além do teto para SABER se truncou.
        linhas = cursor.fetchall()
        truncado = False             # V3.6: sem corte de dados, por decisão
        colunas = [d[0] for d in cursor.description] if cursor.description else []
        tempo_ms = (time.perf_counter() - inicio) * 1000
        return ResultadoConsulta(
            colunas=colunas,
            linhas=linhas,
            n_linhas=len(linhas),
            truncado=truncado,
            tempo_ms=tempo_ms,
            erro=None,
        )
    except sqlite3.Error as excecao:
        tempo_ms = (time.perf_counter() - inicio) * 1000
        return ResultadoConsulta(
            colunas=[],
            linhas=[],
            n_linhas=0,
            truncado=False,
            tempo_ms=tempo_ms,
            erro=str(excecao),
        )
    finally:
        conexao.close()
