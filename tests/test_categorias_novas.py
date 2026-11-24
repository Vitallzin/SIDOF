"""Testes das categorias criadas em 24/11/2026: Veículos, Transferência familiar, Guardar/investir,
Saque em dinheiro, Impostos e contribuições, Tarifas e juros bancários."""

import pandas as pd
import pytest

from financas.aprendizado import pode_aprender
from financas.categorias import CATEGORIAS, CATEGORIAS_FORA_DOS_GASTOS, nome_exibicao
from financas.diagnostico import _bloco
from financas.gerador import gerar_dados
from financas.normalizacao import normalizar
from financas.regras import classificar_por_regras
from financas.sistema import Sistema, treinar_modelo_da_base

USUARIOS = pd.DataFrame({"id_usuario": ["U1"], "nome": ["CARLOS SILVA"]})


def _classificar(descricoes, valor=-100.0):
    extrato = pd.DataFrame({
        "id_transacao": [f"T{i}" for i in range(len(descricoes))],
        "id_usuario": "U1",
        "data": "2026-03-10",
        "descricao": descricoes,
        "valor": valor,
        "meio": "boleto",
        "conta": "corrente",
        "parcela": "",
    })
    return classificar_por_regras(normalizar(extrato), USUARIOS).set_index("descricao")["categoria_regra"]


@pytest.mark.parametrize("descricao, categoria", [
    ("PAGTO BOLETO IPVA 2026 DETRAN", "veiculos"),
    ("LICENCIAMENTO 2026 DETRAN", "veiculos"),
    ("MULTA TRANSITO DETRAN", "veiculos"),
    ("COMPRA DEBITO POSTO SHELL", "veiculos"),
    ("SEGURO AUTO PROTEGE", "veiculos"),
    ("OFICINA MECANICA DO TIAO", "veiculos"),
    ("APP CORRIDA *VIAGEM", "transporte"),
    ("UBER TRIP", "transporte"),
    ("PAGTO BOLETO IPTU 2026 PREFEITURA", "moradia"),
    ("DARF IRPF 2026", "impostos_contribuicoes"),
    ("DAS MEI SIMPLES NACIONAL", "impostos_contribuicoes"),
    ("INSS CONTRIBUINTE INDIVIDUAL", "impostos_contribuicoes"),
    ("TARIFA PACOTE SERVICOS", "tarifas_bancarias"),
    ("IOF COMPRA INTERNACIONAL", "tarifas_bancarias"),
    ("JUROS CHEQUE ESPECIAL", "tarifas_bancarias"),
    ("SAQUE 24H BANCO", "saque"),
    ("APLICACAO RESERVA CDB", "guardar_investir"),
    ("PIX ENVIADO MESADA FILHO", "transferencia_familiar"),
])
def test_regras_das_categorias_novas(descricao, categoria):
    assert _classificar([descricao])[descricao] == categoria


def test_kit_de_limpeza_do_carro_nao_cai_na_regra_de_veiculos():
    # Acessórios e limpeza ficam para o modelo (são compras), não para a regra de veículos
    assert _classificar(["AUTO SHOP ACESSORIOS"])["AUTO SHOP ACESSORIOS"] != "veiculos"


def test_grupos_das_categorias_novas():
    assert CATEGORIAS["veiculos"] == "essencial"
    for categoria in ("transferencia_familiar", "impostos_contribuicoes", "tarifas_bancarias"):
        assert CATEGORIAS[categoria] == "prioritario"
    assert CATEGORIAS["saque"] == "discricionario"
    assert "guardar_investir" in CATEGORIAS_FORA_DOS_GASTOS
    assert _bloco("guardar_investir", "") is None
    assert nome_exibicao("saque") == "Saque em dinheiro"


def test_pix_para_parente_sugere_transferencia_familiar_mas_pergunta():
    extrato = pd.DataFrame({
        "id_transacao": ["T1", "T2"], "id_usuario": "U1", "data": ["2026-03-10", "2026-03-11"],
        "descricao": ["PIX ENVIADO MARIA SILVA", "PIX ENVIADO JOAO SOUZA"], "valor": -200.0,
        "meio": "pix", "conta": "corrente", "parcela": "",
    })
    saidas = Sistema(extrato, USUARIOS, treinar_modelo_da_base()).saidas().set_index("descricao")
    parente = saidas.loc["PIX ENVIADO MARIA SILVA"]
    assert parente["sugestao_modelo"] == "transferencia_familiar"
    assert parente["perguntar_usuario"]  # é só uma pista: quem sabe é o usuário
    assert "sobrenome" in parente["explicacao_final"]
    assert saidas.loc["PIX ENVIADO JOAO SOUZA", "sugestao_modelo"] != "transferencia_familiar"


def test_transferencia_familiar_nunca_vai_para_o_aprendizado_coletivo():
    assert not pode_aprender("MESADA FILHO", "transferencia_familiar", "PIX ENVIADO MESADA FILHO")
    assert pode_aprender("OFICINA MECANICA DO TIAO", "veiculos", "OFICINA MECANICA DO TIAO")


def test_gerador_tem_as_categorias_novas_e_carro_so_para_quem_tem():
    dados = gerar_dados()
    verdade = dados["verdade"]
    for categoria in ("veiculos", "transferencia_familiar", "guardar_investir", "saque", "impostos_contribuicoes", "tarifas_bancarias"):
        assert (verdade["categoria"] == categoria).sum() > 0, categoria
    tabela = dados["extrato"].merge(verdade, on="id_transacao")
    com_carro = set(tabela.loc[tabela["categoria"] == "veiculos", "id_usuario"])
    assert 0 < len(com_carro) < 12


def test_aplicacao_do_gerador_vira_reserva_no_diagnostico():
    dados = gerar_dados()
    tabela = dados["extrato"].merge(dados["verdade"], on="id_transacao")
    quem_aplica = tabela.loc[tabela["categoria"] == "guardar_investir", "id_usuario"].iloc[0]
    indicadores, _ = Sistema(dados["extrato"], dados["usuarios"], treinar_modelo_da_base()).diagnosticar()
    assert indicadores.set_index("id_usuario").loc[quem_aplica, "poupanca_por_mes"] > 0
