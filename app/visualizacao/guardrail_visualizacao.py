# -*- coding: utf-8 -*-
"""
guardrail_visualizacao.py — Guardrail de Visualização: option = JSON PURO.

Regra do projeto (guardada em memória pelo time): o option ECharts gerado
pelo Designer NUNCA pode conter código executável — JsCode, funções JS,
eval, script. O agente cria a ESPECIFICAÇÃO; Python valida; o componente
renderiza.

HONESTIDADE (registrada): a garantia DURA é arquitetural — este projeto
JAMAIS usa o mecanismo JsCode do streamlit-echarts e JAMAIS avalia strings;
o renderizador só recebe dados (json.dumps no preview; dict no st_echarts).
Este guardrail é defesa em profundidade + mensagens claras que alimentam o
retry do Designer.
"""
import json
from dataclasses import dataclass

from app.config import LIMITE_PROFUNDIDADE_OPTION, LIMITE_TAMANHO_OPTION

# Tipos de série que exigem um recurso EXTERNO que o projeto não embarca
# (registerMap com GeoJSON). São estruturalmente válidos mas NÃO renderizam
# no navegador — barramos aqui para cair no fallback tabela controlado, em
# vez de estourar no componente do front (erro "reading 'regions'").
# Comparação em minúsculas (o detector normaliza com .lower()):
TIPOS_NAO_SUPORTADOS = ("map", "geo", "bar3d", "scatter3d")  # gl ausente

# Padrões (minúsculas) que denunciam tentativa de embutir comportamento.
PADROES_PROIBIDOS = (
    "function(", "function (", "=>", "new function",
    "eval(", "<script", "javascript:", "jscode",
)


@dataclass
class ResultadoValidacaoVisual:
    """Veredito do Guardrail de Visualização."""
    aprovado: bool
    motivo: str | None          # claro e acionável (vai ao retry do Designer)
    option: dict | None         # o option JÁ parseado, quando aprovado


def _varrer_strings_proibidas(no, caminho: str = "raiz") -> str | None:
    """Percorre o JSON inteiro (chaves E valores) e retorna
    '{caminho}: {padrão}' da primeira ocorrência proibida — ou None."""
    if isinstance(no, dict):
        for chave, valor in no.items():
            texto_chave = str(chave).lower()
            for padrao in PADROES_PROIBIDOS:
                if padrao in texto_chave:
                    return f"{caminho}.{chave} (chave): '{padrao}'"
            achado = _varrer_strings_proibidas(valor, f"{caminho}.{chave}")
            if achado:
                return achado
    elif isinstance(no, list):
        for indice, item in enumerate(no):
            achado = _varrer_strings_proibidas(item, f"{caminho}[{indice}]")
            if achado:
                return achado
    elif isinstance(no, str):
        texto = no.lower()
        for padrao in PADROES_PROIBIDOS:
            if padrao in texto:
                return f"{caminho}: '{padrao}'"
    return None


def _profundidade(no, atual: int = 1) -> int:
    """Profundidade máxima de aninhamento do JSON."""
    if isinstance(no, dict):
        return max([atual] + [_profundidade(v, atual + 1) for v in no.values()])
    if isinstance(no, list):
        return max([atual] + [_profundidade(v, atual + 1) for v in no])
    return atual


def _tipo_nao_suportado(option: dict) -> str | None:
    """Retorna o 1º series.type que exige recurso externo (map/geo), ou None.
    Também detecta a chave de topo 'geo' (componente de mapa do ECharts)."""
    if "geo" in option:
        return "geo"
    series = option.get("series")
    candidatas = series if isinstance(series, list) else [series]
    for serie in candidatas:
        if isinstance(serie, dict):
            tipo = str(serie.get("type", "")).lower()
            if tipo in TIPOS_NAO_SUPORTADOS:
                return tipo
    return None


def validar_option(option_json) -> ResultadoValidacaoVisual:
    """Funil de validação do option (cada reprovação com motivo acionável):
    1. string não-vazia e tamanho ≤ LIMITE_TAMANHO_OPTION;
    2. json.loads — JSON válido (parsing de DADOS, jamais eval);
    3. raiz é objeto (dict);
    4. profundidade ≤ LIMITE_PROFUNDIDADE_OPTION;
    5. varredura recursiva dos padrões proibidos (chaves e valores);
    6. estrutura mínima de gráfico: chave 'series' presente e não-vazia.
    Nota: 'formatter' como TEMPLATE ('{b}: {c}') é string de dados — passa."""
    if not isinstance(option_json, str) or not option_json.strip():
        return ResultadoValidacaoVisual(
            aprovado=False, motivo="option_json vazio ou não é string.", option=None
        )
    if len(option_json) > LIMITE_TAMANHO_OPTION:
        return ResultadoValidacaoVisual(
            aprovado=False,
            motivo=(f"option_json com {len(option_json)} caracteres excede o "
                    f"limite de {LIMITE_TAMANHO_OPTION}. Reduza os dados ou a decoração."),
            option=None,
        )
    try:
        option = json.loads(option_json)
    except json.JSONDecodeError as excecao:
        return ResultadoValidacaoVisual(
            aprovado=False,
            motivo=f"option_json não é JSON válido: {excecao}. Envie JSON puro, sem comentários.",
            option=None,
        )
    if not isinstance(option, dict):
        return ResultadoValidacaoVisual(
            aprovado=False,
            motivo="A raiz do option deve ser um objeto JSON (dict), não lista/escalar.",
            option=None,
        )
    profundidade = _profundidade(option)
    if profundidade > LIMITE_PROFUNDIDADE_OPTION:
        return ResultadoValidacaoVisual(
            aprovado=False,
            motivo=(f"Aninhamento de {profundidade} níveis excede o limite de "
                    f"{LIMITE_PROFUNDIDADE_OPTION}."),
            option=None,
        )
    achado = _varrer_strings_proibidas(option)
    if achado:
        return ResultadoValidacaoVisual(
            aprovado=False,
            motivo=(f"Conteúdo executável proibido em {achado}. O option deve "
                    "ser JSON PURO: nada de function/arrow/eval/JsCode/script; "
                    "formatter apenas como template string (ex.: '{b}: {c}')."),
            option=None,
        )
    series = option.get("series")
    if not series:
        return ResultadoValidacaoVisual(
            aprovado=False,
            motivo="O option precisa da chave 'series' não-vazia (é ela que desenha o gráfico).",
            option=None,
        )
    tipo_externo = _tipo_nao_suportado(option)
    if tipo_externo:
        return ResultadoValidacaoVisual(
            aprovado=False,
            motivo=(f"Tipo de gráfico '{tipo_externo}' exige recurso externo "
                    "externo (registerMap/GeoJSON) que este sistema não embarca "
                    "— ele não renderizaria no navegador. Escolha um gráfico "
                    "padrão (barra, linha, pizza) ou apresente os dados em tabela."),
            option=None,
        )
    return ResultadoValidacaoVisual(aprovado=True, motivo=None, option=option)
