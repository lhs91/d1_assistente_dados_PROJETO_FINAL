# -*- coding: utf-8 -*-
"""
render_streamlit.py — A decisão PURA de renderização (testável sem Streamlit).

A UI só executa o veredito devolvido aqui: st_echarts para options (dict
PURO — o mecanismo JsCode jamais é importado neste projeto), st.metric para
métricas, st.dataframe para tabelas. Manter a decisão fora da interface
preserva a separação UI×motor e deixa a lógica coberta por testes.
"""
from app.estado import EspecificacaoVisual


def decidir_renderizacao(especificacao: EspecificacaoVisual | None) -> dict:
    """Retorna o veredito de renderização:
    {'tipo': 'echarts', 'option': dict, 'aviso': str|None}
    {'tipo': 'metrica', 'valor': str, 'rotulo': str, 'aviso': ...}
    {'tipo': 'tabela', 'colunas': list, 'linhas': list, 'aviso': ...}
    {'tipo': 'nada', 'aviso': None}     (espec ausente — ex.: falha graciosa)
    'aviso' carrega o motivo do fallback quando espec.fallback_usado."""
    if especificacao is None:
        return {"tipo": "nada", "aviso": None}

    aviso = None
    if especificacao.fallback_usado:
        aviso = (
            "Exibindo tabela de segurança (fallback). "
            f"Motivo: {especificacao.motivo_fallback}"
        )

    if especificacao.option is not None:
        return {"tipo": "echarts", "option": especificacao.option, "aviso": aviso}
    if especificacao.tipo == "metrica":
        return {
            "tipo": "metrica",
            "valor": especificacao.valor_metrica,
            "rotulo": especificacao.rotulo_metrica,
            "aviso": aviso,
        }
    return {
        "tipo": "tabela",
        "colunas": especificacao.colunas or [],
        "linhas": especificacao.linhas or [],
        "aviso": aviso,
    }
