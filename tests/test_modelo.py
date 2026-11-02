"""Testes do modelo, da classificação híbrida e do experimento (Fase 3)."""

import pandas as pd
import pytest

from financas import experimento
from financas.experimento import dividir_por_usuario, executar_experimento, metricas
from financas.gerador import gerar_dados
from financas.modelo import CONFIANCA_MEMORIA, classificar_hibrido, prever, treinar
from financas.normalizacao import normalizar
from financas.regras import CONFIANCA_MINIMA, classificar_por_regras

TREINO = [
    ("SUPERMERCADO BOM PRECO", "alimentacao_basica"),
    ("SUPERMERCADO SAO JORGE", "alimentacao_basica"),
    ("MERCADINHO BOM PRECO", "alimentacao_basica"),
    ("PIZZARIA FORNO A LENHA", "restaurantes_bares"),
    ("PIZZARIA DO CHEF", "restaurantes_bares"),
    ("SUSHI KAZU", "restaurantes_bares"),
    ("PIX ENVIADO CARLOS LOPES", "moradia"),
    ("PIX ENVIADO CARLOS LOPES", "moradia"),
    ("PIX ENVIADO CARLOS LOPES", "moradia"),
]


@pytest.fixture(scope="module")
def modelo():
    textos, categorias = zip(*TREINO)
    return treinar(textos, categorias, c=10)


def _classificado(descricoes, nome_usuario="ANA VIEIRA"):
    quantidade = len(descricoes)
    extrato = pd.DataFrame({
        "id_transacao": [f"T{i}" for i in range(quantidade)],
        "id_usuario": ["U01"] * quantidade,
        "data": ["2026-03-05"] * quantidade,
        "descricao": descricoes,
        "valor": [-50.0] * quantidade,
        "meio": ["cartao_credito"] * quantidade,
        "conta": ["cartao"] * quantidade,
        "parcela": [""] * quantidade,
    })
    usuarios = pd.DataFrame({"id_usuario": ["U01"], "nome": [nome_usuario]})
    return classificar_por_regras(normalizar(extrato), usuarios)


def test_prever_devolve_categoria_e_probabilidade(modelo):
    categorias, confiancas = prever(modelo, ["PIZZARIA NOVA"])
    assert categorias[0] == "restaurantes_bares"
    assert 0 <= confiancas[0] <= 1


def test_modelo_entende_nome_colado_e_abreviado(modelo):
    categorias, _ = prever(modelo, ["PGTO*SUPERMERCADOBOMPR"])
    assert categorias[0] == "alimentacao_basica"


def test_treino_e_reproduzivel():
    textos, categorias = zip(*TREINO)
    _, primeira = prever(treinar(textos, categorias), ["SUSHI KAZU"])
    _, segunda = prever(treinar(textos, categorias), ["SUSHI KAZU"])
    assert primeira[0] == segunda[0]


def test_regra_tem_prioridade_sobre_o_modelo(modelo):
    resultado = classificar_hibrido(_classificado(["PAGTO BOLETO CIA ENERGIA ELETRICA"]), modelo)
    assert resultado.loc[0, "origem"] == "regra"
    assert resultado.loc[0, "categoria_final"] == "energia"


def test_modelo_decide_o_que_as_regras_nao_reconhecem(modelo):
    resultado = classificar_hibrido(_classificado(["MAQ*SUSHIKAZU"]), modelo)
    assert resultado.loc[0, "sugestao_modelo"] == "restaurantes_bares"
    assert resultado.loc[0, "origem"] in ("modelo", "pergunta")


def test_confianca_baixa_vira_pergunta_sem_inventar(modelo):
    resultado = classificar_hibrido(_classificado(["XYZ 123"]), modelo)
    linha = resultado.loc[0]
    if linha["confianca_final"] < CONFIANCA_MINIMA:
        assert linha["perguntar_usuario"]
        assert linha["origem"] == "pergunta"
        assert linha["categoria_final"] == "nao_identificado"
        assert "Perguntar" in linha["explicacao_final"]


def test_pix_para_pessoa_nunca_e_decidido_pelo_modelo(modelo):
    # O modelo viu CARLOS LOPES como moradia, mas só o usuário sabe a finalidade
    resultado = classificar_hibrido(_classificado(["PIX ENVIADO CARLOS LOPES"]), modelo)
    assert resultado.loc[0, "sugestao_modelo"] == "moradia"
    assert resultado.loc[0, "perguntar_usuario"]


def test_memoria_usa_a_resposta_do_usuario(modelo):
    memoria = {("U01", "CARLOS LOPES"): "moradia"}
    resultado = classificar_hibrido(_classificado(["PIX ENVIADO CARLOS LOPES"]), modelo, memoria)
    assert resultado.loc[0, "origem"] == "memoria"
    assert resultado.loc[0, "categoria_final"] == "moradia"
    assert resultado.loc[0, "confianca_final"] == CONFIANCA_MEMORIA
    assert not resultado.loc[0, "perguntar_usuario"]


def test_toda_linha_tem_explicacao(modelo):
    resultado = classificar_hibrido(_classificado(["SUSHI KAZU", "PIX ENVIADO CARLOS LOPES", "PADARIA X"]), modelo)
    assert (resultado["explicacao_final"].str.len() > 0).all()


def test_divisao_por_usuario():
    dados = gerar_dados()
    rodadas = dividir_por_usuario(dados["usuarios_verdade"])
    assert len(rodadas) == 3
    todos = set().union(*rodadas)
    assert len(todos) == 12  # cada usuário é testado exatamente uma vez
    perfis = dados["usuarios_verdade"].set_index("id_usuario")["perfil"]
    for teste in rodadas:
        assert len(teste) == 4
        assert perfis[list(teste)].nunique() == 4  # um de cada perfil


def test_metricas_em_exemplo_pequeno():
    tabela = pd.DataFrame({
        "categoria_final": ["energia", "lazer", "nao_identificado", "agua"],
        "categoria": ["energia", "compras", "saude", "agua"],
        "perguntar_usuario": [False, False, True, False],
    })
    resultado = metricas(tabela)
    assert resultado["automaticas"] == 0.75
    assert resultado["precisao"] == pytest.approx(2 / 3)
    assert resultado["erros_silenciosos"] == 0.25
    assert resultado["perguntas"] == 0.25


@pytest.fixture(scope="module")
def resultado_experimento():
    # Um único valor de C para o teste ficar rápido
    original = experimento.VALORES_DE_C
    experimento.VALORES_DE_C = [10]
    try:
        dados = gerar_dados()
        classificado = classificar_por_regras(normalizar(dados["extrato"]), dados["usuarios"])
        yield executar_experimento(classificado, dados["verdade"], dados["usuarios_verdade"]), classificado
    finally:
        experimento.VALORES_DE_C = original


def test_experimento_testa_cada_saida_uma_vez(resultado_experimento):
    resultado, classificado = resultado_experimento
    saidas = classificado[classificado["direcao"] == "saida"]
    for nome in ("hibrido", "simulacao"):
        assert resultado[nome]["id_transacao"].is_unique
        assert set(resultado[nome]["id_transacao"]) == set(saidas["id_transacao"])


def test_hibrido_decide_mais_que_as_regras_sem_perder_precisao(resultado_experimento):
    resultado, _ = resultado_experimento
    comparacao = experimento.comparar_estrategias(resultado)
    regras, hibrido = comparacao.iloc[0], comparacao.iloc[1]
    assert hibrido["automaticas"] > regras["automaticas"]
    assert hibrido["precisao"] > 0.95


def test_correcoes_diminuem_as_perguntas(resultado_experimento):
    resultado, _ = resultado_experimento
    comparacao = experimento.comparar_estrategias(resultado)
    assert comparacao.iloc[2]["perguntas"] < comparacao.iloc[1]["perguntas"]


def test_nenhum_pix_ambiguo_decidido_pelo_modelo(resultado_experimento):
    resultado, _ = resultado_experimento
    hibrido = resultado["hibrido"]
    assert not ((hibrido["ambigua"] == "sim") & (hibrido["origem"] == "modelo")).any()


def test_lojas_de_teste_cada_loja_sai_uma_vez():
    verdade = gerar_dados()["verdade"]
    rodadas = [experimento.lojas_de_teste(verdade, rodada) for rodada in range(experimento.RODADAS)]
    for i in range(len(rodadas)):
        for j in range(i + 1, len(rodadas)):
            assert not rodadas[i] & rodadas[j]  # nenhuma loja é "nova" em duas rodadas
    lojas = verdade.loc[verdade["loja"] != "", ["loja", "categoria"]].drop_duplicates()
    por_categoria = lojas.groupby("categoria")["loja"].apply(set)
    separadas = set().union(*rodadas)
    for categoria, nomes in por_categoria.items():
        if len(nomes) >= experimento.MINIMO_DE_LOJAS:
            assert nomes <= separadas, categoria
        else:
            assert not nomes & separadas, categoria  # categoria com poucas lojas nunca fica sem treino


def test_teste_duro_marca_lojas_novas():
    original = experimento.VALORES_DE_C
    experimento.VALORES_DE_C = [10]
    try:
        dados = gerar_dados()
        classificado = classificar_por_regras(normalizar(dados["extrato"]), dados["usuarios"])
        resultado = executar_experimento(classificado, dados["verdade"], dados["usuarios_verdade"], separar_lojas=True)
    finally:
        experimento.VALORES_DE_C = original
    hibrido = resultado["hibrido"]
    assert hibrido["loja_nova"].any() and not hibrido["loja_nova"].all()
    assert (hibrido.loc[hibrido["loja_nova"], "loja"] != "").all()
    tabela = experimento.comparar_por_grupo_de_loja(resultado)
    assert set(tabela.index.get_level_values("grupo")) == {"loja nova", "loja já vista", "sem loja (ex.: PIX p/ pessoa)"}


def test_memoria_reaproveita_loja_escrita_de_outro_jeito():
    from financas.modelo import buscar_na_memoria
    memoria = {("U01", "SUSHI KAZU"): "restaurantes_bares"}
    assert buscar_na_memoria(memoria, "U01", "LV*SUSHIKAZU SAO PAULO") == ("restaurantes_bares", "SUSHI KAZU")
    assert buscar_na_memoria(memoria, "U02", "SUSHI KAZU") is None  # memória é de cada usuário


def test_memoria_nao_confunde_pessoas_parecidas():
    from financas.modelo import buscar_na_memoria
    memoria = {("U01", "MARIA SILVA"): "moradia"}
    assert buscar_na_memoria(memoria, "U01", "MARIA SILVA") == ("moradia", "MARIA SILVA")
    assert buscar_na_memoria(memoria, "U01", "MARIA SOUZA") is None
