"""Testes da classificação por regras (Fase 2)."""

import pandas as pd
import pytest

from financas import catalogo
from financas.avaliacao import avaliar_regras
from financas.categorias import CATEGORIAS
from financas.gerador import gerar_dados
from financas.normalizacao import normalizar
from financas.regras import CONFIANCA_MINIMA, REGRAS, classificar_linha, classificar_por_regras


def _linha(descricao, valor=-50.0):
    tabela = normalizar(pd.DataFrame({
        "id_transacao": ["T1"], "id_usuario": ["U01"], "data": ["2026-03-05"],
        "descricao": [descricao], "valor": [valor], "meio": ["pix"], "conta": ["corrente"], "parcela": [""],
    }))
    return tabela.iloc[0].to_dict()


def _classificar(descricao, valor=-50.0, nome_usuario="ANA VIEIRA"):
    return classificar_linha(_linha(descricao, valor), nome_usuario)


@pytest.mark.parametrize("descricao, categoria", [
    ("PAGTO BOLETO CIA ENERGIA ELETRICA", "energia"),
    ("COMPRA DEBITO SUPERMERCADO BOM PRECO", "alimentacao_basica"),
    ("PIX ENVIADO PADARIA PAO DOURADO", "alimentacao_basica"),
    ("DLV*APP ENTREGA COMIDA", "restaurantes_bares"),
    ("LOJA JOGOS DIGITAIS *ONLINE", "jogos"),  # jogos vem antes de compras
    ("PAGAMENTO FATURA CARTAO", "pagamento_fatura"),
    ("PAGTO BOLETO EMPRESTIMO PESSOAL BANCO FACIL", "pagamento_dividas"),
])
def test_regras_reconhecem_casos_obvios(descricao, categoria):
    resultado = _classificar(descricao)
    assert resultado["categoria_regra"] == categoria
    assert resultado["confianca"] >= CONFIANCA_MINIMA


def test_salario_e_renda_fixa():
    assert _classificar("CREDITO SALARIO COMERCIAL BETA SA", 4000.0)["categoria_regra"] == "renda_fixa"


def test_pix_para_o_proprio_nome_e_transferencia_interna():
    resultado = _classificar("PIX ENVIADO ANA VIEIRA", nome_usuario="ANA VIEIRA")
    assert resultado["categoria_regra"] == "transferencia_interna"
    assert resultado["regra"] == "pix_proprio_nome"


def test_pix_para_pessoa_nao_e_adivinhado():
    resultado = _classificar("PIX ENVIADO RODRIGO RODRIGUES")
    assert resultado["categoria_regra"] == "nao_identificado"
    assert resultado["confianca"] < CONFIANCA_MINIMA
    assert "pessoa" in resultado["explicacao"]


def test_entrada_desconhecida_vira_renda_nao_identificada():
    resultado = _classificar("PIX RECEBIDO LUANA ROCHA", 400.0)
    assert resultado["categoria_regra"] == "renda_nao_identificada"
    assert resultado["confianca"] < CONFIANCA_MINIMA


def test_regra_respeita_direcao():
    # Dinheiro entrando de um supermercado não é gasto com alimentação
    resultado = _classificar("PIX RECEBIDO SUPERMERCADO BOM PRECO", 30.0)
    assert resultado["categoria_regra"] != "alimentacao_basica"


def test_palavra_precisa_ser_inteira():
    # "BAR" não pode combinar com o sobrenome "BARBOSA"
    assert _classificar("PIX ENVIADO ANA BARBOSA")["categoria_regra"] == "nao_identificado"


def test_nenhum_nome_de_pessoa_dispara_regra():
    for nome in catalogo.PRIMEIROS_NOMES:
        for sobrenome in catalogo.SOBRENOMES:
            resultado = _classificar(f"PIX ENVIADO {nome} {sobrenome}", nome_usuario="USUARIO TESTE")
            assert resultado["regra"] == "sem_regra", f"{nome} {sobrenome}"


def test_todas_as_regras_sao_validas():
    nomes = [regra.nome for regra in REGRAS]
    assert len(nomes) == len(set(nomes))
    for regra in REGRAS:
        assert regra.categoria in CATEGORIAS
        assert 0 < regra.confianca <= 1
        assert regra.direcao in ("saida", "entrada", "qualquer")


@pytest.fixture(scope="module")
def classificado_e_verdade():
    dados = gerar_dados()
    classificado = classificar_por_regras(normalizar(dados["extrato"]), dados["usuarios"])
    return classificado, dados["verdade"]


def test_toda_transacao_tem_categoria_confianca_e_explicacao(classificado_e_verdade):
    classificado, _ = classificado_e_verdade
    assert classificado["categoria_regra"].isin(CATEGORIAS).all()
    assert classificado["confianca"].between(0, 1).all()
    assert (classificado["explicacao"].str.len() > 0).all()
    assert (classificado["perguntar_usuario"] == (classificado["confianca"] < CONFIANCA_MINIMA)).all()


def test_pix_ambiguo_nunca_tem_confianca_alta(classificado_e_verdade):
    classificado, verdade = classificado_e_verdade
    junto = classificado.merge(verdade, on="id_transacao")
    ambiguos = junto[junto["ambigua"] == "sim"]
    assert ambiguos["perguntar_usuario"].all()


def test_avaliacao_no_conjunto_gerado(classificado_e_verdade):
    resultado = avaliar_regras(*classificado_e_verdade)
    # Com descrições realistas (abreviadas, lojas desconhecidas) as regras reconhecem menos
    assert resultado["cobertura"] > 0.3
    assert resultado["precisao"] > 0.9
    assert len(resultado["nao_identificadas"]) + resultado["cobertura"] * resultado["total"] == pytest.approx(resultado["total"])


def test_avaliacao_em_exemplo_pequeno():
    classificado = pd.DataFrame({
        "id_transacao": ["A", "B", "C", "D"],
        "categoria_regra": ["energia", "compras", "nao_identificado", "agua"],
        "confianca": [0.95, 0.75, 0.0, 0.9],
        "regra": ["energia", "compras", "sem_regra", "agua"],
        "perguntar_usuario": [False, False, True, False],
        "descricao": ["a", "b", "c", "d"],
        "explicacao": ["x", "x", "y", "x"],
    })
    verdade = pd.DataFrame({
        "id_transacao": ["A", "B", "C", "D"],
        "categoria": ["energia", "assinaturas", "lazer", "agua"],
        "ambigua": ["nao", "nao", "sim", "nao"],
    })
    resultado = avaliar_regras(classificado, verdade)
    assert resultado["cobertura"] == 0.75
    assert resultado["precisao"] == pytest.approx(2 / 3)
    assert resultado["perguntas"] == 0.25
    assert list(resultado["erros"]["id_transacao"]) == ["B"]
