"""Testes das faturas em PDF: gerar, ler, classificar e avaliar."""

import pandas as pd
import pytest

from financas.avaliacao import avaliar_faturas
from financas.faturas_pdf import (
    compras_no_cartao,
    fatura_para_extrato,
    gerar_fatura_pdf,
    ler_fatura_pdf,
    ler_faturas_do_conjunto,
    ler_linhas,
)
from financas.gerador import gerar_dados
from financas.sistema import classificar_fatura, treinar_modelo_da_base


@pytest.fixture(scope="module")
def dados():
    return gerar_dados()


def test_ida_e_volta_de_uma_fatura(dados):
    compras = compras_no_cartao(dados["extrato"], "U08", "2026-03").sort_values("data", kind="stable")
    lidas, ignoradas = ler_fatura_pdf(gerar_fatura_pdf(compras, "JULIANA", "2026-03"))
    assert ignoradas == 1  # o "PAGAMENTO RECEBIDO"
    assert list(lidas["data"]) == list(compras["data"])
    assert list(lidas["valor"]) == pytest.approx(list(-compras["valor"]))
    assert list(lidas["parcela"]) == list(compras["parcela"].fillna(""))


def test_leitor_entende_varios_jeitos_de_escrever():
    texto = """
    BANCO QUALQUER - FATURA
    Vencimento: 10/04/2026
    05/03 SUPERMERCADO BOM PRECO 1.234,56
    06/03/2026 LOJA X PARC 02 DE 05 R$ 89,90
    07/03 MAGAZINE ELETRO 03/12 100,00
    08/03 DROGARIA SAUDE TOTAL 45,00
    09/03 ESTORNO LOJA Y -30,00
    10/03 PAGAMENTO RECEBIDO 500,00
    TOTAL DA FATURA 1.469,46
    """
    compras, ignoradas = ler_linhas(texto)
    assert list(compras["descricao"]) == ["SUPERMERCADO BOM PRECO", "LOJA X", "MAGAZINE ELETRO", "DROGARIA SAUDE TOTAL"]
    assert list(compras["parcela"]) == ["", "2/5", "3/12", ""]
    assert list(compras["valor"]) == [1234.56, 89.90, 100.00, 45.00]
    assert (compras["data"].str[:4] == "2026").all()
    assert ignoradas == 2  # estorno (negativo) e pagamento


def test_ano_vem_do_vencimento_na_virada_do_ano():
    compras, _ = ler_linhas("VENCIMENTO 10/01/2027\n28/12 LOJA DE NATAL 50,00\n03/01 PADARIA 10,00")
    assert list(compras["data"]) == ["2026-12-28", "2027-01-03"]


def test_texto_sem_compras():
    compras, _ = ler_linhas("Isto nao e uma fatura")
    assert compras.empty


def test_fatura_vira_extrato_e_e_classificada():
    compras = pd.DataFrame({
        "data": ["2026-03-05", "2026-03-06"],
        "descricao": ["SUPERMERCADO BOM PRECO", "XYZ SERVICOS 123"],
        "parcela": ["", "1/3"],
        "valor": [100.0, 50.0],
    })
    extrato = fatura_para_extrato(compras)
    assert (extrato["valor"] < 0).all() and (extrato["meio"] == "cartao_credito").all()
    classificadas = classificar_fatura(compras, treinar_modelo_da_base())
    assert classificadas.loc[0, "categoria_final"] == "alimentacao_basica"
    assert (classificadas["explicacao_final"].str.len() > 0).all()


def test_modelo_da_base_fica_guardado():
    assert treinar_modelo_da_base() is treinar_modelo_da_base()


def test_avaliacao_interna_das_faturas(dados):
    lidas = ler_faturas_do_conjunto(dados["extrato"], dados["usuarios"])
    assert lidas["id_origem"].notna().all()  # nenhuma fatura perdeu ou inventou compras
    resultado = avaliar_faturas(lidas, dados["extrato"], dados["verdade"], {"com faturas": treinar_modelo_da_base()})
    assert resultado["leitura_perfeita"] == 1.0
    assert resultado["classificacao"].loc["com faturas", "precisao"] > 0.95
