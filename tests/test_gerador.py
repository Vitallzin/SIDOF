"""Testes do gerador de dados sintéticos (Fase 1)."""

import numpy as np
import pandas as pd
import pytest

from financas import catalogo
from financas.categorias import CATEGORIAS, CATEGORIAS_DE_RENDA
from financas.gerador import (
    COLUNAS_EXTRATO,
    PERFIS,
    TIPOS_ANOMALIA,
    TIPOS_NAO_PREVISTOS,
    _abreviar,
    gerar_dados,
    salvar_dados,
)


@pytest.fixture(scope="module")
def dados():
    return gerar_dados()


@pytest.fixture(scope="module")
def tabela(dados):
    """Extrato + verdade + perfil juntos, para facilitar as conferências."""
    junto = dados["extrato"].merge(dados["verdade"], on="id_transacao")
    junto = junto.merge(dados["usuarios_verdade"], on="id_usuario")
    junto["mes"] = pd.to_datetime(junto["data"]).dt.month
    return junto


def test_mesma_semente_gera_dados_identicos(dados):
    de_novo = gerar_dados()
    for nome in dados:
        pd.testing.assert_frame_equal(dados[nome], de_novo[nome])


def test_semente_diferente_gera_dados_diferentes(dados):
    outro = gerar_dados(semente=7)
    assert not dados["extrato"].equals(outro["extrato"])


def test_doze_usuarios_tres_por_perfil(dados):
    perfis = dados["usuarios_verdade"]["perfil"].value_counts()
    assert len(dados["usuarios"]) == 12
    assert set(perfis.index) == set(PERFIS)
    assert (perfis == 3).all()


def test_datas_entre_janeiro_e_junho_de_2026(dados):
    datas = pd.to_datetime(dados["extrato"]["data"])
    assert datas.min() >= pd.Timestamp("2026-01-01")
    assert datas.max() <= pd.Timestamp("2026-06-30")


def test_extrato_e_verdade_tem_as_mesmas_transacoes(dados):
    ids_extrato = dados["extrato"]["id_transacao"]
    assert ids_extrato.is_unique
    assert list(ids_extrato) == list(dados["verdade"]["id_transacao"])


def test_extrato_nao_contem_a_resposta(dados):
    # O sistema não pode ver categoria, anomalia nem perfil
    assert list(dados["extrato"].columns) == COLUNAS_EXTRATO
    assert list(dados["usuarios"].columns) == ["id_usuario", "nome"]


def test_categorias_validas_e_grupo_correto(dados):
    verdade = dados["verdade"]
    assert verdade["categoria"].isin(CATEGORIAS).all()
    assert (verdade["grupo"] == verdade["categoria"].map(CATEGORIAS)).all()


def test_renda_entra_e_gasto_sai(tabela):
    renda = tabela[tabela["categoria"].isin(CATEGORIAS_DE_RENDA)]
    gastos = tabela[~tabela["categoria"].isin(CATEGORIAS_DE_RENDA + ["transferencia_interna", "guardar_investir"])]
    assert (renda["valor"] > 0).all()
    assert (gastos["valor"] < 0).all()


def test_valores_com_no_maximo_duas_casas(dados):
    valores = dados["extrato"]["valor"]
    assert (valores.round(2) == valores).all()


def test_transferencias_internas_se_anulam(tabela):
    internas = tabela[tabela["categoria"] == "transferencia_interna"]
    soma_por_usuario = internas.groupby("id_usuario")["valor"].sum()
    assert soma_por_usuario.abs().max() < 0.01
    assert len(internas) % 2 == 0


def test_parcelas_no_formato_k_de_n(dados):
    parcelas = dados["extrato"]["parcela"].replace("", pd.NA).dropna()
    assert len(parcelas) > 0
    assert parcelas.str.fullmatch(r"\d+/\d+").all()
    numero = parcelas.str.split("/").str[0].astype(int)
    total = parcelas.str.split("/").str[1].astype(int)
    assert ((numero >= 1) & (numero <= total)).all()


def test_parcelas_avancam_uma_por_mes(tabela):
    parceladas = tabela[tabela["parcela"] != ""]
    for _, grupo in parceladas.groupby(["id_usuario", "descricao"]):
        grupo = grupo.sort_values("data")
        numeros = grupo["parcela"].str.split("/").str[0].astype(int)
        assert list(numeros.diff().dropna().unique()) in ([], [1])
        assert list(grupo["mes"].diff().dropna().unique()) in ([], [1])


def test_perfil_com_dividas_tem_mais_parcelas(tabela):
    parcelas_por_perfil = tabela[tabela["parcela"] != ""].groupby("perfil").size()
    assert parcelas_por_perfil.idxmax() == "renda_fixa_com_dividas"


def test_cada_usuario_tem_de_2_a_4_tipos_de_anomalia(tabela):
    anomalas = tabela[tabela["tipo_anomalia"].isin(TIPOS_ANOMALIA)]
    tipos_por_usuario = anomalas.groupby("id_usuario")["tipo_anomalia"].nunique()
    assert len(tipos_por_usuario) == 12
    assert tipos_por_usuario.between(2, 4).all()
    assert set(anomalas["tipo_anomalia"]) <= set(TIPOS_ANOMALIA)


def test_anomalias_so_depois_do_historico(tabela):
    anomalas = tabela[tabela["tipo_anomalia"] != ""]
    assert anomalas["mes"].isin([4, 5, 6]).all()


def test_estabelecimento_novo_nunca_aparece_antes(tabela):
    novas = tabela[tabela["tipo_anomalia"] == "estabelecimento_novo_alto"]
    for _, linha in novas.iterrows():
        mesmo_usuario = tabela[(tabela["id_usuario"] == linha["id_usuario"]) & (tabela["descricao"] == linha["descricao"])]
        assert len(mesmo_usuario) == 1


def test_cobranca_duplicada_tem_original_igual(tabela):
    duplicadas = tabela[tabela["tipo_anomalia"] == "cobranca_duplicada"]
    for _, linha in duplicadas.iterrows():
        iguais = tabela[
            (tabela["id_usuario"] == linha["id_usuario"])
            & (tabela["descricao"] == linha["descricao"])
            & (tabela["valor"] == linha["valor"])
        ]
        assert len(iguais) >= 2


def _variacao_da_renda_mensal(tabela, categoria):
    """Coeficiente de variação (desvio padrão / média) da renda mensal de cada usuário."""
    renda = tabela[tabela["categoria"] == categoria].groupby(["id_usuario", "mes"])["valor"].sum()
    por_usuario = renda.groupby("id_usuario")
    return por_usuario.std() / por_usuario.mean()


def test_renda_fixa_estavel_e_autonomo_variavel(tabela):
    sem_troca = tabela[~tabela["troca_emprego"]]
    autonomos = tabela[tabela["perfil"] == "renda_variavel_autonomo"]
    assert (_variacao_da_renda_mensal(sem_troca, "renda_fixa") < 0.05).all()
    assert (_variacao_da_renda_mensal(autonomos, "renda_variavel") > 0.2).all()


def test_troca_de_emprego_tem_um_mes_sem_salario_e_dois_empregadores(tabela):
    trocas = tabela[tabela["troca_emprego"]]
    assert trocas["id_usuario"].nunique() == 3  # o 3º usuário de cada perfil com salário
    for _, usuario in trocas.groupby("id_usuario"):
        salarios = usuario[usuario["categoria"] == "renda_fixa"]
        assert salarios["mes"].nunique() == 5  # um dos 6 meses fica sem salário
        mes_sem_salario = (set(range(1, 7)) - set(salarios["mes"])).pop()
        bicos = usuario[(usuario["categoria"] == "renda_variavel") & (usuario["mes"] == mes_sem_salario)]
        assert len(bicos) >= 1
        antes = salarios[salarios["mes"] < mes_sem_salario]["descricao"].unique()
        depois = salarios[salarios["mes"] > mes_sem_salario]["descricao"].unique()
        assert len(antes) == 1 and len(depois) == 1 and antes[0] != depois[0]


def test_nem_todo_salario_tem_a_palavra_salario(tabela):
    salarios = tabela[tabela["categoria"] == "renda_fixa"]
    tem_palavra = salarios["descricao"].str.contains("SALARIO")
    assert tem_palavra.any() and not tem_palavra.all()


def test_ajuda_da_familia_tem_o_sobrenome_do_usuario(dados, tabela):
    sobrenomes = dados["usuarios"].set_index("id_usuario")["nome"].str.split().str[-1]
    ajudas = tabela[tabela["categoria"] == "renda_eventual"]
    assert len(ajudas) > 0
    for _, linha in ajudas.iterrows():
        assert linha["descricao"].endswith(sobrenomes[linha["id_usuario"]])


def test_todo_perfil_tem_pix_de_pessoa_que_conta_como_renda(tabela):
    # Vendas, bicos, clientes: PIX de uma pessoa sem dizer de quê. Desde 25/11/2026 conta como renda (sem pergunta).
    de_pessoa = (tabela["categoria"] == "renda_variavel") & (tabela["ambigua"] == "sim")
    assert set(tabela.loc[de_pessoa, "perfil"].unique()) == set(PERFIS)


def test_existem_pix_ambiguos_mas_nao_sao_maioria(tabela):
    pix = tabela[tabela["meio"] == "pix"]
    proporcao = (pix["ambigua"] == "sim").mean()
    assert 0.05 <= proporcao <= 0.35


def test_fatura_igual_ao_cartao_do_mes_anterior(tabela):
    for _, usuario in tabela.groupby("id_usuario"):
        cartao = usuario[usuario["meio"] == "cartao_credito"].groupby("mes")["valor"].sum()
        faturas = usuario[usuario["categoria"] == "pagamento_fatura"].groupby("mes")["valor"].sum()
        for mes in range(2, 7):
            assert faturas[mes] == pytest.approx(cartao[mes - 1], abs=0.05)


def test_abreviar_encurta_so_palavras_longas():
    rng = np.random.default_rng(0)
    for _ in range(50):
        abreviado = _abreviar(rng, "SUPERMERCADO BOM PRECO")
        assert abreviado.split()[1] == "BOM"  # palavras curtas ficam iguais
        assert len(abreviado) <= len("SUPERMERCADO BOM PRECO")


def test_descricoes_das_compras_tem_variacoes(tabela):
    # A mesma loja deve aparecer escrita de jeitos diferentes, como no mundo real
    nomes_do_catalogo = {loja for lojas in catalogo.ESTABELECIMENTOS.values() for loja, _, _ in lojas}
    compras = tabela[tabela["meio"].isin(["cartao_credito", "cartao_debito"]) & (tabela["parcela"] == "")]
    loja = compras["descricao"].str.replace("COMPRA DEBITO ", "", regex=False)
    fora_do_catalogo = ~loja.isin(nomes_do_catalogo | {nome for nome, _ in catalogo.ASSINATURAS})
    assert 0.2 < fora_do_catalogo.mean() < 0.9
    supermercado = tabela["descricao"].str.contains("SUPERM|PGTO\\*SUP|MAQ\\*SUP|CRD\\*SUP|LV\\*SUP|PAGFACIL\\*SUP")
    assert tabela.loc[supermercado, "descricao"].nunique() > 3


def test_mesma_conta_mensal_aparece_igual_todo_mes(tabela):
    energia = tabela[tabela["categoria"] == "energia"]
    assert (energia.groupby("id_usuario")["descricao"].nunique() == 1).all()


def test_salvar_dados_cria_os_quatro_csvs(dados, tmp_path):
    salvar_dados(dados, tmp_path)
    for nome in ["extrato", "usuarios", "verdade", "usuarios_verdade"]:
        relido = pd.read_csv(tmp_path / f"{nome}.csv")
        assert len(relido) == len(dados[nome])


def test_loja_de_origem_so_na_verdade(tabela, dados):
    assert "loja" not in dados["extrato"].columns
    compras = tabela[tabela["meio"].isin(["cartao_credito", "cartao_debito", "boleto"]) & (tabela["categoria"] != "pagamento_fatura")]
    assert (compras["loja"] != "").all()
    pix_pessoa = tabela[(tabela["ambigua"] == "sim") & (tabela["meio"] == "pix")]
    assert (pix_pessoa["loja"] == "").all()


def _sobra_por_usuario(tabela):
    """(renda efetiva - gastos) / renda efetiva, com as categorias verdadeiras."""
    renda = tabela[tabela["categoria"].isin(["renda_fixa", "renda_variavel"])].groupby("id_usuario")["valor"].sum()
    gastos = -tabela[
        (tabela["valor"] < 0) & ~tabela["categoria"].isin(["transferencia_interna", "guardar_investir", "pagamento_fatura"])
    ].groupby("id_usuario")["valor"].sum()
    perfis = tabela.groupby("id_usuario")["perfil"].first()
    return pd.DataFrame({"perfil": perfis, "sobra": (renda - gastos) / renda})


def test_sobra_plausivel_para_cada_perfil(tabela):
    # Comportamento normal: sem as anomalias não previstas (ex.: um PIX de 30% a 60% da renda)
    sobra = _sobra_por_usuario(tabela[~tabela["tipo_anomalia"].isin(TIPOS_NAO_PREVISTOS)])
    # Ninguém gasta muito mais do que ganha por 6 meses. Quem trocou de emprego ficou 1 de 6 meses
    # sem salário (~17% a menos de renda no período), então o limite dele é mais largo.
    troca = tabela.groupby("id_usuario")["troca_emprego"].first()
    assert (sobra.loc[~troca, "sobra"] > -0.15).all()
    assert (sobra.loc[troca, "sobra"] > -0.30).all()
    media = sobra.groupby("perfil")["sobra"].mean()
    assert media["renda_fixa_poucos_compromissos"] > 0.10
    assert media["renda_fixa_poucos_compromissos"] == media.max()
    assert media["renda_fixa_com_dividas"] < media["renda_variavel_autonomo"]


def test_anomalias_nao_previstas(tabela):
    nao_previstas = tabela[tabela["tipo_anomalia"].isin(TIPOS_NAO_PREVISTOS)]
    por_usuario = nao_previstas.groupby("id_usuario")["tipo_anomalia"].nunique()
    assert len(por_usuario) == 12 and por_usuario.between(1, 2).all()
    assert nao_previstas["mes"].isin([4, 5, 6]).all()
    assert set(tabela.loc[tabela["tipo_anomalia"] != "", "tipo_anomalia"]) <= set(TIPOS_ANOMALIA + TIPOS_NAO_PREVISTOS)
