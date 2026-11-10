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

# Nome de cada categoria para mostrar ao usuário (com acentos)
NOMES_EXIBICAO = {
    "moradia": "Moradia", "energia": "Energia", "agua": "Água", "alimentacao_basica": "Alimentação básica",
    "transporte": "Transporte", "telecom": "Telefone e internet", "educacao": "Educação", "saude": "Saúde",
    "pagamento_dividas": "Pagamento de dívidas", "restaurantes_bares": "Restaurantes e bares", "lazer": "Lazer",
    "jogos": "Jogos", "compras": "Compras", "assinaturas": "Assinaturas",
    "transferencia_interna": "Transferência entre suas contas", "renda_fixa": "Renda fixa",
    "renda_variavel": "Renda variável", "renda_eventual": "Renda eventual",
    "renda_nao_identificada": "Renda não identificada", "pagamento_fatura": "Pagamento de fatura",
    "nao_identificado": "A confirmar",
}


def nome_exibicao(categoria):
    return NOMES_EXIBICAO.get(categoria, categoria.replace("_", " ").capitalize())
