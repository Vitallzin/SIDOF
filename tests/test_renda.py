"""Testes de renda e transferências internas (Fase 4)."""

import pandas as pd
import pytest

from financas.gerador import gerar_dados
from financas.normalizacao import normalizar
from financas.regras import classificar_por_regras
from financas.renda import classificar_entradas, parece_empresa, perfil_de_renda, transferencias_por_par

MESES = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]


def _tabela(linhas, nome_usuario="ANA VIEIRA"):
    """linhas: lista de (data, descricao, valor) ou (data, descricao, valor, conta)."""
    registros = []
    for i, linha in enumerate(linhas):
        data, descricao, valor = linha[:3]
        conta = linha[3] if len(linha) > 3 else "corrente"
        registros.append({
            "id_transacao": f"T{i}", "id_usuario": "U01", "data": data, "descricao": descricao,
            "valor": valor, "meio": "pix", "conta": conta, "parcela": "",
        })
    usuarios = pd.DataFrame({"id_usuario": ["U01"], "nome": [nome_usuario]})
    return classificar_por_regras(normalizar(pd.DataFrame(registros)), usuarios), usuarios


def _categorias(linhas, nome_usuario="ANA VIEIRA"):
    classificado, usuarios = _tabela(linhas, nome_usuario)
    entradas = classificar_entradas(classificado, usuarios)
    return entradas.set_index("id_transacao")


def test_parece_empresa():
    assert parece_empresa("STUDIO DESIGN LTDA")
    assert parece_empresa("CONSTRUTORA HORIZONTE")
    assert parece_empresa("EVENTOS E FESTAS ALEGRIA")  # nome longo
    assert not parece_empresa("MARIA SOUZA")


def test_par_de_transferencia_sem_descricao_util():
    classificado, _ = _tabela([
        ("2026-03-10", "DOC 123", -500.0, "corrente"),
        ("2026-03-10", "CREDITO 456", 500.0, "poupanca"),
        ("2026-03-11", "CREDITO 789", 500.0, "poupanca"),  # outro dia: não é par
    ])
    assert transferencias_por_par(classificado) == {"T0", "T1"}


def test_par_ignora_mesma_conta_e_cartao():
    classificado, _ = _tabela([
        ("2026-03-10", "PIX ENVIADO JOSE LIMA", -80.0, "corrente"),
        ("2026-03-10", "PIX RECEBIDO MARIA LIMA", 80.0, "corrente"),
        ("2026-03-12", "LOJA X", -60.0, "cartao"),
        ("2026-03-12", "PIX RECEBIDO JOAO ROCHA", 60.0, "corrente"),
    ])
    assert transferencias_por_par(classificado) == set()


def test_cada_transacao_so_entra_em_um_par():
    classificado, _ = _tabela([
        ("2026-03-10", "SAIDA A", -100.0, "corrente"),
        ("2026-03-10", "ENTRADA A", 100.0, "poupanca"),
        ("2026-03-10", "ENTRADA B", 100.0, "poupanca"),
    ])
    assert len(transferencias_por_par(classificado)) == 2


def test_salario_empresa_e_transferencia():
    entradas = _categorias([
        ("2026-03-05", "CREDITO SALARIO METALURGICA ALFA LTDA", 4000.0),
        ("2026-03-08", "PIX RECEBIDO STUDIO DESIGN LTDA", 900.0),
        ("2026-03-09", "PIX RECEBIDO ANA VIEIRA", 300.0, "poupanca"),
    ])
    assert entradas.loc["T0", "categoria_renda"] == "renda_fixa"
    assert entradas.loc["T1", "categoria_renda"] == "renda_variavel"
    assert entradas.loc["T2", "categoria_renda"] == "transferencia_interna"
    assert not entradas.loc[["T0", "T1", "T2"], "perguntar_usuario"].any()


def test_mesmo_sobrenome_e_ajuda_da_familia_sem_perguntar():
    entradas = _categorias([
        ("2026-03-05", "CREDITO SALARIO METALURGICA ALFA LTDA", 4000.0),
        ("2026-03-20", "PIX RECEBIDO PAULO VIEIRA", 500.0),
    ])
    assert entradas.loc["T1", "categoria_renda"] == "renda_eventual"
    assert not entradas["perguntar_usuario"].any()  # o sistema nunca pergunta sobre ganhos


def test_entrada_recorrente_desconhecida_conta_como_renda_sem_perguntar_e_sem_falar_de_imposto():
    linhas = [(f"{mes}-05", "CREDITO SALARIO METALURGICA ALFA LTDA", 4000.0) for mes in MESES]
    linhas += [(f"{mes}-15", "PIX RECEBIDO LUANA ROCHA", 400.0 + i) for i, mes in enumerate(MESES[:4])]
    entradas = _categorias(linhas)
    desconhecidas = entradas[entradas["contraparte"] == "LUANA ROCHA"]
    assert (desconhecidas["categoria_renda"] == "renda_variavel").all()
    assert not desconhecidas["perguntar_usuario"].any()
    explicacao = desconhecidas["explicacao_renda"].iloc[0].lower()
    for palavra in ("fiscal", "imposto", "sonega", "irregular", "ilegal", "fraude"):
        assert palavra not in explicacao


def test_autonomo_com_cliente_pessoa():
    linhas = []
    for i, mes in enumerate(MESES):
        linhas.append((f"{mes}-03", "PIX RECEBIDO AGENCIA CRIATIVA ME", 1000.0 + 300 * i))
        linhas.append((f"{mes}-12", "PIX RECEBIDO STUDIO DESIGN LTDA", 800.0 + 500 * (i % 2)))
        linhas.append((f"{mes}-20", "PIX RECEBIDO MARIA LIMA", 300.0 * (i + 1)))  # valores bem diferentes
    entradas = _categorias(linhas)
    maria = entradas[entradas["contraparte"] == "MARIA LIMA"]
    assert (maria["categoria_renda"] == "renda_variavel").all()
    assert not maria["perguntar_usuario"].any()  # cliente: conta como renda, sem perguntar


def test_perfil_renda_fixa_usa_a_media_e_ignora_ajuda():
    linhas = [(f"{mes}-05", "CREDITO SALARIO METALURGICA ALFA LTDA", 3000.0) for mes in MESES]
    linhas.append(("2026-02-10", "PIX RECEBIDO PAULO VIEIRA", 1000.0))
    classificado, usuarios = _tabela(linhas)
    perfil = perfil_de_renda(classificar_entradas(classificado, usuarios), MESES).iloc[0]
    assert perfil["tipo_renda"] == "fixa"
    assert perfil["media"] == 3000.0
    assert perfil["renda_referencia"] == 3000.0
    assert perfil["eventual_total"] == 1000.0


def test_perfil_autonomo_usa_o_menor_mes():
    # Exemplo da proposta: R$ 2.000, R$ 4.000, R$ 1.500... com 3 clientes
    totais = [2000.0, 4000.0, 1500.0, 3000.0, 3500.0, 2500.0]
    linhas = []
    for mes, total in zip(MESES, totais):
        for cliente in ("AGENCIA CRIATIVA ME", "STUDIO DESIGN LTDA", "CONSTRUTORA HORIZONTE"):
            linhas.append((f"{mes}-10", f"PIX RECEBIDO {cliente}", total / 3))
    classificado, usuarios = _tabela(linhas)
    perfil = perfil_de_renda(classificar_entradas(classificado, usuarios), MESES).iloc[0]
    assert perfil["tipo_renda"] == "autonoma"
    assert perfil["minima"] == pytest.approx(1500.0)
    assert perfil["renda_referencia"] == pytest.approx(1500.0)
    assert perfil["variacao"] > 0.2


@pytest.fixture(scope="module")
def resultado_gerado():
    dados = gerar_dados()
    classificado = classificar_por_regras(normalizar(dados["extrato"]), dados["usuarios"])
    entradas = classificar_entradas(classificado, dados["usuarios"])
    perfis = perfil_de_renda(entradas, sorted(classificado["mes"].unique()))
    return entradas, perfis.merge(dados["usuarios_verdade"], on="id_usuario", suffixes=("", "_real"))


def test_toda_entrada_tem_explicacao(resultado_gerado):
    entradas, _ = resultado_gerado
    assert (entradas["explicacao_renda"].str.len() > 0).all()


def test_perfis_de_renda_fixa_sao_reconhecidos(resultado_gerado):
    _, perfis = resultado_gerado
    fixos = perfis[perfis["perfil"] != "renda_variavel_autonomo"]
    assert (fixos["tipo_renda"] == "fixa").all()


def test_autonomos_usam_o_menor_mes_para_planejar(resultado_gerado):
    _, perfis = resultado_gerado
    autonomos = perfis[perfis["perfil"] == "renda_variavel_autonomo"]
    assert autonomos["tipo_renda"].isin(["autonoma", "variavel"]).all()
    assert (autonomos["renda_referencia"] == autonomos["minima"]).all()


def test_explicacoes_de_perfil_sao_neutras(resultado_gerado):
    _, perfis = resultado_gerado
    texto = " ".join(perfis["explicacao"]).lower()
    for palavra in ("gastador", "irresponsável", "sonega", "irregular"):
        assert palavra not in texto


def test_salario_sem_a_palavra_salario():
    linhas = [(f"{mes}-05", "TED RECEBIDA COMERCIAL BETA S.A.", 3000.0 + i * 10) for i, mes in enumerate(MESES)]
    entradas = _categorias(linhas)
    assert (entradas["categoria_renda"] == "renda_fixa").all()
    assert not entradas["perguntar_usuario"].any()
    assert "salário" in entradas["explicacao_renda"].iloc[0]


def test_empresa_que_paga_varias_vezes_por_mes_nao_e_salario():
    linhas = []
    for mes in MESES:
        linhas.append((f"{mes}-05", "PIX RECEBIDO STUDIO DESIGN LTDA", 1000.0))
        linhas.append((f"{mes}-20", "PIX RECEBIDO STUDIO DESIGN LTDA", 1000.0))
    entradas = _categorias(linhas)
    assert (entradas["categoria_renda"] == "renda_variavel").all()


def _troca_de_emprego():
    """Cenário do maestro: salário, salário, mês só com PIX, salário de outra empresa."""
    linhas = [
        ("2026-01-05", "CREDITO SALARIO METALURGICA ALFA LTDA", 3000.0),
        ("2026-02-05", "CREDITO SALARIO METALURGICA ALFA LTDA", 3000.0),
        ("2026-03-12", "PIX RECEBIDO EVENTOS E FESTAS ALEGRIA", 400.0),
        ("2026-03-20", "PIX RECEBIDO STUDIO DESIGN LTDA", 250.0),
        ("2026-03-25", "PIX RECEBIDO CONSTRUTORA HORIZONTE", 300.0),
    ]
    linhas += [(f"{mes}-07", "TED RECEBIDA HOSPITAL SAO LUCAS LTDA", 3400.0) for mes in MESES[3:]]
    classificado, usuarios = _tabela(linhas)
    return perfil_de_renda(classificar_entradas(classificado, usuarios), MESES).iloc[0]


def test_troca_de_emprego_nao_vira_autonomo():
    perfil = _troca_de_emprego()
    assert perfil["tipo_renda"] == "fixa"
    assert perfil["troca_emprego"]
    assert perfil["empresa_anterior"] == "METALURGICA ALFA LTDA"
    assert perfil["empresa_atual"] == "HOSPITAL SAO LUCAS LTDA"
    assert perfil["meses_sem_salario"] == ["2026-03"]


def test_troca_de_emprego_planeja_pelo_salario_atual():
    perfil = _troca_de_emprego()
    assert perfil["renda_referencia"] == pytest.approx(3400.0)
    assert "troca de emprego" in perfil["explicacao"]


def test_dois_empregos_ao_mesmo_tempo_nao_e_troca():
    linhas = [(f"{mes}-05", "CREDITO SALARIO METALURGICA ALFA LTDA", 3000.0) for mes in MESES]
    linhas += [(f"{mes}-15", "TED RECEBIDA HOSPITAL SAO LUCAS LTDA", 1500.0) for mes in MESES]
    classificado, usuarios = _tabela(linhas)
    perfil = perfil_de_renda(classificar_entradas(classificado, usuarios), MESES).iloc[0]
    assert not perfil["troca_emprego"]
    assert perfil["tipo_renda"] == "fixa"
    assert perfil["media"] == pytest.approx(4500.0)


def test_trocas_de_emprego_detectadas_no_conjunto_gerado(resultado_gerado):
    _, perfis = resultado_gerado
    assert perfis["troca_emprego_real"].sum() == 3
    assert (perfis["troca_emprego"] == perfis["troca_emprego_real"]).all()


# ---------- 25/11/2026: ganhos sem pergunta e mudanças no salário ----------

def _perfil(linhas, nome_usuario="ANA VIEIRA"):
    classificado, usuarios = _tabela(linhas, nome_usuario)
    return perfil_de_renda(classificar_entradas(classificado, usuarios), MESES).iloc[0]


def test_nenhuma_entrada_vira_pergunta():
    linhas = [
        ("2026-01-05", "PIX RECEBIDO JOAO SOUZA", 80.0),
        ("2026-01-06", "CREDITO MAQUININHA STONE VENDAS", 250.0),
        ("2026-01-07", "DEPOSITO EM DINHEIRO", 300.0),
        ("2026-01-08", "PIX RECEBIDO MARIA LIMA", 45.0),
    ]
    entradas = _categorias(linhas)
    assert not entradas["perguntar_usuario"].any()
    assert (entradas["categoria_renda"] == "renda_variavel").all()


@pytest.mark.parametrize("descricao", [
    "CREDITO EMPRESTIMO PESSOAL BANCO X",
    "PIX RECEBIDO - ADIANTAMENTO FAMILIAR (IRMAO)",
    "PIX RECEBIDO AJUDA DA TIA",
])
def test_excecoes_reconhecidas_sozinhas_nao_sao_renda_do_trabalho(descricao):
    entradas = _categorias([("2026-01-10", descricao, 900.0)])
    assert entradas.loc["T0", "categoria_renda"] == "renda_eventual"
    assert not entradas.loc["T0", "perguntar_usuario"]


def test_salario_que_parou_mostra_periodo_sem_emprego_e_planeja_pelo_menor_mes():
    # Salário de janeiro a abril; em maio e junho só PIX de clientes
    linhas = [(f"{mes}-05", "CREDITO SALARIO METALURGICA ALFA LTDA", 3000.0) for mes in MESES[:4]]
    linhas += [("2026-05-10", "PIX RECEBIDO JOAO SOUZA", 900.0), ("2026-06-10", "PIX RECEBIDO JOAO SOUZA", 1200.0)]
    perfil = _perfil(linhas)
    assert perfil["situacao_salario"] == "parou"
    assert perfil["tipo_renda"] == "variavel"
    assert perfil["renda_referencia"] == 900.0
    assert "período sem emprego fixo" in perfil["explicacao"]
    assert "abril" in perfil["explicacao"]


def test_salario_que_comecou_depois_de_meses_so_com_pix():
    linhas = [("2026-01-10", "PIX RECEBIDO JOAO SOUZA", 700.0), ("2026-02-10", "PIX RECEBIDO MARIA LIMA", 600.0)]
    linhas += [(f"{mes}-05", "CREDITO SALARIO METALURGICA ALFA LTDA", 3000.0) for mes in MESES[2:]]
    perfil = _perfil(linhas)
    assert perfil["situacao_salario"] == "comecou"
    assert perfil["tipo_renda"] == "fixa"
    assert perfil["renda_referencia"] == 3000.0
    assert "Renda fixa desde março" in perfil["explicacao"]


def test_salario_fixo_com_extras_planeja_so_pelo_salario():
    linhas = [(f"{mes}-05", "CREDITO SALARIO METALURGICA ALFA LTDA", 3000.0) for mes in MESES]
    linhas += [(f"{mes}-20", "PIX RECEBIDO JOAO SOUZA", 200.0 * (i + 1)) for i, mes in enumerate(MESES)]
    perfil = _perfil(linhas)
    assert perfil["tipo_renda"] == "fixa"  # os extras variam, mas o salário não
    assert perfil["renda_referencia"] == 3000.0
    assert perfil["extra_por_mes"] == pytest.approx(700.0)
    assert "fora do planejamento" in perfil["explicacao"]


def test_sobrenome_so_conta_quando_quem_mandou_parece_uma_pessoa():
    # Usuário "CARLOS BAR": um depósito do caixa do bar termina com "BAR", mas não é parente
    entradas = _categorias([
        ("2026-01-10", "DEPOSITO EM DINHEIRO - CAIXA BAR", 400.0),
        ("2026-01-11", "PIX RECEBIDO MARIA BAR", 300.0),
    ], nome_usuario="CARLOS BAR")
    assert entradas.loc["T0", "categoria_renda"] == "renda_variavel"
    assert entradas.loc["T1", "categoria_renda"] == "renda_eventual"


def test_um_mes_so_nao_mostra_variacao_invalida():
    classificado, usuarios = _tabela([("2026-06-05", "PIX RECEBIDO JOAO SOUZA", 500.0), ("2026-06-10", "PIX RECEBIDO MARIA LIMA", 300.0)])
    perfil = perfil_de_renda(classificar_entradas(classificado, usuarios), ["2026-06"]).iloc[0]
    assert perfil["variacao"] == 0.0
    assert "nan" not in perfil["explicacao"].lower()
