# -*- coding: utf-8 -*-
"""
llm_falso.py — Mock roteirizável do LLM para os testes determinísticos.

O roteiro é um dicionário {SchemaPydantic: [saida1, saida2, ...]}. Cada
chamada estruturada consome a PRÓXIMA saída do schema pedido. Se o roteiro
de um schema acabar, estoura AssertionError — é assim que os testes de
orçamento detectam loops além do esperado.
"""
from collections import defaultdict


class _SaidaEstruturada:
    """Proxy devolvido por with_structured_output(schema)."""

    def __init__(self, dono, schema):
        self._dono = dono
        self._schema = schema

    def invoke(self, prompt: str):
        return self._dono._consumir(self._schema, prompt)


class LlmRoteirizado:
    """Mock do LLM com fila de saídas por schema Pydantic."""

    def __init__(self, roteiro: dict):
        # Copia as filas para não mutar o dicionário do teste.
        self._roteiro = {schema: list(saidas) for schema, saidas in roteiro.items()}
        self.prompts: list = []                       # todos os prompts, em ordem
        self.prompts_por_schema: dict = defaultdict(list)
        self.chamadas_por_schema: dict = defaultdict(int)

    def with_structured_output(self, schema):
        return _SaidaEstruturada(self, schema)

    def _consumir(self, schema, prompt: str):
        self.prompts.append(prompt)
        self.prompts_por_schema[schema].append(prompt)
        self.chamadas_por_schema[schema] += 1
        fila = self._roteiro.get(schema, [])
        assert fila, (
            f"Roteiro esgotado para {schema.__name__}: o grafo chamou o LLM "
            "mais vezes do que o teste previu (possível loop além do esperado)."
        )
        return fila.pop(0)

    @property
    def total_de_chamadas(self) -> int:
        return len(self.prompts)
