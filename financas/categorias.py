"""Lista oficial de categorias e o grupo de cada uma (aprovada na Sessão 1)."""

GRUPOS = {
    "essencial": ["moradia", "energia", "agua", "alimentacao_basica", "transporte", "telecom"],
    "prioritario": ["educacao", "saude", "pagamento_dividas"],
    "discricionario": ["restaurantes_bares", "lazer", "jogos", "compras", "assinaturas"],
    "outros": [
        "transferencia_interna",
        "renda_fixa",
        "renda_variavel",
        "renda_eventual",
        "renda_nao_identificada",
        "pagamento_fatura",
        "nao_identificado",
    ],
}

# categoria -> grupo, por exemplo "energia" -> "essencial"
CATEGORIAS = {categoria: grupo for grupo, lista in GRUPOS.items() for categoria in lista}

# Categorias que representam dinheiro entrando como renda.
CATEGORIAS_DE_RENDA = ["renda_fixa", "renda_variavel", "renda_eventual", "renda_nao_identificada"]
