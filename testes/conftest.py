# -*- coding: utf-8 -*-
"""conftest.py — fixtures compartilhadas + relatório legível da suíte.

Relatório legível (regra do projeto): sob o nome de cada teste, uma frase
curta do que foi testado (1ª linha da docstring; fallback = nome do teste)
e o resultado, com linha em branco entre testes.

Nota de implementação (pequeno desvio da SPEC, registrado): as fixtures vivem
aqui no conftest — onde o pytest as descobre automaticamente — e a CRIAÇÃO do
banco sintético vive em banco_sintetico.py, como a SPEC define.
"""
from pathlib import Path

import pytest

from app.config import CAMINHO_BANCO_PADRAO
from testes.banco_sintetico import criar_banco_sintetico

_RELATORIO = {"config": None, "terminal": None}


def pytest_configure(config):
    """Guarda o config; o terminalreporter é buscado preguiçosamente
    (no pytest 9 ele ainda não está registrado neste momento)."""
    _RELATORIO["config"] = config


def _terminal():
    """Busca (e cacheia) o terminal reporter quando ele já existir."""
    if _RELATORIO["terminal"] is None and _RELATORIO["config"] is not None:
        _RELATORIO["terminal"] = _RELATORIO["config"].pluginmanager.get_plugin(
            "terminalreporter"
        )
    return _RELATORIO["terminal"]


def pytest_report_teststatus(report, config):
    """Suprime as letrinhas de progresso (.F s) — o bloco legível as substitui."""
    if report.when == "call":
        if report.passed:
            return "passed", "", "PASSOU"
        if report.failed:
            return "failed", "", "FALHOU"
    if report.skipped:
        return "skipped", "", "PULADO"


def _frase_do_teste(item) -> str:
    """1ª linha da docstring; sem docstring, deriva do nome do teste."""
    doc = getattr(item.function, "__doc__", None)
    if doc and doc.strip():
        return doc.strip().splitlines()[0]
    return item.name.replace("test_", "").replace("_", " ")


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """Anexa a frase legível ao relatório de cada fase do teste."""
    relatorio = yield
    relatorio.frase_legivel = _frase_do_teste(item)
    relatorio.nome_legivel = item.name
    return relatorio


def pytest_runtest_logreport(report):
    """Escreve o bloco legível: nome do teste, o que testa e o resultado."""
    eh_chamada = report.when == "call"
    eh_pulo_no_setup = report.when == "setup" and report.skipped
    if not (eh_chamada or eh_pulo_no_setup):
        return
    terminal = _terminal()
    if terminal is None:
        return
    if report.passed:
        resultado = "PASSOU"
    elif report.failed:
        resultado = "FALHOU"
    else:
        resultado = "PULADO"
    terminal.write_line(getattr(report, "nome_legivel", report.nodeid))
    terminal.write_line(f"   testa: {getattr(report, 'frase_legivel', '')}")
    terminal.write_line(f"   resultado: {resultado}")
    terminal.write_line("")


@pytest.fixture
def banco_sintetico(tmp_path: Path) -> Path:
    """Banco sintético com armadilhas plantadas, em diretório temporário."""
    return criar_banco_sintetico(tmp_path / "sintetico.db")


@pytest.fixture
def banco_real() -> Path:
    """Caminho do anexo_desafio_1.db real (pula o teste se ausente)."""
    if not CAMINHO_BANCO_PADRAO.exists():
        pytest.skip("anexo_desafio_1.db ausente em data/ — teste pulado.")
    return CAMINHO_BANCO_PADRAO
