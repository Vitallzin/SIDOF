"""Testes de parcelas e compromissos futuros (Fase 5)."""

import pandas as pd
import pytest

from financas.avaliacao import contar_parcelamentos
from financas.formatacao import mes_por_extenso, reais
from financas.gerador import gerar_dados
from financas.normalizacao import normalizar
from financas.parcelas import (
    LIMITE_COMPROMETIMENTO_ALTO,
    comprometimento_da_renda,
    compromissos_futuros,
    identificar_parcelamentos,
    proximos_meses,
)
from financas.regras import classificar_por_regras
from financas.renda import classificar_entradas, perfil_de_renda


def _extrato(linhas):
    """linhas: (data, descricao, valor, meio, parcela)"""
    return pd.DataFrame([
        {"id_transacao": f"T{i}", "id_usuario": "U01", "data": data, "descricao": descricao,
         "valor": valor, "meio": meio, "conta": "cartao" if meio == "cartao_credito" else "corrente", "parcela": parcela}
        for i, (data, descricao, valor, meio, parcela) in enumerate(linhas)
    ])


def _exemplo_da_proposta():
    """R$ 1.200 em 12x de R$ 100, com as 4 primeiras parcelas pagas de janeiro a abril."""
    linhas = [(f"2026-0{m}-15", "MAGAZINE ELETRO LAR", -100.0, "cartao_credito", f"{m}/12") for m in range(1, 5)]
    return normalizar(_extrato(linhas))


def test_formatacao():
    assert reais(1234.5) == "R$ 1.234,50"
    assert mes_por_extenso("2027-02") == "fevereiro de 2027"
    assert proximos_meses("2026-11", 3) == ["2026-12", "2027-01", "2027-02"]


def test_exemplo_da_proposta_1200_em_12x_de_100():
    compra = identificar_parcelamentos(_exemplo_da_proposta()).iloc[0]
    assert compra["valor_total"] == 1200.0
    assert compra["valor_parcela"] == 100.0
    assert compra["total_parcelas"] == 12
    assert compra["ultima_paga"] == 4
    assert compra["parcelas_restantes"] == 8
    assert compra["valor_restante"] == 800.0
    assert compra["mes_final"] == "2026-12"
    assert "compra de R$ 1.200,00 em 12x de R$ 100,00" in compra["explicacao"]
    assert "Faltam 8 (R$ 800,00), até dezembro de 2026" in compra["explicacao"]


def test_exemplo_da_proposta_compromete_100_por_mes_ate_dezembro():
    parcelamentos = identificar_parcelamentos(_exemplo_da_proposta())
    compromissos = compromissos_futuros(parcelamentos, ["U01"], "2026-04")
    linha = compromissos.loc["U01"]
    assert list(linha[["2026-05", "2026-12"]]) == [100.0, 100.0]
    assert linha["2027-01"] == 0
    assert linha.sum() == 800.0


def test_compra_que_comecou_antes_do_periodo():
    linhas = [(f"2026-0{m}-10", "MOVEIS CASA BELA", -50.0, "cartao_credito", f"{m + 6}/10") for m in range(1, 5)]
    compra = identificar_parcelamentos(normalizar(_extrato(linhas))).iloc[0]
    assert compra["comecou_antes"]
    assert compra["parcelas_restantes"] == 0
    assert "Já quitada" in compra["explicacao"]


def test_duas_compras_na_mesma_loja_ficam_separadas():
    linhas = [
        ("2026-01-10", "LOJA X", -100.0, "cartao_credito", "1/3"),
        ("2026-02-10", "LOJA X", -100.0, "cartao_credito", "2/3"),
        ("2026-02-20", "LOJA X", -60.0, "cartao_credito", "1/5"),
    ]
    assert len(identificar_parcelamentos(normalizar(_extrato(linhas)))) == 2


def test_divida_por_boleto_entra_como_compromisso():
    linhas = [(f"2026-0{m}-05", "PAGTO BOLETO EMPRESTIMO PESSOAL BANCO FACIL", -300.0, "boleto", f"{m + 10}/24") for m in range(1, 7)]
    divida = identificar_parcelamentos(normalizar(_extrato(linhas))).iloc[0]
    assert divida["tipo"] == "dívida/financiamento"
    assert divida["parcelas_restantes"] == 8
    assert divida["explicacao"].startswith("EMPRESTIMO PESSOAL BANCO FACIL")


def test_comprometimento_da_renda_e_aviso_neutro():
    parcelamentos = identificar_parcelamentos(_exemplo_da_proposta())
    compromissos = compromissos_futuros(parcelamentos, ["U01"], "2026-04")
    perfis = pd.DataFrame({"id_usuario": ["U01"], "renda_referencia": [300.0]})
    linha = comprometimento_da_renda(parcelamentos, compromissos, perfis).iloc[0]
    assert linha["percentual_da_renda"] == pytest.approx(1 / 3, abs=0.001)
    assert linha["alto_comprometimento"] == (1 / 3 >= LIMITE_COMPROMETIMENTO_ALTO)
    assert "alto comprometimento da renda" in linha["explicacao"]
    for palavra in ("gastador", "irresponsável", "endividado demais"):
        assert palavra not in linha["explicacao"].lower()


def test_sem_parcelas_nao_ha_compromisso():
    extrato = normalizar(_extrato([("2026-03-10", "PADARIA", -10.0, "cartao_debito", "")]))
    parcelamentos = identificar_parcelamentos(extrato)
    assert parcelamentos.empty


@pytest.fixture(scope="module")
def conjunto_gerado():
    dados = gerar_dados()
    classificado = classificar_por_regras(normalizar(dados["extrato"]), dados["usuarios"])
    parcelamentos = identificar_parcelamentos(classificado)
    perfis = perfil_de_renda(classificar_entradas(classificado, dados["usuarios"]), sorted(classificado["mes"].unique()))
    compromissos = compromissos_futuros(parcelamentos, dados["usuarios"]["id_usuario"], classificado["mes"].max())
    return dados, parcelamentos, compromissos, comprometimento_da_renda(parcelamentos, compromissos, perfis)


def test_encontra_todos_os_parcelamentos_gerados(conjunto_gerado):
    dados, parcelamentos, _, _ = conjunto_gerado
    contagem = contar_parcelamentos(parcelamentos, dados["extrato"], dados["verdade"])
    assert (contagem["encontrados"] == contagem["existentes"]).all()


def test_valor_total_e_parcela_vezes_numero(conjunto_gerado):
    _, parcelamentos, _, _ = conjunto_gerado
    assert (parcelamentos["valor_total"] == (parcelamentos["valor_parcela"] * parcelamentos["total_parcelas"]).round(2)).all()
    assert (parcelamentos["parcelas_restantes"] >= 0).all()


def test_perfil_com_dividas_e_o_mais_comprometido(conjunto_gerado):
    dados, _, _, comprometimento = conjunto_gerado
    junto = comprometimento.merge(dados["usuarios_verdade"], on="id_usuario")
    media = junto.groupby("perfil")["percentual_da_renda"].mean()
    assert media.idxmax() == "renda_fixa_com_dividas"
