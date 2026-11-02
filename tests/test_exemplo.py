"""Teste de exemplo da Fase 0: confirma que o ambiente funciona."""

import pandas
import sklearn

from financas import SEMENTE


def test_semente_fixa():
    assert SEMENTE == 42


def test_bibliotecas_instaladas():
    assert pandas.__version__
    assert sklearn.__version__
