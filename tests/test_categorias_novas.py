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


# ---------- 25/11/2026: Jogos entrou em Lazer; parcela "5/18" sem a palavra "parcela" ----------

def test_jogos_agora_e_lazer():
    from financas.categorias import CATEGORIAS
    assert "jogos" not in CATEGORIAS
    assert _classificar(["PIXEL GAMES STORE"])["PIXEL GAMES STORE"] == "lazer"


def test_voto_antigo_em_jogos_conta_como_lazer():
    from financas.aprendizado import ArmazenamentoMemoria, conhecimento_coletivo
    banco = ArmazenamentoMemoria()
    # Votos gravados antes da mudança (a categoria "jogos" não pode mais ser escolhida, então gravamos direto)
    for sessao in ("a", "b"):
        banco.salvar_voto("PIXELGAMESSTORE", "PIXEL GAMES STORE", sessao, "jogos", "fatura")
    assert conhecimento_coletivo(banco)["PIXELGAMESSTORE"][0] == "lazer"


@pytest.mark.parametrize("descricao, sem_parcela, parcela", [
    ("LOJA X 05/18", "LOJA X", "5/18"),
    ("MAGAZINE ELETRO 3/12", "MAGAZINE ELETRO", "3/12"),
    ("IPVA 2026 - PARCELA 2/3", "IPVA 2026", "2/3"),
    ("CURSO PARC 4 DE 10", "CURSO", "4/10"),
    ("LOJA X 7/5", "LOJA X 7/5", ""),  # 7 de 5 não existe: não é parcela
])
def test_parcela_escrita_no_fim_da_descricao(descricao, sem_parcela, parcela):
    from financas.extratos import _separar_parcela
    assert _separar_parcela(descricao) == (sem_parcela, parcela)


def test_coluna_parcela_no_csv():
    from financas.extratos import ler_csv
    texto = "Data;Descricao;Valor;Parcela\n05/06/2026;LOJA X;-100,00;05/18\n06/06/2026;PADARIA;-10,00;\n"
    movimentos = ler_csv(texto.encode(), "extrato.csv").movimentos
    assert list(movimentos["parcela"]) == ["5/18", ""]


def test_parcela_desconhecida_conta_nas_parcelas_e_pergunta_do_que_e():
    extrato = pd.DataFrame({
        "id_transacao": ["T1"], "id_usuario": "U1", "data": "2026-03-10", "descricao": ["XYZW QWRT"],
        "valor": -150.0, "meio": "cartao_credito", "conta": "cartao", "parcela": ["5/18"],
    })
    sistema = Sistema(extrato, USUARIOS, treinar_modelo_da_base())
    pergunta = sistema.perguntas().iloc[0]
    assert pergunta["parcela"] == "5/18"
    assert "Parcela 5/18" in pergunta["explicacao_final"]
    indicadores, _ = sistema.diagnosticar()
    assert indicadores.iloc[0]["parcelas"] == pytest.approx(150.0)  # já entra no bloco das parcelas
