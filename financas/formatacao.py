"""Formatação de valores e datas para os textos mostrados ao usuário."""

import pandas as pd

MESES_POR_EXTENSO = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def reais(valor):
    """1234.5 -> 'R$ 1.234,50'"""
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def mes_por_extenso(mes):
    """'2027-02' -> 'fevereiro de 2027'"""
    periodo = pd.Period(mes, freq="M")
    return f"{MESES_POR_EXTENSO[periodo.month - 1]} de {periodo.year}"
