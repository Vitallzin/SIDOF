"""Testes de indicadores e diagnóstico (Fase 6)."""

import re

import pandas as pd
import pytest

from financas.avaliacao import com_respostas_do_usuario
from financas.diagnostico import _bloco, _sentido, diagnosticar, gastos_por_bloco
from financas.normalizacao import normalizar
from financas.regras import classificar_por_regras

MESES = range(1, 7)


def _mensal(dia, descricao, valor, meio, parcela=None, conta=None):
    """A mesma transação nos 6 meses. parcela pode ser uma função do mês, ex.: lambda m: f'{m}/12'."""
    return [
        (f"2026-0{mes}-{dia:02d}", descricao, valor, meio, parcela(mes) if parcela else "", conta)
        for mes in MESES
    ]


def _classificar(linhas, nome="ANA VIEIRA"):
    extrato = pd.DataFrame([
        {
            "id_transacao": f"T{i}", "id_usuario": "U01", "data": data, "descricao": descricao, "valor": valor,
            "meio": meio, "parcela": parcela,
            "conta": conta or ("cartao" if meio == "cartao_credito" else "corrente"),
        }
        for i, (data, descricao, valor, meio, parcela, conta) in enumerate(linhas)
    ])
    usuarios = pd.DataFrame({"id_usuario": ["U01"], "nome": [nome]})
    return classificar_por_regras(normalizar(extrato), usuarios), usuarios


def _exemplo_da_proposta():
    """Renda de R$ 3.000: 1.700 essenciais, 500 discricionários, 300 parcelas, sobra de 500."""
    linhas = _mensal(5, "CREDITO SALARIO METALURGICA ALFA LTDA", 3000.0, "ted")
    linhas += _mensal(8, "PAGTO BOLETO IMOBILIARIA LAR DOCE LAR", -1000.0, "boleto")
    linhas += _mensal(10, "PAGTO BOLETO CIA ENERGIA ELETRICA", -150.0, "boleto")
    linhas += _mensal(11, "PAGTO BOLETO SANEAMENTO AGUAS CLARAS", -50.0, "boleto")
    linhas += _mensal(12, "COMPRA DEBITO SUPERMERCADO BOM PRECO", -500.0, "cartao_debito")
    linhas += _mensal(15, "RESTAURANTE SABOR CASEIRO", -300.0, "cartao_credito")
    linhas += _mensal(16, "STREAMING FILMES MAIS", -200.0, "cartao_credito")
    linhas += _mensal(18, "MAGAZINE ELETRO LAR", -100.0, "cartao_credito", lambda m: f"{m}/12")
    linhas += _mensal(20, "PAGTO BOLETO EMPRESTIMO PESSOAL BANCO FACIL", -200.0, "boleto", lambda m: f"{m + 5}/24")
    return linhas


def test_exemplo_da_proposta():
    classificado, usuarios = _classificar(_exemplo_da_proposta())
    tabela, textos = diagnosticar(classificado, usuarios)
    linha = tabela.iloc[0]
    assert linha["renda_media"] == 3000.0
    assert linha["essenciais"] == 1700.0
    assert linha["discricionarios"] == 500.0
    assert linha["parcelas"] == 300.0
    assert linha["prioritarios"] == 0.0
    assert linha["a_confirmar"] == 0.0
    assert linha["sobra_media"] == 500.0
    texto = textos["U01"]
    assert "R$ 1.700,00" in texto and "57%" in texto
    assert "R$ 500,00" in texto
    assert "Para onde foi o dinheiro" in texto
    assert "De onde vêm os números" in texto


def test_fatura_e_transferencia_interna_nao_contam_duas_vezes():
    linhas = _exemplo_da_proposta()
    linhas += _mensal(10, "PAGAMENTO FATURA CARTAO", -600.0, "boleto")
    linhas += _mensal(25, "TRANSF ENTRE CONTAS PROPRIAS", -300.0, "ted", conta="corrente")
    linhas += _mensal(25, "TRANSF ENTRE CONTAS PROPRIAS", 300.0, "ted", conta="poupanca")
    classificado, usuarios = _classificar(linhas)
    tabela, textos = diagnosticar(classificado, usuarios)
    linha = tabela.iloc[0]
    assert linha["gastos_total"] == 2500.0
    assert linha["sobra_media"] == 500.0
    assert linha["poupanca_por_mes"] == 300.0
    assert "R$ 300,00 por mês foram guardados" in textos["U01"]


def test_bloco_de_cada_categoria():
    assert _bloco("moradia", "") == "essenciais"
    assert _bloco("saude", "") == "prioritarios"
    assert _bloco("lazer", "") == "discricionarios"
    assert _bloco("compras", "3/10") == "parcelas"
    assert _bloco("nao_identificado", "") == "a_confirmar"
    assert _bloco("pagamento_fatura", "") is None
    assert _bloco("transferencia_interna", "") is None


def test_sentido_da_variacao():
    assert _sentido(0.02) == "ficaram estáveis"
    assert _sentido(0.25) == "subiram 25%"
    assert _sentido(-0.10) == "caíram 10%"


def test_gastos_por_bloco_preenche_meses_sem_gasto():
    saidas = pd.DataFrame({
        "id_usuario": ["U01"], "mes": ["2026-01"], "valor": [-50.0], "parcela": [""], "categoria_final": ["lazer"],
    })
    gastos = gastos_por_bloco(saidas, ["2026-01", "2026-02"])
    assert len(gastos) == 2 * 5  # 2 meses x 5 blocos
    assert gastos["valor"].sum() == 50.0


def test_pontos_de_atencao_com_linguagem_neutra():
    linhas = _mensal(5, "CREDITO SALARIO METALURGICA ALFA LTDA", 2000.0, "ted")
    linhas += _mensal(8, "PAGTO BOLETO IMOBILIARIA LAR DOCE LAR", -1500.0, "boleto")
    linhas += _mensal(20, "PAGTO BOLETO EMPRESTIMO PESSOAL BANCO FACIL", -800.0, "boleto", lambda m: f"{m}/24")
    classificado, usuarios = _classificar(linhas)
    _, textos = diagnosticar(classificado, usuarios)
    texto = textos["U01"]
    assert "saídas superaram a renda efetiva em R$ 300,00 por mês" in texto
    assert "Alto comprometimento da renda" in texto
    for palavra in ("gastador", "irresponsável", "gasta demais", "sonega", "invista", "ações", "fundo"):
        assert not re.search(rf"{palavra}", texto.lower()), palavra  # palavra inteira


def test_aumento_de_discricionarios_aparece_na_evolucao():
    linhas = _mensal(5, "CREDITO SALARIO METALURGICA ALFA LTDA", 3000.0, "ted")
    linhas += [(f"2026-0{m}-15", "RESTAURANTE SABOR CASEIRO", -100.0 if m <= 3 else -300.0, "cartao_credito", "", None) for m in MESES]
    classificado, usuarios = _classificar(linhas)
    tabela, textos = diagnosticar(classificado, usuarios)
    assert tabela.iloc[0]["variacao_discricionarios"] == pytest.approx(2.0)
    assert "discricionários subiram 200%" in textos["U01"]
    assert "restaurantes bares" in textos["U01"]


def test_com_respostas_do_usuario_preenche_so_as_perguntas():
    hibrido = pd.DataFrame({
        "categoria_final": ["energia", "nao_identificado"],
        "categoria": ["energia", "moradia"],
        "perguntar_usuario": [False, True],
    })
    confirmado = com_respostas_do_usuario(hibrido)
    assert list(confirmado["categoria_final"]) == ["energia", "moradia"]
    assert list(hibrido["categoria_final"]) == ["energia", "nao_identificado"]  # original intacto
