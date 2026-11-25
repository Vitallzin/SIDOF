"""Lista oficial de categorias e o grupo de cada uma.

Aprovada na Sessão 1 e ampliada por decisão do maestro em 24/11/2026: Veículos, Transferência familiar,
Guardar/investir, Saque em dinheiro, Impostos e contribuições, Tarifas e juros bancários.
Em 25/11/2026 "Jogos" entrou em "Lazer".
"""

GRUPOS = {
    "essencial": ["moradia", "energia", "agua", "alimentacao_basica", "transporte", "veiculos", "telecom"],
    "prioritario": [
        "educacao", "saude", "pagamento_dividas", "transferencia_familiar", "impostos_contribuicoes", "tarifas_bancarias",
    ],
    "discricionario": ["restaurantes_bares", "lazer", "compras", "assinaturas", "saque"],
    "outros": [
        "transferencia_interna",
        "guardar_investir",
        "renda_fixa",
        "renda_variavel",
        "renda_eventual",
        "renda_nao_identificada",
        "pagamento_fatura",
        "nao_identificado",
    ],
}

# Categorias que deixaram de existir -> onde estão agora (votos antigos do aprendizado coletivo continuam valendo)
CATEGORIAS_ANTIGAS = {"jogos": "lazer"}  # 25/11/2026: jogos entrou em lazer (decisão do maestro)

# categoria -> grupo, por exemplo "energia" -> "essencial"
CATEGORIAS = {categoria: grupo for grupo, lista in GRUPOS.items() for categoria in lista}

# Categorias que representam dinheiro entrando como renda.
CATEGORIAS_DE_RENDA = ["renda_fixa", "renda_variavel", "renda_eventual", "renda_nao_identificada"]

# Dinheiro do próprio usuário mudando de lugar: não é gasto (a reserva soma o que foi guardado)
CATEGORIAS_FORA_DOS_GASTOS = ("transferencia_interna", "guardar_investir", "pagamento_fatura")

# Nome de cada categoria para mostrar ao usuário (com acentos)
NOMES_EXIBICAO = {
    "moradia": "Moradia", "energia": "Energia", "agua": "Água", "alimentacao_basica": "Alimentação básica",
    "transporte": "Transporte", "veiculos": "Veículos", "telecom": "Telefone e internet", "educacao": "Educação",
    "saude": "Saúde", "pagamento_dividas": "Pagamento de dívidas", "transferencia_familiar": "Transferência familiar",
    "impostos_contribuicoes": "Impostos e contribuições", "tarifas_bancarias": "Tarifas e juros bancários",
    "restaurantes_bares": "Restaurantes e bares", "lazer": "Lazer (inclui jogos)", "compras": "Compras",
    "assinaturas": "Assinaturas", "saque": "Saque em dinheiro",
    "transferencia_interna": "Transferência entre suas contas", "guardar_investir": "Guardar/investir",
    "renda_fixa": "Renda fixa", "renda_variavel": "Renda variável", "renda_eventual": "Renda eventual",
    "renda_nao_identificada": "Renda não identificada", "pagamento_fatura": "Pagamento de fatura",
    "nao_identificado": "A confirmar",
}


def nome_exibicao(categoria):
    return NOMES_EXIBICAO.get(categoria, categoria.replace("_", " ").capitalize())
