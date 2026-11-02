"""Testes da normalização do extrato (Fase 2)."""

import pandas as pd

from financas.normalizacao import normalizar, normalizar_texto, separar_operacao


def _extrato(descricoes, valores=None, parcelas=None):
    quantidade = len(descricoes)
    return pd.DataFrame({
        "id_transacao": [f"T{i}" for i in range(quantidade)],
        "id_usuario": ["U01"] * quantidade,
        "data": ["2026-03-05"] * quantidade,
        "descricao": descricoes,
        "valor": valores or [-10.0] * quantidade,
        "meio": ["pix"] * quantidade,
        "conta": ["corrente"] * quantidade,
        "parcela": parcelas or [""] * quantidade,
    })


def test_normalizar_texto_tira_acento_espacos_e_poe_maiusculas():
    assert normalizar_texto("  Pão  de   Açúcar ") == "PAO DE ACUCAR"
    assert normalizar_texto(None) == ""


def test_separar_operacao():
    assert separar_operacao("PIX ENVIADO MARIA SOUZA") == ("pix_enviado", "MARIA SOUZA")
    assert separar_operacao("COMPRA DEBITO PADARIA X") == ("compra_debito", "PADARIA X")
    assert separar_operacao("MKTPLACE*PEDIDO") == ("outra", "MKTPLACE*PEDIDO")


def test_normalizar_cria_colunas_auxiliares():
    tabela = normalizar(_extrato(["pix recebido  joão silva", "Padaria"], valores=[100.0, -5.0]))
    assert list(tabela["descricao"]) == ["PIX RECEBIDO JOAO SILVA", "PADARIA"]
    assert list(tabela["direcao"]) == ["entrada", "saida"]
    assert list(tabela["operacao"]) == ["pix_recebido", "outra"]
    assert tabela.loc[0, "contraparte"] == "JOAO SILVA"
    assert tabela.loc[0, "mes"] == "2026-03"


def test_normalizar_separa_parcela_e_aceita_vazio():
    tabela = normalizar(_extrato(["LOJA A", "LOJA B", "LOJA C"], parcelas=["3/12", "", None]))
    assert tabela.loc[0, "parcela_numero"] == 3
    assert tabela.loc[0, "parcela_total"] == 12
    assert pd.isna(tabela.loc[1, "parcela_numero"])
    assert pd.isna(tabela.loc[2, "parcela_total"])
    assert tabela.loc[2, "parcela"] == ""


def test_normalizar_nao_remove_linhas_repetidas():
    # Repetição pode ser cobrança duplicada: o usuário precisa ver
    tabela = normalizar(_extrato(["LOJA A", "LOJA A"]))
    assert len(tabela) == 2


def test_normalizar_nao_altera_o_original():
    original = _extrato(["padaria"])
    normalizar(original)
    assert original.loc[0, "descricao"] == "padaria"
