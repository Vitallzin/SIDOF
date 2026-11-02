"""Testes do sistema em uso (sem a verdade dos usuários atendidos)."""

import ast
import inspect

import pytest

from financas import sistema
from financas.experimento import metricas
from financas.gerador import gerar_dados
from financas.sistema import SEMENTE_BASE, Sistema, treinar_modelo_da_base


@pytest.fixture(scope="module")
def dados():
    return gerar_dados()


@pytest.fixture(scope="module")
def modelo():
    return treinar_modelo_da_base()


def test_base_de_treino_e_outra_populacao(dados):
    base = gerar_dados(SEMENTE_BASE)
    assert not base["extrato"]["descricao"].equals(dados["extrato"]["descricao"])
    assert not base["usuarios_verdade"]["renda_base"].equals(dados["usuarios_verdade"]["renda_base"])


def test_sistema_nunca_le_a_verdade_dos_atendidos():
    assert "verdade" not in inspect.signature(Sistema).parameters
    # Olha só o código (nomes e textos usados), não os comentários
    arvore = ast.parse(inspect.getsource(Sistema))
    nomes = {no.id for no in ast.walk(arvore) if isinstance(no, ast.Name)}
    textos = {no.value for no in ast.walk(arvore) if isinstance(no, ast.Constant) and isinstance(no.value, str)}
    assert "verdade" not in nomes
    assert not {"verdade", "categoria", "tipo_anomalia"} & textos


def test_sistema_decide_a_maior_parte_e_acerta(dados, modelo):
    atendido = Sistema(dados["extrato"], dados["usuarios"], modelo)
    saidas = atendido.saidas().merge(dados["verdade"][["id_transacao", "categoria"]], on="id_transacao")
    resultado = metricas(saidas)
    assert resultado["automaticas"] > 0.7
    assert resultado["precisao"] > 0.95


def test_responder_tira_a_pergunta_e_vale_para_os_proximos(dados, modelo):
    atendido = Sistema(dados["extrato"], dados["usuarios"], modelo)
    perguntas = atendido.perguntas("U01")
    contraparte = atendido.classificado.set_index("id_transacao").loc[perguntas["id_transacao"], "contraparte"]
    alvo = contraparte.value_counts().index[0]  # contraparte que gera mais perguntas
    ids_alvo = contraparte[contraparte == alvo].index
    atendido.responder(ids_alvo[0], "moradia")
    depois = atendido.saidas().set_index("id_transacao").loc[ids_alvo]
    assert not depois["perguntar_usuario"].any()
    assert (depois["categoria_final"] == "moradia").all()
    assert (depois["origem"] == "memoria").all()


def test_resposta_com_categoria_invalida(dados, modelo):
    atendido = Sistema(dados["extrato"], dados["usuarios"], modelo)
    with pytest.raises(ValueError):
        atendido.responder(dados["extrato"]["id_transacao"].iloc[0], "categoria_inventada")


def test_responder_diminui_o_a_confirmar_do_diagnostico(dados, modelo):
    atendido = Sistema(dados["extrato"], dados["usuarios"], modelo)
    antes, _ = atendido.diagnosticar()
    verdade = dados["verdade"].set_index("id_transacao")["categoria"]
    for id_transacao in atendido.perguntas("U01")["id_transacao"]:
        atendido.responder(id_transacao, verdade[id_transacao])
    depois, textos = atendido.diagnosticar()
    u01 = lambda tabela: tabela.set_index("id_usuario").loc["U01", "a_confirmar"]
    assert u01(depois) < u01(antes)
    assert "Diagnóstico de U01" in textos["U01"]


def test_sistema_gera_alertas_com_explicacao(dados, modelo):
    alertas = Sistema(dados["extrato"], dados["usuarios"], modelo).alertas()
    assert len(alertas) > 0
    assert (alertas["explicacao"].str.len() > 20).all()
