"""Testes do monitoramento e da interface (Fase 9)."""

import pytest
from streamlit.testing.v1 import AppTest

from financas.gerador import gerar_dados
from financas.monitoramento import extrato_ate, notificacoes_do_mes
from financas.sistema import treinar_modelo_da_base


@pytest.fixture(scope="module")
def dados():
    return gerar_dados()


@pytest.fixture(scope="module")
def modelo():
    return treinar_modelo_da_base()


def test_extrato_ate_corta_os_meses_seguintes(dados):
    parcial = extrato_ate(dados["extrato"], "2026-03")
    assert parcial["data"].str[:7].max() == "2026-03"
    assert len(parcial) < len(dados["extrato"])


def test_notificacoes_tem_tipo_e_mensagem(dados, modelo):
    notificacoes = notificacoes_do_mes(dados["extrato"], dados["usuarios"], modelo, "2026-05")
    assert len(notificacoes) > 0
    assert (notificacoes["mensagem"].str.len() > 20).all()
    assert set(notificacoes["tipo"]) <= {
        "Aumento de gasto", "Possível cobrança duplicada", "Compra alta em lugar novo",
        "Muitas compras em pouco tempo", "Nova parcela", "Queda de renda",
    }


def test_troca_de_emprego_gera_aviso_de_queda_de_renda(dados, modelo):
    # Usuários que trocaram de emprego ficam um mês sem salário (março ou abril)
    trocas = dados["usuarios_verdade"].loc[dados["usuarios_verdade"]["troca_emprego"], "id_usuario"]
    avisados = set()
    for mes in ("2026-03", "2026-04"):
        notificacoes = notificacoes_do_mes(dados["extrato"], dados["usuarios"], modelo, mes)
        avisados |= set(notificacoes.loc[notificacoes["tipo"] == "Queda de renda", "id_usuario"])
    assert set(trocas) <= avisados


def test_notificacao_nao_usa_meses_futuros(dados, modelo):
    # O que o sistema diz em abril não pode mudar por causa de maio e junho
    so_ate_abril = extrato_ate(dados["extrato"], "2026-04")
    com_tudo = notificacoes_do_mes(dados["extrato"], dados["usuarios"], modelo, "2026-04")
    sem_futuro = notificacoes_do_mes(so_ate_abril, dados["usuarios"], modelo, "2026-04")
    assert com_tudo.equals(sem_futuro)


def _textos(app):
    return " ".join(elemento.value for elemento in app.markdown)


def test_interface_abre_e_troca_de_usuario_e_mes():
    app = AppTest.from_file("../app.py", default_timeout=180).run()
    assert not app.exception
    assert "junho de 2026" in _textos(app)  # abre no último mês
    app.sidebar.selectbox[0].set_value("U09").run()
    assert not app.exception
    app.sidebar.select_slider[0].set_value("2026-04").run()
    assert not app.exception
    assert "abril de 2026" in _textos(app)
    assert "Olá" in app.header[0].value
