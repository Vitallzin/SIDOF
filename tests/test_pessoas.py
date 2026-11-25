"""Pessoa ou loja: CPF/CNPJ, loja já vista no cartão, forma do nome e primeiro nome."""

import pandas as pd
import pytest

from financas.aprendizado import ArmazenamentoMemoria, contagem_do_documento, pode_aprender, registrar_confirmacao
from financas.extratos import ler_csv
from financas.normalizacao import normalizar
from financas.pessoas import eh_pessoa, extrair_documento, parece_pessoa, sem_detalhes
from financas.regras import classificar_por_regras
from financas.sistema import Sistema, treinar_modelo_da_base

USUARIOS = pd.DataFrame({"id_usuario": ["U1"], "nome": ["CARLOS SILVA"]})


def _classificado(linhas):
    """linhas: (descricao, valor, meio)."""
    extrato = pd.DataFrame({
        "id_transacao": [f"T{i}" for i in range(len(linhas))], "id_usuario": "U1", "data": "2026-03-10",
        "descricao": [linha[0] for linha in linhas], "valor": [linha[1] for linha in linhas],
        "meio": [linha[2] for linha in linhas], "conta": "corrente", "parcela": "",
    })
    return classificar_por_regras(normalizar(extrato), USUARIOS).set_index("id_transacao")


@pytest.mark.parametrize("texto, limpo, tipo", [
    ("PIX ENVIADO PICHAU - CNPJ 09.376.495/0001-22", "PIX ENVIADO PICHAU", "cnpj"),
    ("PIX ENVIADO MARIA SOUZA - CPF ***.456.789-**", "PIX ENVIADO MARIA SOUZA", "cpf"),
    ("PIX ENVIADO 09376495000122 PICHAU", "PIX ENVIADO 09376495000122 PICHAU", ""),  # sem o formato, não arrisca
    ("PIX ENVIADO JOAO LIMA CPF 12345678900", "PIX ENVIADO JOAO LIMA", "cpf"),
    ("COMPRA DEBITO PADARIA", "COMPRA DEBITO PADARIA", ""),
])
def test_extrair_documento_apaga_o_numero(texto, limpo, tipo):
    assert extrair_documento(texto) == (limpo, tipo)


def test_documento_nunca_fica_na_descricao_normalizada():
    classificado = _classificado([("PIX ENVIADO PICHAU - CNPJ 09.376.495/0001-22", -500.0, "pix")])
    linha = classificado.loc["T0"]
    assert linha["tipo_documento"] == "cnpj"
    assert "0001" not in linha["descricao"] and linha["contraparte"] == "PICHAU"


def test_cnpj_faz_loja_com_cara_de_nome_virar_loja_e_cpf_faz_pessoa():
    classificado = _classificado([
        ("PIX ENVIADO MARIA BONITA - CNPJ 11.222.333/0001-44", -80.0, "pix"),  # loja com nome de gente
        ("PIX ENVIADO PADARIA DO ZE - CPF ***.111.222-**", -20.0, "pix"),  # pessoa, mesmo com nome de loja
    ])
    assert not classificado.loc["T0", "eh_pessoa"]
    assert classificado.loc["T1", "eh_pessoa"]


def test_loja_que_ja_apareceu_no_cartao_nao_e_pessoa_no_pix():
    classificado = _classificado([
        ("ACAI DA PRAIA", -18.0, "cartao_credito"),
        ("PIX ENVIADO ACAI DA PRAIA", -22.0, "pix"),
    ])
    assert not classificado.loc["T1", "eh_pessoa"]


@pytest.mark.parametrize("nome, pessoa", [
    ("MARIA DA SILVA", True),
    ("JOAO LIMA", True),
    ("BAZAR DA ESQUINA", False),  # "BAZAR" não é nome de gente
    ("CANTINA NONNA ITALIA", False),
    ("AMAZON", False),  # uma palavra só: loja
    ("JOSE RICARDO (SALARIO GARCOM)", True),  # o que está entre parênteses é anotação
])
def test_forma_do_nome_e_primeiro_nome(nome, pessoa):
    assert eh_pessoa(nome) == pessoa


def test_parenteses_nao_atrapalham_a_forma_do_nome():
    assert sem_detalhes("JOSE RICARDO (SALARIO GARCOM)") == "JOSE RICARDO"
    assert parece_pessoa("JOSE RICARDO (SALARIO GARCOM)")


def test_pix_para_loja_nao_fica_travado_como_pessoa():
    extrato = pd.DataFrame({
        "id_transacao": ["T1", "T2"], "id_usuario": "U1", "data": ["2026-03-10", "2026-03-11"],
        "descricao": ["PIX ENVIADO BAZAR DA ESQUINA - CNPJ 11.222.333/0001-44", "PIX ENVIADO ANA SOUZA"],
        "valor": -50.0, "meio": "pix", "conta": "corrente", "parcela": "",
    })
    saidas = Sistema(extrato, USUARIOS, treinar_modelo_da_base()).saidas().set_index("id_transacao")
    assert "PIX para uma pessoa" not in saidas.loc["T1", "explicacao_final"]
    assert saidas.loc["T2", "perguntar_usuario"]  # pessoa: sempre pergunta


def test_privacidade_cpf_nunca_vai_para_o_aprendizado_e_cnpj_vai():
    banco = ArmazenamentoMemoria()
    # Forma de nome de pessoa, mas com CNPJ: é loja e pode ser aprendida
    assert pode_aprender("MARIA BONITA", "compras", "PIX ENVIADO MARIA BONITA", tipo_documento="cnpj")
    # Com CPF, nunca, mesmo que o nome pareça de loja
    assert not pode_aprender("PADARIA DO ZE", "alimentacao_basica", "PIX ENVIADO PADARIA DO ZE", tipo_documento="cpf")
    # Sem documento, nome com forma de pessoa fica de fora (cuidado em primeiro lugar)
    assert not registrar_confirmacao(banco, "JOSE RICARDO (SALARIO GARCOM)", "compras", "s1", "fatura", "PIX ENVIADO JOSE RICARDO (SALARIO GARCOM)")
    assert banco.ler_lojas() == {}


def test_grafico_conta_pix_para_loja_como_loja():
    classificado = _classificado([
        ("PIX ENVIADO BAZAR DA ESQUINA - CNPJ 11.222.333/0001-44", -50.0, "pix"),
        ("PIX ENVIADO ANA SOUZA", -30.0, "pix"),
    ])
    saidas = classificado.reset_index().assign(perguntar_usuario=True, origem="pergunta")
    contagem = contagem_do_documento(saidas)
    assert contagem["compras"] == 2 and contagem["compras_lojas"] == 1


def test_csv_com_coluna_de_documento():
    texto = "Data;Descricao;Valor;CPF/CNPJ\n05/06/2026;PIX ENVIADO PICHAU;-500,00;09376495000122\n06/06/2026;PIX ENVIADO ANA;-10,00;\n"
    movimentos = ler_csv(texto.encode(), "extrato.csv").movimentos
    assert "CNPJ" in movimentos.iloc[0]["descricao"]
    tabela = normalizar(movimentos.assign(id_transacao=["A", "B"], id_usuario="U1", meio="pix", conta="corrente"))
    assert list(tabela["tipo_documento"]) == ["cnpj", ""]
