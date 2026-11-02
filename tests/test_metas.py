"""Testes de metas financeiras (Fase 7)."""

import re

import pandas as pd
import pytest

from financas.metas import Meta, acompanhar, aportes_por_mes, meta_exemplo, plano_da_meta, previsao, reserva_de_referencia
from financas.normalizacao import normalizar
from financas.regras import classificar_por_regras

COMPUTADOR = Meta("Computador", 4000.0, 10, "2026-01")


def test_exemplo_da_proposta_400_por_mes():
    assert COMPUTADOR.valor_mensal == 400.0
    assert COMPUTADOR.mes_final == "2026-10"
    assert meta_exemplo("2026-01") == Meta("Computador novo", 4000.0, 10, "2026-01")


def test_exemplo_da_proposta_no_ritmo():
    acompanhamento = acompanhar(COMPUTADOR, [400.0] * 10)
    assert list(acompanhamento["situacao"][:9]) == ["no ritmo"] * 9
    assert acompanhamento["situacao"].iloc[-1] == "concluída"
    resumo = previsao(COMPUTADOR, acompanhamento)
    assert resumo["falta"] == 0
    assert "A meta foi atingida" in resumo["explicacao"]


def test_exemplo_da_proposta_com_ritmo_menor():
    # Guardando R$ 300 em vez de R$ 400 nos 4 primeiros meses
    acompanhamento = acompanhar(COMPUTADOR, [300.0] * 4)
    assert acompanhamento["acumulado"].iloc[-1] == 1200.0
    assert acompanhamento["esperado"].iloc[-1] == 1600.0
    assert (acompanhamento["situacao"] == "atrasada").all()
    resumo = previsao(COMPUTADOR, acompanhamento)
    assert resumo["meses_previstos"] == 14  # 4 + ceil(2800 / 300)
    assert resumo["mensal_para_cumprir_prazo"] == pytest.approx(2800 / 6, abs=0.01)
    assert "deve levar cerca de 14 meses, 4 meses a mais que o planejado" in resumo["explicacao"]
    assert "R$ 466,67 por mês nos 6 meses restantes" in resumo["explicacao"]


def test_ritmo_maior_fica_adiantada_e_dentro_do_prazo():
    resumo = previsao(COMPUTADOR, acompanhar(COMPUTADOR, [800.0] * 2))
    assert resumo["situacao"] == "adiantada"
    assert resumo["meses_previstos"] == 5
    assert "dentro do prazo" in resumo["explicacao"]


def test_sem_aportes_nao_inventa_previsao():
    resumo = previsao(COMPUTADOR, acompanhar(COMPUTADOR, [0.0, 0.0]))
    assert resumo["meses_previstos"] is None
    assert "não dá para estimar" in resumo["explicacao"]


def test_valor_ja_guardado_reduz_o_mensal():
    meta = Meta("Viagem", 3000.0, 10, "2026-01", ja_guardado=1000.0)
    assert meta.valor_mensal == 200.0


def test_plano_compara_com_a_sobra():
    assert "Cabe na sobra média" in plano_da_meta(COMPUTADOR, 1000.0)
    texto = plano_da_meta(COMPUTADOR, 250.0)
    assert "mais que a sobra média" in texto and "cerca de 16 meses" in texto
    assert "não sobra dinheiro" in plano_da_meta(COMPUTADOR, -100.0)


def test_plano_lembra_a_ordem_quando_a_renda_varia_e_e_neutro():
    texto = plano_da_meta(COMPUTADOR, 1000.0, tipo_renda="autonoma")
    assert "reserva para meses difíceis" in texto
    for palavra in ("invista", "ações", "tesouro", "cdb", "fundo", "gastador"):
        assert not re.search(rf"\b{palavra}\b", texto.lower()), palavra


def test_reserva_de_referencia():
    assert reserva_de_referencia(2000.0, "fixa") == (6000.0, 3)
    assert reserva_de_referencia(2000.0, "autonoma") == (12000.0, 6)


def test_aportes_vem_das_transferencias_para_a_poupanca():
    extrato = pd.DataFrame([
        {"id_transacao": f"T{i}", "id_usuario": "U01", "data": data, "descricao": "TRANSF ENTRE CONTAS PROPRIAS",
         "valor": valor, "meio": "ted", "conta": conta, "parcela": ""}
        for i, (data, valor, conta) in enumerate([
            ("2026-01-10", -500.0, "corrente"), ("2026-01-10", 500.0, "poupanca"),
            ("2026-02-10", 100.0, "corrente"), ("2026-02-10", -100.0, "poupanca"),  # resgate
        ])
    ])
    usuarios = pd.DataFrame({"id_usuario": ["U01"], "nome": ["ANA VIEIRA"]})
    classificado = classificar_por_regras(normalizar(extrato), usuarios)
    aportes = aportes_por_mes(classificado, ["2026-01", "2026-02", "2026-03"])
    assert list(aportes.loc["U01"]) == [500.0, -100.0, 0.0]


def test_prazo_muito_longo_aparece_em_anos_e_sugere_rever():
    texto = plano_da_meta(COMPUTADOR, 10.0)
    assert "400 meses (cerca de 33 anos)" in texto
    assert "rever o valor ou o prazo" in texto
