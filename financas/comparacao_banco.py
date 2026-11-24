"""Comparação com a categoria que o próprio banco coloca no extrato.

A categoria do banco NUNCA é usada para classificar: o SIDOF classifica sozinho e só depois compara.
É uma checagem externa: "o SIDOF concordou com o banco em X% das saídas".
Cada banco usa nomes próprios; o mapa abaixo traduz os nomes mais comuns para as categorias do SIDOF.
Categorias do banco sem equivalente (ex.: "Serviços domésticos") ficam fora da conta.
"""

import pandas as pd

from financas.categorias import nome_exibicao
from financas.normalizacao import normalizar_texto

# Nome da categoria no banco -> categorias do SIDOF que contam como concordância
MAPA_DO_BANCO = {
    "TRANSPORTE": {"transporte", "veiculos"}, "MOBILIDADE": {"transporte", "veiculos"},
    "COMBUSTIVEL": {"veiculos"}, "VEICULO": {"veiculos"}, "VEICULOS": {"veiculos"}, "AUTOMOVEL": {"veiculos"},
    "CARRO": {"veiculos"}, "AUTO": {"veiculos"},
    "MERCADO": {"alimentacao_basica"}, "SUPERMERCADO": {"alimentacao_basica"},
    "ALIMENTACAO FORA": {"restaurantes_bares"}, "RESTAURANTES": {"restaurantes_bares"}, "RESTAURANTE": {"restaurantes_bares"},
    "BARES E RESTAURANTES": {"restaurantes_bares"}, "DELIVERY": {"restaurantes_bares"},
    "ALIMENTACAO": {"alimentacao_basica", "restaurantes_bares"},
    "ASSINATURAS": {"assinaturas"}, "SERVICOS DIGITAIS": {"assinaturas"}, "STREAMING": {"assinaturas"},
    "MORADIA": {"moradia"}, "CASA": {"moradia"}, "ALUGUEL": {"moradia"},
    "CONTAS DE CONSUMO": {"energia", "agua", "telecom"}, "CONTAS": {"energia", "agua", "telecom"},
    "ENERGIA": {"energia"}, "AGUA": {"agua"}, "TELEFONE": {"telecom"}, "INTERNET": {"telecom"},
    "SAUDE": {"saude"}, "FARMACIA": {"saude"},
    "EDUCACAO": {"educacao"},
    "COMPRAS": {"compras"}, "VESTUARIO": {"compras"},
    "LAZER": {"lazer"}, "ENTRETENIMENTO": {"lazer"}, "VIAGEM": {"lazer"}, "JOGOS": {"jogos"},
    "INVESTIMENTO": {"guardar_investir"}, "INVESTIMENTOS": {"guardar_investir"}, "POUPANCA": {"guardar_investir"},
    "APLICACAO": {"guardar_investir"},
    "TRANSFERENCIA ENTRE CONTAS": {"transferencia_interna"},
    "EMPRESTIMO": {"pagamento_dividas"}, "DIVIDAS": {"pagamento_dividas"},
    "CARTAO DE CREDITO": {"pagamento_fatura"}, "FATURA": {"pagamento_fatura"},
    "SAQUE": {"saque"},
    "FAMILIA": {"transferencia_familiar"},
    # "Impostos" no banco é amplo: IPTU é moradia, IPVA é veículo, o resto é imposto/contribuição
    "IMPOSTOS": {"impostos_contribuicoes", "veiculos", "moradia"}, "TRIBUTOS": {"impostos_contribuicoes", "veiculos", "moradia"},
    "TARIFAS": {"tarifas_bancarias"}, "TARIFAS BANCARIAS": {"tarifas_bancarias"}, "ENCARGOS": {"tarifas_bancarias"},
    "JUROS": {"tarifas_bancarias"},
}
PENDENTE = "nao_identificado"


def comparar_com_banco(saidas):
    """Compara a categoria final do SIDOF com a do banco nas saídas que têm categoria do banco.

    Devolve None se o documento não traz categoria. Senão, um dicionário com:
    comparaveis, concordam, taxa, pendentes (o SIDOF ainda vai perguntar), sem_equivalente,
    por_categoria (tabela) e discordancias (exemplos).
    """
    if "categoria_banco" not in saidas or not (saidas["categoria_banco"].fillna("") != "").any():
        return None
    com_banco = saidas[saidas["categoria_banco"].fillna("") != ""].copy()
    com_banco["chave_banco"] = com_banco["categoria_banco"].map(normalizar_texto)
    com_banco["esperadas"] = com_banco["chave_banco"].map(MAPA_DO_BANCO)
    sem_equivalente = com_banco[com_banco["esperadas"].isna()]
    mapeadas = com_banco[com_banco["esperadas"].notna()]
    pendentes = mapeadas[mapeadas["categoria_final"] == PENDENTE]
    comparaveis = mapeadas[mapeadas["categoria_final"] != PENDENTE].copy()
    comparaveis["concorda"] = [final in esperadas for final, esperadas in zip(comparaveis["categoria_final"], comparaveis["esperadas"])]

    por_categoria = comparaveis.groupby("categoria_banco").agg(
        transacoes=("concorda", "size"), concordam=("concorda", "sum")
    ).reset_index()
    por_categoria["taxa"] = por_categoria["concordam"] / por_categoria["transacoes"]
    discordancias = comparaveis[~comparaveis["concorda"]].assign(
        sidof=lambda t: t["categoria_final"].map(nome_exibicao)
    )[["descricao", "categoria_banco", "sidof"]].drop_duplicates("descricao")

    concordam = int(comparaveis["concorda"].sum())
    return {
        "comparaveis": len(comparaveis),
        "concordam": concordam,
        "taxa": concordam / len(comparaveis) if len(comparaveis) else 0.0,
        "pendentes": len(pendentes),
        "sem_equivalente": len(sem_equivalente),
        "categorias_sem_equivalente": sorted(sem_equivalente["categoria_banco"].unique()),
        "por_categoria": por_categoria.sort_values("transacoes", ascending=False, ignore_index=True),
        "discordancias": discordancias.reset_index(drop=True),
    }
