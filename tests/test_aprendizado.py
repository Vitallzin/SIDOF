"""Testes do aprendizado contínuo (sem internet: usa a memória local no lugar do Firebase)."""

import pandas as pd
import pytest

from financas.aprendizado import (
    ArmazenamentoMemoria,
    conhecimento_coletivo,
    criar_armazenamento,
    exemplos_de_treino,
    pode_aprender,
    registrar_confirmacao,
    registrar_uso_fatura,
    resumo,
)
from financas.modelo import buscar_no_coletivo
from financas.sistema import classificar_fatura, treinar_modelo_da_base


@pytest.fixture
def banco():
    return ArmazenamentoMemoria()


def test_sem_credenciais_usa_memoria_local():
    assert isinstance(criar_armazenamento(None), ArmazenamentoMemoria)


def test_so_vale_para_todos_com_duas_sessoes(banco):
    registrar_confirmacao(banco, "SUSHI KAZU", "restaurantes_bares", "sessao-a", "fatura")
    assert conhecimento_coletivo(banco) == {}
    registrar_confirmacao(banco, "SUSHI KAZU", "restaurantes_bares", "sessao-a", "fatura")  # mesma pessoa de novo
    assert conhecimento_coletivo(banco) == {}
    registrar_confirmacao(banco, "LV*SUSHIKAZU 1234", "restaurantes_bares", "sessao-b", "fatura")  # mesma loja
    assert conhecimento_coletivo(banco)["SUSHIKAZU"] == ("restaurantes_bares", 2, "SUSHI KAZU")


def test_vence_a_categoria_mais_votada(banco):
    for sessao, categoria in [("a", "compras"), ("b", "lazer"), ("c", "lazer"), ("d", "lazer")]:
        registrar_confirmacao(banco, "BOLICHE STRIKE", categoria, sessao, "ficticio")
    assert conhecimento_coletivo(banco)["BOLICHESTRIKE"][:2] == ("lazer", 3)


def test_pessoas_renda_e_transferencias_nunca_sao_guardadas(banco):
    assert not registrar_confirmacao(banco, "CARLOS LOPES", "moradia", "a", "ficticio", "PIX ENVIADO CARLOS LOPES")
    assert not registrar_confirmacao(banco, "SUSHI KAZU", "renda_variavel", "a", "fatura")
    assert not registrar_confirmacao(banco, "SUSHI KAZU", "transferencia_interna", "a", "fatura")
    assert banco.ler_lojas() == {}
    assert pode_aprender("LV*SUSHIKAZU", "restaurantes_bares")
    # Nome curto de loja parece de pessoa, mas numa compra de cartão é loja
    assert pode_aprender("SUSHI KAZU", "restaurantes_bares", "SUSHI KAZU")
    assert not pode_aprender("SUSHI KAZU", "restaurantes_bares", "PIX ENVIADO SUSHI KAZU")


def test_nada_alem_de_loja_categoria_e_origem_e_guardado(banco):
    registrar_confirmacao(banco, "SUSHI KAZU", "restaurantes_bares", "a", "fatura")
    registrar_uso_fatura(banco, compras=10, perguntas=3, resolvidas_pelo_coletivo=2)
    loja = banco.ler_lojas()["SUSHIKAZU"]
    assert set(loja) == {"nome", "votos", "atualizado_em"}
    assert loja["votos"]["a"] == {"categoria": "restaurantes_bares", "origem": "fatura"}
    assert set(banco.ler_usos()[0]) == {"data_hora", "compras", "perguntas", "resolvidas_pelo_coletivo"}


def test_origem_invalida(banco):
    with pytest.raises(ValueError):
        registrar_confirmacao(banco, "SUSHI KAZU", "restaurantes_bares", "a", "outra")


def test_resumo_separa_as_origens(banco):
    for sessao in ("a", "b"):
        registrar_confirmacao(banco, "SUSHI KAZU", "restaurantes_bares", sessao, "fatura")
        registrar_confirmacao(banco, "EMPORIO DONA ROSA", "alimentacao_basica", sessao, "ficticio")
    registrar_confirmacao(banco, "BAZAR DA ESQUINA", "compras", "a", "ficticio")
    dados = resumo(banco)
    assert dados["lojas_aprendidas"] == 2 and dados["lojas_com_votos"] == 3
    assert dados["aprendidas_por_origem"] == {"fatura": 1, "ficticio": 1}
    assert dados["confirmacoes"] == 5 and dados["sessoes"] == 2


def test_busca_no_coletivo_reconhece_a_mesma_loja_escrita_diferente():
    conhecimento = {"SUSHIKAZU": ("restaurantes_bares", 2, "SUSHI KAZU")}
    assert buscar_no_coletivo(conhecimento, "PGTO*SUSHIKAZU SAO PAULO")[0] == "restaurantes_bares"
    assert buscar_no_coletivo(conhecimento, "CARLOS LOPES", pix_para_pessoa=True) is None
    assert buscar_no_coletivo({}, "SUSHI KAZU") is None


def test_fatura_nova_usa_o_que_outros_ensinaram(banco):
    for sessao in ("a", "b"):
        registrar_confirmacao(banco, "QUIOSQUE TAPIOCA DA PRAIA", "restaurantes_bares", sessao, "fatura")
    compras = pd.DataFrame({"data": ["2026-03-05"], "descricao": ["QUIOSQUE TAPIOCA DA PRAIA"], "parcela": [""], "valor": [18.0]})
    modelo = treinar_modelo_da_base()
    sem = classificar_fatura(compras, modelo)
    com = classificar_fatura(compras, modelo, conhecimento=conhecimento_coletivo(banco))
    assert sem.loc[0, "origem"] != "coletivo"
    assert com.loc[0, "origem"] == "coletivo"
    assert com.loc[0, "categoria_final"] == "restaurantes_bares"
    assert not com.loc[0, "perguntar_usuario"]
    assert "outros usuários" in com.loc[0, "explicacao_final"]


def test_retreino_inclui_as_lojas_aprendidas():
    exemplos = exemplos_de_treino({"XQZW": ("lazer", 2, "XQZW ARENA DIVERSAO")})
    assert exemplos == (("XQZW ARENA DIVERSAO", "lazer"),)
    modelo = treinar_modelo_da_base(exemplos_extra=exemplos)
    assert modelo is not treinar_modelo_da_base()
    assert modelo.predict(["XQZW ARENA DIVERSAO"])[0] == "lazer"
