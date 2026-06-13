# -*- coding: utf-8 -*-
"""Testes do detector determinístico de outliers (z-score > 2)."""
from app.analise_outliers import detectar_outliers, texto_dos_outliers


def test_detecta_outlier_alto():
    """Um valor muito acima dos demais (|z|>2) é sinalizado, com z positivo."""
    cols = ["estado", "receita"]
    linhas = [["SP", 141665], ["SC", 9670], ["PR", 6807], ["MG", 5200],
              ["BA", 4900], ["RS", 5100]]
    achados = detectar_outliers(cols, linhas)
    assert len(achados) == 1
    assert achados[0]["rotulo"] == "SP"
    assert achados[0]["z"] > 2


def test_sem_outlier_quando_dados_equilibrados():
    """Dados homogêneos não geram falso outlier."""
    cols = ["mes", "vendas"]
    linhas = [["jan", 100], ["fev", 102], ["mar", 98], ["abr", 101],
              ["mai", 99]]
    assert detectar_outliers(cols, linhas) == []


def test_amostra_pequena_nao_dispara():
    """Menos de 3 pontos: sem estatística confiável, sem outlier."""
    assert detectar_outliers(["x", "y"], [["a", 1], ["b", 999]]) == []


def test_coluna_nao_numerica_e_ignorada():
    """Colunas de texto não entram no cálculo (sem exceção)."""
    cols = ["cliente", "cidade"]
    linhas = [["A", "SP"], ["B", "RJ"], ["C", "SP"], ["D", "MG"]]
    assert detectar_outliers(cols, linhas) == []


def test_texto_dos_outliers_formata_para_o_prompt():
    """O bloco textual cita rótulo, coluna, valor e z — base do Diretor."""
    achados = [{"coluna": "receita", "rotulo": "SP", "valor": 141665.0,
                "z": 2.23}]
    texto = texto_dos_outliers(achados)
    assert "FORA DO PADRÃO" in texto
    assert "SP" in texto and "receita" in texto and "2.23" in texto
    assert texto_dos_outliers([]) == ""
