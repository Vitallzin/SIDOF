"""Classificação por regras (Fase 2).

Cada regra procura uma palavra-chave na descrição e devolve uma categoria,
um nível de confiança e uma explicação curta. A primeira regra que combinar vence.
Quando nenhuma regra combina, a transação fica "não identificada" e o usuário é consultado.

As palavras-chave são genéricas (ex.: SUPERMERCADO, FARMACIA), do tipo que
funcionaria em extratos reais, e não nomes exatos das lojas do gerador.
"""

import re
from dataclasses import dataclass

import pandas as pd

from financas.normalizacao import normalizar_texto

# Abaixo desta confiança o sistema pergunta ao usuário (decisão do plano, ajustável)
CONFIANCA_MINIMA = 0.70


@dataclass(frozen=True)
class Regra:
    nome: str
    palavras: tuple  # basta uma delas aparecer como palavra inteira
    categoria: str
    confianca: float
    direcao: str = "saida"  # "saida", "entrada" ou "qualquer"

    def procurar(self, descricao):
        """Devolve a palavra encontrada na descrição, ou None."""
        for palavra in self.palavras:
            if re.search(rf"\b{re.escape(palavra)}\b", descricao):
                return palavra
        return None


# Regras que indicam dinheiro do próprio usuário mudando de lugar (não é gasto nem renda)
REGRAS_INTERNAS = ("transferencia_propria", "pix_proprio_nome", "aplicacao_propria")

# Ordem importa: regras mais específicas primeiro.
REGRAS = [
    # Movimentações que não são gasto nem renda
    Regra("fatura_cartao", ("FATURA CARTAO", "PAGAMENTO FATURA", "PAGTO FATURA", "PAG FATURA", "FATURA DO CARTAO"), "pagamento_fatura", 0.99),
    Regra("transferencia_propria", ("TRANSF ENTRE CONTAS PROPRIAS",), "transferencia_interna", 0.99, "qualquer"),
    Regra("salario", ("SALARIO",), "renda_fixa", 0.95, "entrada"),
    # Entradas que não são renda do trabalho (rendimento vem antes de "poupança")
    Regra("rendimento", ("RENDIMENTO", "RENDIMENTOS"), "renda_eventual", 0.90, "entrada"),
    Regra("reembolso", ("REEMBOLSO", "ESTORNO", "DEVOLUCAO"), "renda_eventual", 0.85, "entrada"),
    # Dinheiro guardado: aplicação e resgate de investimento/poupança do próprio usuário
    Regra("aplicacao_propria", ("APLICACAO", "RESGATE", "POUPANCA"), "guardar_investir", 0.90, "qualquer"),
    Regra("saque", ("SAQUE",), "saque", 0.95),
    # Impostos: cada um vai para onde pertence (IPTU é moradia, IPVA é veículo); o resto é imposto/contribuição
    Regra("iptu", ("IPTU", "TAXA DE LIXO", "TAXA LIXO"), "moradia", 0.95),
    Regra("documentos_veiculo", ("IPVA", "LICENCIAMENTO", "DETRAN", "MULTA TRANSITO", "MULTA DE TRANSITO"), "veiculos", 0.95),
    Regra("impostos", (
        "DARF", "DAS MEI", "DAS SIMPLES", "SIMPLES NACIONAL", "IMPOSTO DE RENDA", "IRPF", "INSS", "RECEITA FEDERAL",
        "ITBI", "ITCMD",
    ), "impostos_contribuicoes", 0.90),
    Regra("tarifas", (
        "TARIFA", "IOF", "JUROS", "ENCARGOS", "CESTA DE SERVICOS", "PACOTE SERVICOS", "ANUIDADE", "CHEQUE ESPECIAL",
    ), "tarifas_bancarias", 0.90),
    Regra("mesada", ("MESADA",), "transferencia_familiar", 0.85),
    # Essenciais
    Regra("aluguel", ("IMOBILIARIA", "ALUGUEL", "CONDOMINIO"), "moradia", 0.95),
    Regra("energia", ("ENERGIA ELETRICA", "ENERGIA"), "energia", 0.95),
    Regra("agua", ("SANEAMENTO", "AGUAS", "AGUA"), "agua", 0.90),
    Regra("telecom", ("TELECOM", "OPERADORA", "INTERNET", "TELEFONIA"), "telecom", 0.90),
    Regra("mercado", ("SUPERMERCADO", "MERCADINHO", "MERCADO", "ATACADAO", "HORTIFRUTI", "PADARIA", "ACOUGUE"), "alimentacao_basica", 0.90),
    # Veículo próprio (combustível, manutenção, seguro); kit de limpeza e acessórios ficam em compras
    Regra("veiculos", (
        "COMBUSTIVEL", "POSTO", "AUTOPOSTO", "ESTACIONAMENTO", "PEDAGIO", "OFICINA", "MECANICA", "AUTOPECAS",
        "AUTO PECAS", "PNEUS", "BORRACHARIA", "SEGURO AUTO", "LAVA JATO",
    ), "veiculos", 0.85),
    # Transporte: ônibus, metrô, trem e corridas por aplicativo
    Regra("transporte", ("CORRIDA", "BILHETE", "METRO", "ONIBUS", "UBER"), "transporte", 0.85),
    # Prioritários
    Regra("dividas", ("EMPRESTIMO", "FINANCIAMENTO", "RENEGOCIACAO", "ACORDO"), "pagamento_dividas", 0.95),
    Regra("plano_saude", ("PLANO SAUDE",), "saude", 0.95),
    Regra("saude", ("DROGARIA", "FARMACIA", "CLINICA", "ODONTO"), "saude", 0.85),
    Regra("educacao", ("FACULDADE", "ESCOLA", "IDIOMAS", "CURSO"), "educacao", 0.85),
    # Discricionários
    Regra("restaurantes", ("RESTAURANTE", "PIZZARIA", "LANCHONETE", "HAMBURGUERIA", "BAR", "ENTREGA COMIDA"), "restaurantes_bares", 0.85),
    Regra("jogos", ("JOGOS", "GAME"), "jogos", 0.85),
    Regra("assinaturas", ("STREAMING", "ASSINATURA", "ACADEMIA", "PREMIUM"), "assinaturas", 0.80),
    Regra("lazer", ("CINEMA", "INGRESSOS", "TEATRO", "SHOW", "PARQUE", "VIAGENS"), "lazer", 0.80),
    Regra("compras", ("MAGAZINE", "MOVEIS", "CELULARES", "CALCADOS", "PAPELARIA", "MKTPLACE", "UTILIDADES", "LOJA"), "compras", 0.75),
]

# Indícios de que a contraparte é uma empresa e não uma pessoa
MARCAS_DE_EMPRESA = ("LTDA", "ME", "SA", "EIRELI", "CIA", "SERVICOS")


def parece_pessoa(contraparte):
    """Duas ou três palavras só com letras e sem indício de empresa, ex.: 'MARIA SOUZA'.

    Nomes de pessoa não têm '*' (prefixo de maquininha) nem números (código do terminal).
    """
    palavras = contraparte.split()
    return (
        2 <= len(palavras) <= 3
        and all(palavra.isalpha() for palavra in palavras)
        and not any(palavra in MARCAS_DE_EMPRESA for palavra in palavras)
    )


def _nome_categoria(categoria):
    return categoria.replace("_", " ")


def classificar_linha(linha, nome_usuario):
    """Classifica uma transação normalizada. Devolve categoria, confiança, regra e explicação."""
    eh_pix = linha["operacao"] in ("pix_enviado", "pix_recebido")

    if eh_pix and linha["contraparte"] == nome_usuario:
        return {
            "categoria_regra": "transferencia_interna",
            "confianca": 0.90,
            "regra": "pix_proprio_nome",
            "explicacao": "PIX com o próprio nome do usuário: transferência entre contas dele.",
        }

    for regra in REGRAS:
        if regra.direcao not in ("qualquer", linha["direcao"]):
            continue
        palavra = regra.procurar(linha["descricao"])
        if palavra:
            return {
                "categoria_regra": regra.categoria,
                "confianca": regra.confianca,
                "regra": regra.nome,
                "explicacao": f'A descrição contém "{palavra}", típico de {_nome_categoria(regra.categoria)}.',
            }

    if linha["direcao"] == "entrada":
        return {
            "categoria_regra": "renda_nao_identificada",
            "confianca": 0.0,
            "regra": "sem_regra",
            "explicacao": "Entrada sem origem conhecida: pode ser renda, ajuda ou outra coisa. Perguntar ao usuário.",
        }
    if eh_pix and parece_pessoa(linha["contraparte"]):
        explicacao = "PIX para uma pessoa: a finalidade não aparece no extrato. Perguntar ao usuário."
    else:
        explicacao = "Nenhuma regra reconheceu a descrição. Perguntar ao usuário."
    return {"categoria_regra": "nao_identificado", "confianca": 0.0, "regra": "sem_regra", "explicacao": explicacao}


def classificar_por_regras(extrato_normalizado, usuarios):
    """Aplica as regras a todas as transações e indica quais precisam de pergunta ao usuário."""
    nomes = usuarios.set_index("id_usuario")["nome"].map(normalizar_texto)
    resultados = [
        classificar_linha(linha, nomes.get(linha["id_usuario"], ""))
        for linha in extrato_normalizado.to_dict("records")
    ]
    tabela = pd.concat([extrato_normalizado.reset_index(drop=True), pd.DataFrame(resultados)], axis=1)
    tabela["perguntar_usuario"] = tabela["confianca"] < CONFIANCA_MINIMA
    tabela["mesmo_sobrenome"] = [
        _pix_para_parente(linha["operacao"], linha["contraparte"], nomes.get(linha["id_usuario"], ""))
        for linha in tabela[["operacao", "contraparte", "id_usuario"]].to_dict("records")
    ]
    return tabela


def _pix_para_parente(operacao, contraparte, nome_usuario):
    """PIX enviado para outra pessoa com o mesmo sobrenome do usuário: pista (não certeza) de família."""
    if operacao != "pix_enviado" or not nome_usuario or contraparte == nome_usuario or not parece_pessoa(contraparte):
        return False
    return contraparte.split()[-1] == nome_usuario.split()[-1]
