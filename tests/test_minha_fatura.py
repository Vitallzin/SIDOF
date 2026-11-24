"""Testes do modo "Minha fatura": várias faturas (e a renda opcional) viram o extrato de uma pessoa."""

import pandas as pd
import pytest

from financas.faturas_pdf import (
    DESCRICAO_RENDA_INFORMADA,
    ID_FATURA,
    compras_no_cartao,
    extrato_de_faturas,
    gerar_fatura_pdf,
    ler_fatura_pdf,
    mes_da_fatura,
)
from financas.gerador import gerar_dados
from financas.metas import Meta, plano_da_meta
from financas.sistema import Sistema, treinar_modelo_da_base


def _compras(datas, descricoes, valores, parcelas=None):
    return pd.DataFrame({
        "data": datas,
        "descricao": descricoes,
        "parcela": parcelas or [""] * len(datas),
        "valor": valores,
    })


ABRIL = _compras(
    ["2026-03-29", "2026-04-02", "2026-04-10", "2026-04-15"],
    ["IFOOD RESTAURANTE", "SUPERMERCADO BOM PRECO", "MAGAZINE LOJAS", "NETFLIX"],
    [45.0, 320.0, 100.0, 39.9],
    ["", "", "1/3", ""],
)
MAIO = _compras(
    ["2026-05-03", "2026-05-10", "2026-05-15"],
    ["SUPERMERCADO BOM PRECO", "MAGAZINE LOJAS", "NETFLIX"],
    [350.0, 100.0, 39.9],
    ["", "2/3", ""],
)


@pytest.fixture(scope="module")
def modelo():
    return treinar_modelo_da_base()


def _diagnostico(extrato, usuarios, modelo):
    indicadores, textos = Sistema(extrato, usuarios, modelo).diagnosticar()
    return indicadores.set_index("id_usuario").loc[ID_FATURA], textos[ID_FATURA]


def test_cada_fatura_conta_como_um_mes():
    assert mes_da_fatura(ABRIL) == "2026-04"
    extrato, usuarios = extrato_de_faturas([ABRIL, MAIO], "ANA")
    assert sorted(extrato["data"].str[:7].unique()) == ["2026-04", "2026-05"]
    # A compra de 29/03 aparece na fatura de abril: entra no mês da fatura
    assert extrato.loc[extrato["descricao"] == "IFOOD RESTAURANTE", "data"].item() == "2026-04-01"
    assert list(usuarios["id_usuario"]) == [ID_FATURA]
    assert usuarios["nome"].item() == "ANA"


def test_extrato_de_faturas_tem_ids_unicos_e_so_compras_sem_renda():
    extrato, _ = extrato_de_faturas([ABRIL, MAIO], "")
    assert extrato["id_transacao"].is_unique
    assert len(extrato) == len(ABRIL) + len(MAIO)
    assert (extrato["valor"] < 0).all()
    assert (extrato["meio"] == "cartao_credito").all()


def test_renda_informada_entra_uma_vez_por_mes():
    extrato, _ = extrato_de_faturas([ABRIL, MAIO], "ANA", renda_mensal=3000)
    renda = extrato[extrato["valor"] > 0]
    assert len(renda) == 2
    assert (renda["descricao"] == DESCRICAO_RENDA_INFORMADA).all()
    assert renda["valor"].tolist() == [3000.0, 3000.0]
    assert extrato["id_transacao"].is_unique


def test_sem_compras_da_erro_claro():
    with pytest.raises(ValueError):
        extrato_de_faturas([_compras([], [], [])], "ANA")


def test_diagnostico_com_renda_informada(modelo):
    extrato, usuarios = extrato_de_faturas([ABRIL, MAIO], "ANA", renda_mensal=3000)
    linha, _ = _diagnostico(extrato, usuarios, modelo)
    assert linha["renda_media"] == pytest.approx(3000)
    assert linha["tipo_renda"] == "fixa"
    assert linha["sobra_media"] == pytest.approx(3000 - linha["gastos_total"])
    assert linha["taxa_de_sobra"] > 0


def test_diagnostico_sem_renda_nao_inventa_sobra(modelo):
    extrato, usuarios = extrato_de_faturas([ABRIL, MAIO], "ANA")
    linha, texto = _diagnostico(extrato, usuarios, modelo)
    assert linha["renda_media"] == 0
    assert linha["tipo_renda"] == "nao_informada"
    assert linha["gastos_total"] > 0
    assert any("Renda não informada" in ponto for ponto in linha["secoes"]["pontos"])
    outros_pontos = [ponto for ponto in linha["secoes"]["pontos"] if not ponto.startswith("Renda não informada")]
    assert not any("sobra" in ponto.lower() for ponto in outros_pontos)
    assert "—" in texto  # sobra e porcentagens sem base aparecem como "—"


def test_diagnostico_com_uma_fatura_so(modelo):
    extrato, usuarios = extrato_de_faturas([MAIO], "ANA")
    linha, _ = _diagnostico(extrato, usuarios, modelo)
    assert "Com um mês só" in linha["secoes"]["evolucao"]
    assert linha["variacao_gastos"] == 0


def test_meses_de_tamanhos_diferentes_comparam_medias_por_mes(modelo):
    # 3 faturas: a 1ª metade tem 1 mês e a 2ª tem 2. Gasto igual todo mês = sem variação.
    meses = ["2026-03", "2026-04", "2026-05"]
    faturas = [_compras([f"{mes}-10"], ["SUPERMERCADO BOM PRECO"], [300.0]) for mes in meses]
    extrato, usuarios = extrato_de_faturas(faturas, "ANA")
    linha, _ = _diagnostico(extrato, usuarios, modelo)
    assert linha["variacao_gastos"] == pytest.approx(0)


def test_faturas_em_pdf_viram_diagnostico(modelo):
    dados = gerar_dados()
    lidas = []
    for mes in ("2026-04", "2026-05", "2026-06"):
        compras = compras_no_cartao(dados["extrato"], "U08", mes)
        lidas.append(ler_fatura_pdf(gerar_fatura_pdf(compras, "JULIANA (FICTICIA)", mes))[0])
    extrato, usuarios = extrato_de_faturas(lidas, "JULIANA", renda_mensal=2500)
    linha, _ = _diagnostico(extrato, usuarios, modelo)
    assert linha["renda_media"] == pytest.approx(2500)
    assert "Comparando" in linha["secoes"]["evolucao"]


def test_meta_sem_renda_pede_a_renda():
    meta = Meta("Computador", 4000.0, 10, "2026-05")
    texto = plano_da_meta(meta, None)
    assert "Informe a renda" in texto
    assert "não sobra" not in texto
