"""Gerador de dados sintéticos (Fase 1).

Cria extratos fictícios de 12 usuários (3 por perfil), de janeiro a junho de 2026.

Arquivos gerados:
- extrato.csv: o que o sistema vê, como num extrato de banco
- usuarios.csv: nome de cada usuário (o banco conhece o nome do cliente)
- verdade.csv: categoria real de cada transação e anomalias plantadas (SÓ para avaliação)
- usuarios_verdade.csv: perfil real de cada usuário (SÓ para avaliação)
"""

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from financas import SEMENTE
from financas import catalogo as cat
from financas.categorias import CATEGORIAS

ANO = 2026
MESES = [1, 2, 3, 4, 5, 6]
USUARIOS_POR_PERFIL = 3
# As anomalias só entram nos últimos meses, para existir histórico antes delas.
MESES_COM_ANOMALIA = [4, 5, 6]
# Tipos NÃO previstos: nenhum detector foi pensado para eles (ver docs/03_decisoes_anomalias.md).
# Servem para medir se os métodos encontram anomalias que ninguém antecipou.
TIPOS_NAO_PREVISTOS = [
    "conta_fixa_disparada",
    "pix_alto_desconhecido",
    "cobranca_recorrente_nova",
]
TIPOS_ANOMALIA = [
    "pico_categoria",
    "cobranca_duplicada",
    "estabelecimento_novo_alto",
    "frequencia_incomum",
]

PASTA_PADRAO = Path(__file__).resolve().parent.parent / "dados_gerados"

COLUNAS_EXTRATO = ["id_transacao", "id_usuario", "data", "descricao", "valor", "meio", "conta", "parcela"]
# loja: nome original da loja/empresa (vazio quando não há loja, ex.: PIX para pessoa)
COLUNAS_VERDADE = ["id_transacao", "categoria", "grupo", "ambigua", "tipo_anomalia", "loja"]

# Características de cada perfil.
# escala: multiplica os valores do dia a dia (quem ganha menos gasta valores menores)
PERFIS = {
    "renda_fixa_poucos_compromissos": {
        "tipo_renda": "fixa", "renda": (5500, 7500), "escala": 1.1, "aluguel": (1100, 1600),
        "parcelamentos": (0, 1), "dividas": (0, 0),
        "chance_poupanca": 1.0, "poupanca": (400, 900),
        "chance_ajuda_familia": 0.2, "chance_educacao": 0.4, "chance_plano_saude": 0.7,
        "chance_carro": 0.8, "chance_envio_familia": 0.3, "chance_aplicacao": 0.9, "chance_iptu": 0.6,
        "chance_tarifa": 0.4, "chance_saque": 0.4, "chance_darf": 0.5,
        "sobra_alvo": (0.25, 0.40),
    },
    "renda_variavel_autonomo": {
        "tipo_renda": "variavel", "renda": (3200, 5000), "escala": 0.9, "aluguel": (900, 1300),
        "parcelamentos": (0, 2), "dividas": (0, 0),
        "chance_poupanca": 0.5, "poupanca": (200, 700),
        "chance_ajuda_familia": 0.4, "chance_educacao": 0.3, "chance_plano_saude": 0.3,
        "chance_carro": 0.6, "chance_envio_familia": 0.3, "chance_aplicacao": 0.5, "chance_iptu": 0.3,
        "chance_tarifa": 0.6, "chance_saque": 0.6, "chance_darf": 0.0,
        "sobra_alvo": (0.08, 0.22),
    },
    "renda_fixa_com_dividas": {
        "tipo_renda": "fixa", "renda": (3800, 5000), "escala": 0.8, "aluguel": (900, 1300),
        "parcelamentos": (4, 6), "dividas": (2, 2),
        "chance_poupanca": 0.15, "poupanca": (100, 300),
        "chance_ajuda_familia": 0.3, "chance_educacao": 0.4, "chance_plano_saude": 0.3,
        "chance_carro": 0.6, "chance_envio_familia": 0.4, "chance_aplicacao": 0.0, "chance_iptu": 0.3,
        "chance_tarifa": 0.8, "chance_saque": 0.5, "chance_darf": 0.0,
        "sobra_alvo": (0.04, 0.12),
    },
    "renda_baixa_pouca_margem": {
        "tipo_renda": "fixa", "renda": (1600, 2100), "escala": 0.5, "aluguel": (450, 700),
        "parcelamentos": (0, 1), "dividas": (0, 1),
        "chance_poupanca": 0.2, "poupanca": (50, 150),
        "chance_ajuda_familia": 0.7, "chance_educacao": 0.2, "chance_plano_saude": 0.0,
        "chance_carro": 0.2, "chance_envio_familia": 0.5, "chance_aplicacao": 0.0, "chance_iptu": 0.0,
        "chance_tarifa": 0.6, "chance_saque": 0.8, "chance_darf": 0.0,
        "sobra_alvo": (0.06, 0.12),
    },
}

# Limites do ajuste ao orçamento: os gastos do dia a dia nunca ficam menores que 40%
# nem maiores que 250% do que foi sorteado, para continuarem plausíveis
FATOR_MINIMO, FATOR_MAXIMO = 0.4, 2.5

# Quantas compras por mês em cada categoria do dia a dia (antes do hábito pessoal)
FREQUENCIA_MENSAL = {
    "alimentacao_basica": (4, 7),
    "transporte": (2, 6),
    "veiculos": (2, 5),  # só para quem tem carro
    "saude": (0, 2),
    "restaurantes_bares": (2, 6),
    "lazer": (0, 2),
    "jogos": (0, 2),
    "compras": (1, 3),
}

# Formas de pagamento possíveis em cada categoria do dia a dia
MEIOS = {
    "alimentacao_basica": ["cartao_debito", "pix", "cartao_credito", "pix"],
    "transporte": ["cartao_debito", "cartao_credito"],
    "veiculos": ["cartao_debito", "cartao_credito"],
    "saude": ["cartao_debito", "cartao_credito", "pix"],
    "restaurantes_bares": ["cartao_credito", "pix", "cartao_debito", "pix"],
    "lazer": ["cartao_credito"],
    "jogos": ["cartao_credito"],
    "compras": ["cartao_credito", "cartao_debito", "pix"],
}

# Como cada forma de pagamento aparece no texto do extrato
PREFIXOS = {
    "cartao_debito": "COMPRA DEBITO ",
    "cartao_credito": "",
    "pix": "PIX ENVIADO ",
    "boleto": "PAGTO BOLETO ",
}

# Ruído realista nas descrições: prefixos de maquininha, cidades e limite de caracteres
ADQUIRENTES = ["PGTO*", "MAQ*", "CRD*", "LV*", "PAGFACIL*"]
CIDADES = ["SAO PAULO", "RIO DE JANEIRO", "BELO HORIZONT", "CURITIBA", "SALVADOR", "RECIFE"]
LIMITE_CARACTERES = 22  # muitas maquininhas cortam o nome da loja nesse tamanho


# ---------- Funções auxiliares ----------

def _escolher(rng, lista):
    """Sorteia um item de uma lista."""
    return lista[int(rng.integers(len(lista)))]


def _uniforme(rng, minimo, maximo):
    return float(rng.uniform(minimo, maximo))


def _dia(rng):
    # Até o dia 28 para valer em todos os meses
    return int(rng.integers(1, 29))


def _data(mes, dia):
    return date(ANO, mes, dia)


def _nome_pessoa(rng, sobrenome=None):
    nome = _escolher(rng, cat.PRIMEIROS_NOMES)
    return f"{nome} {sobrenome or _escolher(rng, cat.SOBRENOMES)}"


def _abreviar(rng, texto):
    """Encurta palavras longas, como fazem os bancos. Ex.: 'SUPERMERCADO BOM PRECO' -> 'SUPERM BOM PREC'."""
    palavras = []
    for palavra in texto.split():
        if len(palavra) > 5 and rng.random() < 0.5:
            palavra = palavra[: int(rng.integers(3, 6))]
        palavras.append(palavra)
    return " ".join(palavras)


def _baguncar(rng, loja):
    """Mostra o nome da loja como aparece em extratos reais: abreviado, colado, cortado ou com cidade."""
    texto = loja
    if rng.random() < 0.35:
        texto = _abreviar(rng, texto)
    if rng.random() < 0.25:
        texto = _escolher(rng, ADQUIRENTES) + texto.replace(" ", "")
    if rng.random() < 0.4:
        texto = texto[:LIMITE_CARACTERES].strip()
    if rng.random() < 0.25:
        texto = f"{texto} {_escolher(rng, CIDADES)}"
    if rng.random() < 0.15:
        texto = f"{texto} {int(rng.integers(1000, 10000))}"
    return texto


def _abreviar_as_vezes(rng, empresa):
    """Boletos costumam trazer o nome completo; às vezes vêm abreviados."""
    return _abreviar(rng, empresa) if rng.random() < 0.3 else empresa


def _linha(data, descricao, valor, meio, categoria, conta="corrente", parcela="", ambigua=False, anomalia="", loja=""):
    """Monta uma transação. Valor negativo = saída, positivo = entrada."""
    return {
        "data": data,
        "descricao": descricao,
        "valor": round(float(valor), 2),
        "meio": meio,
        "conta": "cartao" if meio == "cartao_credito" else conta,
        "parcela": parcela,
        "categoria": categoria,
        "ambigua": ambigua,
        "tipo_anomalia": anomalia,
        "loja": loja,
    }


# ---------- Renda ----------

def _salario_mensal(rng, empresa, valor, meses):
    """Salário de um emprego: mesmo dia, mesmo formato e valor estável em cada mês."""
    formato, meio = _escolher(rng, cat.FORMATOS_SALARIO)
    dia = int(rng.integers(1, 8))
    return [
        _linha(_data(mes, dia), formato.format(empresa), valor * _uniforme(rng, 0.98, 1.02), meio, "renda_fixa")
        for mes in meses
    ]


def _bicos(rng, mes, renda_base):
    """Trabalhos avulsos no mês sem salário, pagos por empresas."""
    total = renda_base * _uniforme(rng, 0.2, 0.4)
    partes = rng.dirichlet(np.ones(int(rng.integers(1, 4)))) * total
    return [
        _linha(_data(mes, _dia(rng)), f"PIX RECEBIDO {_escolher(rng, cat.EMPRESAS_CLIENTES)}", parte, "pix", "renda_variavel")
        for parte in partes
    ]


def _salarios(rng, renda_base, troca_de_emprego):
    empresa = _escolher(rng, cat.EMPRESAS_EMPREGADORAS)
    if not troca_de_emprego:
        return _salario_mensal(rng, empresa, renda_base, MESES)
    # Troca de emprego: um mês sem salário (com bicos) e depois salário de outra empresa
    mes_sem_salario = int(rng.integers(3, 5))
    nova_empresa = _escolher(rng, [e for e in cat.EMPRESAS_EMPREGADORAS if e != empresa])
    novo_salario = renda_base * _uniforme(rng, 0.85, 1.2)
    linhas = _salario_mensal(rng, empresa, renda_base, [m for m in MESES if m < mes_sem_salario])
    linhas += _bicos(rng, mes_sem_salario, renda_base)
    linhas += _salario_mensal(rng, nova_empresa, novo_salario, [m for m in MESES if m > mes_sem_salario])
    return linhas


def _cliente(rng):
    """Cliente de um autônomo: pessoa (ambíguo no extrato) ou empresa."""
    if rng.random() < 0.3:
        return _nome_pessoa(rng), True
    return _escolher(rng, cat.EMPRESAS_CLIENTES), False


def _renda_autonomo(rng, renda_base):
    clientes = [_cliente(rng) for _ in range(int(rng.integers(4, 7)))]
    # Meses bons e ruins embaralhados, para garantir renda variável
    multiplicadores = rng.permutation([0.5, 0.7, 0.9, 1.1, 1.3, 1.5])
    linhas = []
    for mes, multiplicador in zip(MESES, multiplicadores):
        total = renda_base * multiplicador * _uniforme(rng, 0.9, 1.1)
        partes = rng.dirichlet(np.ones(int(rng.integers(2, 7)))) * total
        for parte in partes:
            nome, eh_pessoa = _escolher(rng, clientes)
            linhas.append(_linha(_data(mes, _dia(rng)), f"PIX RECEBIDO {nome}", parte, "pix", "renda_variavel", ambigua=eh_pessoa))
    return linhas


def _renda_eventual(rng, cfg, nome_usuario):
    """Ajuda da família: o parente tem o mesmo sobrenome do usuário (mas não o mesmo nome)."""
    if rng.random() >= cfg["chance_ajuda_familia"]:
        return []
    sobrenome = nome_usuario.split()[-1]
    parente = _nome_pessoa(rng, sobrenome)
    while parente == nome_usuario:
        parente = _nome_pessoa(rng, sobrenome)
    meses = sorted(int(m) for m in rng.choice(MESES, size=int(rng.integers(1, 3)), replace=False))
    return [
        _linha(_data(mes, _dia(rng)), f"PIX RECEBIDO {parente}", _uniforme(rng, 200, 1000) * cfg["escala"], "pix", "renda_eventual", ambigua=True)
        for mes in meses
    ]


def _renda_nao_identificada(rng):
    """Entradas repetidas de uma pessoa sem origem conhecida."""
    pessoa = _nome_pessoa(rng)
    valor_base = _uniforme(rng, 150, 600)
    meses = sorted(int(m) for m in rng.choice(MESES, size=int(rng.integers(3, 7)), replace=False))
    return [
        _linha(_data(mes, _dia(rng)), f"PIX RECEBIDO {pessoa}", valor_base * _uniforme(rng, 0.9, 1.1), "pix", "renda_nao_identificada", ambigua=True)
        for mes in meses
    ]


def _rendas(rng, usuario, cfg, tem_renda_desconhecida):
    troca_de_emprego = usuario["troca_emprego"]
    if cfg["tipo_renda"] == "fixa":
        linhas = _salarios(rng, usuario["renda_base"], troca_de_emprego)
    else:
        linhas = _renda_autonomo(rng, usuario["renda_base"])
    linhas += _renda_eventual(rng, cfg, usuario["nome"])
    if tem_renda_desconhecida:
        linhas += _renda_nao_identificada(rng)
    return linhas


# ---------- Contas fixas, dívidas e parcelamentos ----------

def _conta_mensal(rng, empresa, categoria, valor_base, variacao, meio="boleto"):
    """Conta que se repete todo mês no mesmo dia, com pequena variação de valor."""
    dia = _dia(rng)
    # O nome é sorteado uma vez: a mesma conta aparece igual todo mês
    nome = _baguncar(rng, empresa) if meio == "cartao_credito" else _abreviar_as_vezes(rng, empresa)
    descricao = PREFIXOS[meio] + nome
    return [
        _linha(_data(mes, dia), descricao, -valor_base * _uniforme(rng, 1 - variacao, 1 + variacao), meio, categoria, loja=empresa)
        for mes in MESES
    ]


def _aluguel(rng, cfg):
    """Metade paga por boleto da imobiliária; metade por PIX ao proprietário (ambíguo)."""
    valor = _uniforme(rng, *cfg["aluguel"])
    if rng.random() < 0.5:
        return _conta_mensal(rng, _escolher(rng, cat.IMOBILIARIAS), "moradia", valor, 0)
    proprietario = _nome_pessoa(rng)
    dia = int(rng.integers(1, 11))
    return [
        _linha(_data(mes, dia), f"PIX ENVIADO {proprietario}", -valor, "pix", "moradia", ambigua=True)
        for mes in MESES
    ]


def _assinaturas(rng):
    quantidade = int(rng.integers(1, 4))
    escolhidas = rng.choice(len(cat.ASSINATURAS), size=quantidade, replace=False)
    linhas = []
    for i in escolhidas:
        nome, valor = cat.ASSINATURAS[i]
        linhas += _conta_mensal(rng, nome, "assinaturas", valor, 0, meio="cartao_credito")
    return linhas


def _contas_fixas(rng, cfg):
    escala = cfg["escala"]
    linhas = _aluguel(rng, cfg)
    linhas += _conta_mensal(rng, cat.CONTA_ENERGIA, "energia", _uniforme(rng, 90, 220) * escala, 0.2)
    linhas += _conta_mensal(rng, cat.CONTA_AGUA, "agua", _uniforme(rng, 40, 110) * escala, 0.15)
    linhas += _conta_mensal(rng, cat.CONTA_TELECOM, "telecom", _uniforme(rng, 60, 150) * escala, 0)
    if rng.random() < cfg["chance_educacao"]:
        escola, minimo, maximo = _escolher(rng, cat.ESCOLAS)
        linhas += _conta_mensal(rng, escola, "educacao", _uniforme(rng, minimo, maximo) * escala, 0)
    if rng.random() < cfg["chance_plano_saude"]:
        plano, minimo, maximo = _escolher(rng, cat.PLANOS_SAUDE)
        linhas += _conta_mensal(rng, plano, "saude", _uniforme(rng, minimo, maximo) * escala, 0)
    return linhas + _assinaturas(rng)


def _custos_do_carro(rng, cfg):
    """Seguro mensal (nem todo dono tem), IPVA em 3 parcelas de janeiro a março e licenciamento em abril."""
    linhas = []
    if rng.random() < 0.6:
        seguro, minimo, maximo = _escolher(rng, cat.SEGUROS_AUTO)
        linhas += _conta_mensal(rng, seguro, "veiculos", _uniforme(rng, minimo, maximo) * cfg["escala"], 0)
    ipva = _uniforme(rng, 600, 1800) * cfg["escala"] / 3
    dia = _dia(rng)
    linhas += [
        _linha(_data(mes, dia), f"PAGTO BOLETO {cat.IPVA}", -ipva, "boleto", "veiculos", parcela=f"{mes}/3", loja=cat.IPVA)
        for mes in (1, 2, 3)
    ]
    linhas.append(_linha(_data(4, _dia(rng)), f"PAGTO BOLETO {cat.LICENCIAMENTO}", -_uniforme(rng, 150, 250),
                         "boleto", "veiculos", loja=cat.LICENCIAMENTO))
    return linhas


def _impostos_e_tarifas(rng, cfg):
    """DAS do MEI (autônomos), IPTU em 10 parcelas a partir de fevereiro, DARF do IR, tarifas e juros do banco."""
    linhas = []
    if cfg["tipo_renda"] == "variavel":
        nome, minimo, maximo = cat.DAS_MEI
        linhas += _conta_mensal(rng, nome, "impostos_contribuicoes", _uniforme(rng, minimo, maximo), 0)
    if rng.random() < cfg["chance_iptu"]:
        parcela, dia = _uniforme(rng, 60, 200) * cfg["escala"], _dia(rng)
        linhas += [
            _linha(_data(mes, dia), f"PAGTO BOLETO {cat.IPTU}", -parcela, "boleto", "moradia", parcela=f"{mes - 1}/10", loja=cat.IPTU)
            for mes in MESES if mes >= 2
        ]
    if rng.random() < cfg["chance_darf"]:
        linhas.append(_linha(_data(4, _dia(rng)), f"PAGTO BOLETO {cat.DARF_IRPF}", -_uniforme(rng, 200, 900),
                             "boleto", "impostos_contribuicoes", loja=cat.DARF_IRPF))
    if rng.random() < cfg["chance_tarifa"]:
        nome, minimo, maximo = _escolher(rng, cat.TARIFAS)
        valor, dia = _uniforme(rng, minimo, maximo), _dia(rng)
        linhas += [_linha(_data(mes, dia), nome, -valor, "debito_automatico", "tarifas_bancarias", loja=nome) for mes in MESES]
    if cfg["dividas"][1] > 0 and rng.random() < 0.5:
        # Quem tem dívidas às vezes entra no cheque especial
        for mes in sorted(int(m) for m in rng.choice(MESES, size=int(rng.integers(1, 4)), replace=False)):
            linhas.append(_linha(_data(mes, 28), cat.JUROS_CHEQUE_ESPECIAL, -_uniforme(rng, 15, 90), "debito_automatico",
                                 "tarifas_bancarias", loja=cat.JUROS_CHEQUE_ESPECIAL))
    return linhas


def _envios_para_familia(rng, cfg, nome_usuario):
    """PIX mensal para um parente (mesmo sobrenome), por exemplo ajuda aos pais ou mesada."""
    if rng.random() >= cfg["chance_envio_familia"]:
        return []
    sobrenome = nome_usuario.split()[-1]
    parente = _nome_pessoa(rng, sobrenome)
    while parente == nome_usuario:
        parente = _nome_pessoa(rng, sobrenome)
    valor, dia = _uniforme(rng, 100, 400) * cfg["escala"], int(rng.integers(1, 15))
    return [
        _linha(_data(mes, dia), f"PIX ENVIADO {parente}", -valor * _uniforme(rng, 0.9, 1.1), "pix", "transferencia_familiar", ambigua=True)
        for mes in MESES
    ]


def _dividas(rng, cfg):
    """Dívidas pagas por boleto, com número da parcela (ex.: 7/24)."""
    quantidade = int(rng.integers(cfg["dividas"][0], cfg["dividas"][1] + 1))
    linhas = []
    for i in rng.choice(len(cat.DIVIDAS), size=quantidade, replace=False):
        nome, minimo, maximo, total_parcelas = cat.DIVIDAS[i]
        valor = _uniforme(rng, minimo, maximo) * cfg["escala"]
        # Número da parcela paga em janeiro (a dívida pode ter começado antes)
        primeira = int(rng.integers(1, total_parcelas - len(MESES) + 2))
        dia = _dia(rng)
        texto = _abreviar_as_vezes(rng, nome)
        for deslocamento, mes in enumerate(MESES):
            parcela = f"{primeira + deslocamento}/{total_parcelas}"
            linhas.append(_linha(_data(mes, dia), f"PAGTO BOLETO {texto}", -valor, "boleto", "pagamento_dividas", parcela=parcela, loja=nome))
    return linhas


def _parcelamentos(rng, cfg):
    """Compras parceladas no cartão. Só entram as parcelas que caem entre janeiro e junho."""
    quantidade = int(rng.integers(cfg["parcelamentos"][0], cfg["parcelamentos"][1] + 1))
    linhas = []
    for i in rng.choice(len(cat.COMPRAS_PARCELADAS), size=quantidade, replace=False):
        loja, minimo, maximo, categoria = cat.COMPRAS_PARCELADAS[i]
        total_parcelas = int(_escolher(rng, [3, 4, 5, 6, 10, 12]))
        valor_parcela = round(_uniforme(rng, minimo, maximo) * cfg["escala"] / total_parcelas, 2)
        # Índice do mês da 1ª parcela (0 = janeiro; negativo = começou antes)
        inicio = int(rng.integers(-total_parcelas + 1, len(MESES)))
        dia = _dia(rng)
        texto = _baguncar(rng, loja)  # todas as parcelas aparecem com o mesmo texto
        for numero in range(1, total_parcelas + 1):
            indice = inicio + numero - 1
            if 0 <= indice < len(MESES):
                linhas.append(_linha(_data(MESES[indice], dia), texto, -valor_parcela, "cartao_credito", categoria, parcela=f"{numero}/{total_parcelas}", loja=loja))
    return linhas


# ---------- Gastos do dia a dia, PIX ambíguos e transferências internas ----------

def _sortear_habitos(rng, tem_carro):
    """Cada usuário tem suas lojas favoritas e sua frequência de compra por categoria."""
    favoritos, frequencia = {}, {}
    for categoria, lojas in cat.ESTABELECIMENTOS.items():
        quantidade = min(len(lojas), int(rng.integers(2, 4)))
        favoritos[categoria] = [lojas[i] for i in rng.choice(len(lojas), size=quantidade, replace=False)]
        frequencia[categoria] = _uniforme(rng, 0.5, 1.5)
    if rng.random() < 0.5:
        frequencia["jogos"] = 0  # metade dos usuários não gasta com jogos
    if not tem_carro:
        frequencia["veiculos"] = 0
    return {"favoritos": favoritos, "frequencia": frequencia}


def _compra(rng, mes, categoria, habitos, escala, dia=None, anomalia=""):
    loja, minimo, maximo = _escolher(rng, habitos["favoritos"][categoria])
    meio = _escolher(rng, MEIOS[categoria])
    valor = _uniforme(rng, minimo, maximo) * escala
    return _linha(_data(mes, dia or _dia(rng)), PREFIXOS[meio] + _baguncar(rng, loja), -valor, meio, categoria, anomalia=anomalia, loja=loja)


def _gastos_do_dia_a_dia(rng, cfg, habitos):
    linhas = []
    for mes in MESES:
        for categoria, (minimo, maximo) in FREQUENCIA_MENSAL.items():
            quantidade = round(int(rng.integers(minimo, maximo + 1)) * habitos["frequencia"][categoria])
            linhas += [_compra(rng, mes, categoria, habitos, cfg["escala"]) for _ in range(quantidade)]
    return linhas


def _pix_ambiguos(rng, cfg):
    """PIX para pessoas: contatos frequentes (mesma finalidade sempre) e alguns avulsos."""
    contatos = [(_nome_pessoa(rng), _escolher(rng, cat.FINALIDADES_PIX)) for _ in range(int(rng.integers(1, 4)))]
    linhas = []
    for mes in MESES:
        envios = [contato for contato in contatos if rng.random() < 0.4]
        if rng.random() < 0.2:
            envios.append((_nome_pessoa(rng), _escolher(rng, cat.FINALIDADES_PIX)))
        for nome, (categoria, minimo, maximo) in envios:
            valor = _uniforme(rng, minimo, maximo) * cfg["escala"]
            linhas.append(_linha(_data(mes, _dia(rng)), f"PIX ENVIADO {nome}", -valor, "pix", categoria, ambigua=True))
    return linhas


def _saques(rng, cfg):
    """Saques em dinheiro: o extrato não mostra em que o dinheiro foi gasto."""
    if rng.random() >= cfg["chance_saque"]:
        return []
    local = _escolher(rng, cat.SAQUES)
    linhas = []
    for mes in MESES:
        for _ in range(int(rng.integers(0, 3))):
            valor = round(_uniforme(rng, 50, 300) * cfg["escala"] / 10) * 10  # saque é valor redondo
            linhas.append(_linha(_data(mes, _dia(rng)), local, -max(valor, 20), "saque", "saque", loja=local))
    return linhas


def _aplicacoes(rng, cfg):
    """Aplicação mensal num investimento do próprio usuário (sai da conta corrente e entra na reserva)."""
    if rng.random() >= cfg["chance_aplicacao"]:
        return []
    texto = _escolher(rng, cat.APLICACOES)
    valor, dia = _uniforme(rng, 150, 500) * cfg["escala"], _dia(rng)
    linhas = []
    for mes in MESES:
        if rng.random() < 0.8:
            linhas += [
                _linha(_data(mes, dia), texto, -valor, "ted", "guardar_investir", conta="corrente"),
                _linha(_data(mes, dia), texto, valor, "ted", "guardar_investir", conta="poupanca"),
            ]
    return linhas


def _par_de_transferencia(rng, data, valor, para_poupanca, nome_usuario):
    """Uma transferência interna gera duas linhas: a saída de uma conta e a entrada na outra."""
    origem, destino = ("corrente", "poupanca") if para_poupanca else ("poupanca", "corrente")
    if rng.random() < 0.5:
        texto_saida = texto_entrada = "TRANSF ENTRE CONTAS PROPRIAS"
        meio = "ted"
    else:
        # PIX para o próprio nome: mais difícil de reconhecer
        texto_saida, texto_entrada = f"PIX ENVIADO {nome_usuario}", f"PIX RECEBIDO {nome_usuario}"
        meio = "pix"
    return [
        _linha(data, texto_saida, -valor, meio, "transferencia_interna", conta=origem),
        _linha(data, texto_entrada, valor, meio, "transferencia_interna", conta=destino),
    ]


def _transferencias_internas(rng, cfg, nome_usuario):
    linhas = []
    for mes in MESES:
        if rng.random() >= cfg["chance_poupanca"]:
            continue
        valor = _uniforme(rng, *cfg["poupanca"])
        para_poupanca = rng.random() < 0.85
        linhas += _par_de_transferencia(rng, _data(mes, _dia(rng)), valor, para_poupanca, nome_usuario)
    return linhas


# ---------- Orçamento ----------

def _ajustar_ao_orcamento(rng, cfg, rendas, fixas, ajustaveis):
    """Ajusta os gastos do dia a dia para a sobra do usuário cair na faixa do perfil.

    Sem isso, os gastos eram sorteados sem olhar a renda e muita gente gastava mais do
    que ganhava todo mês. Contas fixas, dívidas e parcelas não mudam; só os valores
    das compras do dia a dia e dos PIX para pessoas. As anomalias entram depois, por cima.
    """
    renda = sum(l["valor"] for l in rendas if l["categoria"] in ("renda_fixa", "renda_variavel"))
    gasto_fixo = sum(-l["valor"] for l in fixas)
    gasto_ajustavel = sum(-l["valor"] for l in ajustaveis)
    alvo = renda * (1 - _uniforme(rng, *cfg["sobra_alvo"])) - gasto_fixo
    fator = min(max(alvo / gasto_ajustavel, FATOR_MINIMO), FATOR_MAXIMO) if gasto_ajustavel > 0 else 1.0
    for linha in ajustaveis:
        linha["valor"] = round(linha["valor"] * fator, 2)


# ---------- Anomalias plantadas ----------

def _media_mensal(linhas, categoria, antes_do_mes):
    meses = [m for m in MESES if m < antes_do_mes]
    total = sum(-l["valor"] for l in linhas if l["categoria"] == categoria and l["data"].month in meses)
    return total / len(meses)


def _pico_categoria(rng, mes, cfg, habitos, linhas):
    """Compras extras que deixam o mês bem acima da média da categoria."""
    categoria = _escolher(rng, ["restaurantes_bares", "compras", "lazer"])
    media = _media_mensal(linhas, categoria, mes)
    extra_desejado = max(media, 150 * cfg["escala"]) * _uniforme(rng, 1.5, 2.5)
    extras, soma = [], 0.0
    while soma < extra_desejado:
        compra = _compra(rng, mes, categoria, habitos, cfg["escala"], anomalia="pico_categoria")
        extras.append(compra)
        soma -= compra["valor"]
    return extras


def _cobranca_duplicada(rng, mes, cfg, habitos, linhas):
    """Repete uma cobrança já existente, no mesmo dia ou no dia seguinte."""
    candidatas = [
        l for l in linhas
        if l["data"].month == mes and l["valor"] < 0 and not l["parcela"]
        and l["meio"] in ("cartao_credito", "cartao_debito", "boleto")
    ]
    copia = dict(_escolher(rng, candidatas))
    if rng.random() < 0.5 and copia["data"].day < 28:
        copia["data"] = copia["data"] + timedelta(days=1)
    copia["tipo_anomalia"] = "cobranca_duplicada"
    return [copia]


def _estabelecimento_novo_alto(rng, mes, cfg, habitos, linhas):
    loja = _escolher(rng, cat.ESTABELECIMENTOS_NOVOS)
    texto = _baguncar(rng, loja)
    valor = _uniforme(rng, 900, 2000) * cfg["escala"]
    return [_linha(_data(mes, _dia(rng)), texto, -valor, "cartao_credito", "compras", anomalia="estabelecimento_novo_alto", loja=loja)]


def _frequencia_incomum(rng, mes, cfg, habitos, linhas):
    """Muitas compras pequenas na mesma loja em um ou dois dias."""
    categoria = _escolher(rng, ["transporte", "restaurantes_bares", "jogos"])
    loja, minimo, maximo = min(habitos["favoritos"][categoria], key=lambda item: item[1])
    meio = _escolher(rng, MEIOS[categoria])
    texto = _baguncar(rng, loja)
    dia_inicial = int(rng.integers(1, 28))
    linhas_novas = []
    for _ in range(int(rng.integers(8, 15))):
        dia = dia_inicial + int(rng.integers(0, 2))
        valor = _uniforme(rng, minimo, minimo + (maximo - minimo) * 0.4) * cfg["escala"]
        linhas_novas.append(_linha(_data(mes, dia), PREFIXOS[meio] + texto, -valor, meio, categoria, anomalia="frequencia_incomum", loja=loja))
    return linhas_novas


PLANTADORES = {
    "pico_categoria": _pico_categoria,
    "cobranca_duplicada": _cobranca_duplicada,
    "estabelecimento_novo_alto": _estabelecimento_novo_alto,
    "frequencia_incomum": _frequencia_incomum,
}


def _anomalias(rng, cfg, habitos, linhas):
    """Planta de 2 a 4 tipos diferentes de anomalia, cada um em um mês de abril a junho."""
    quantidade = int(rng.integers(2, 5))
    novas = []
    for tipo in rng.choice(TIPOS_ANOMALIA, size=quantidade, replace=False):
        mes = _escolher(rng, MESES_COM_ANOMALIA)
        novas += PLANTADORES[str(tipo)](rng, mes, cfg, habitos, linhas)
    return novas


def _conta_fixa_disparada(rng, linhas, renda_base, cfg):
    """Uma conta mensal vem bem maior em um mês. Altera a linha existente."""
    mes = _escolher(rng, MESES_COM_ANOMALIA)
    candidatas = [l for l in linhas if l["categoria"] in ("energia", "agua", "telecom") and l["data"].month == mes and not l["tipo_anomalia"]]
    conta = _escolher(rng, candidatas)
    conta["valor"] = round(conta["valor"] * _uniforme(rng, 2.5, 3.5), 2)
    conta["tipo_anomalia"] = "conta_fixa_disparada"
    return []


def _pix_alto_desconhecido(rng, linhas, renda_base, cfg):
    """PIX alto para uma pessoa que nunca apareceu no extrato."""
    nomes_vistos = {l["descricao"] for l in linhas}
    pessoa = _nome_pessoa(rng)
    while f"PIX ENVIADO {pessoa}" in nomes_vistos:
        pessoa = _nome_pessoa(rng)
    categoria, _, _ = _escolher(rng, cat.FINALIDADES_PIX)
    mes = _escolher(rng, MESES_COM_ANOMALIA)
    valor = renda_base * _uniforme(rng, 0.3, 0.6)
    return [_linha(_data(mes, _dia(rng)), f"PIX ENVIADO {pessoa}", -valor, "pix", categoria, ambigua=True, anomalia="pix_alto_desconhecido")]


def _cobranca_recorrente_nova(rng, linhas, renda_base, cfg):
    """Nova cobrança mensal pequena no cartão, a partir de um mês entre abril e junho."""
    nome, minimo, maximo = _escolher(rng, cat.COBRANCAS_NOVAS)
    valor = round(_uniforme(rng, minimo, maximo), 2)
    inicio = _escolher(rng, MESES_COM_ANOMALIA)
    dia = _dia(rng)
    return [
        _linha(_data(mes, dia), nome, -valor, "cartao_credito", "assinaturas", anomalia="cobranca_recorrente_nova", loja=nome)
        for mes in MESES if mes >= inicio
    ]


PLANTADORES_NAO_PREVISTOS = {
    "conta_fixa_disparada": _conta_fixa_disparada,
    "pix_alto_desconhecido": _pix_alto_desconhecido,
    "cobranca_recorrente_nova": _cobranca_recorrente_nova,
}


def _anomalias_nao_previstas(rng, cfg, renda_base, linhas):
    """Planta 1 ou 2 tipos não previstos por usuário."""
    novas = []
    for tipo in rng.choice(TIPOS_NAO_PREVISTOS, size=int(rng.integers(1, 3)), replace=False):
        novas += PLANTADORES_NAO_PREVISTOS[str(tipo)](rng, linhas, renda_base, cfg)
    return novas


# ---------- Fatura do cartão ----------

def _faturas(rng, linhas):
    """Todo dia 10 a conta corrente paga a fatura com as compras no cartão do mês anterior."""
    gasto_cartao = {
        mes: sum(-l["valor"] for l in linhas if l["meio"] == "cartao_credito" and l["data"].month == mes)
        for mes in MESES
    }
    faturas = []
    for mes in MESES:
        if mes == MESES[0]:
            # Não temos dezembro: estimamos a fatura a partir de janeiro
            valor = gasto_cartao[mes] * _uniforme(rng, 0.9, 1.1)
        else:
            valor = gasto_cartao[mes - 1]
        if valor > 0:
            faturas.append(_linha(_data(mes, 10), "PAGAMENTO FATURA CARTAO", -valor, "boleto", "pagamento_fatura"))
    return faturas


# ---------- Montagem ----------

def _gerar_usuario(id_usuario, perfil, rng, nomes_usados, tem_renda_desconhecida, troca_emprego=False):
    cfg = PERFIS[perfil]
    nome = _nome_pessoa(rng)
    while nome in nomes_usados:
        nome = _nome_pessoa(rng)
    nomes_usados.add(nome)
    usuario = {
        "id_usuario": id_usuario,
        "nome": nome,
        "perfil": perfil,
        "renda_base": round(_uniforme(rng, *cfg["renda"]), 2),
        "troca_emprego": troca_emprego,
    }
    tem_carro = rng.random() < cfg["chance_carro"]
    habitos = _sortear_habitos(rng, tem_carro)

    rendas = _rendas(rng, usuario, cfg, tem_renda_desconhecida)
    fixas = _contas_fixas(rng, cfg) + _dividas(rng, cfg) + _parcelamentos(rng, cfg)
    fixas += (_custos_do_carro(rng, cfg) if tem_carro else []) + _impostos_e_tarifas(rng, cfg)
    fixas += _envios_para_familia(rng, cfg, nome)
    ajustaveis = _gastos_do_dia_a_dia(rng, cfg, habitos) + _pix_ambiguos(rng, cfg) + _saques(rng, cfg)
    _ajustar_ao_orcamento(rng, cfg, rendas, fixas, ajustaveis)
    linhas = rendas + fixas + ajustaveis + _transferencias_internas(rng, cfg, nome) + _aplicacoes(rng, cfg)
    linhas += _anomalias(rng, cfg, habitos, linhas)
    linhas += _anomalias_nao_previstas(rng, cfg, usuario["renda_base"], linhas)
    linhas += _faturas(rng, linhas)

    for linha in linhas:
        linha["id_usuario"] = id_usuario
    return usuario, linhas


def gerar_dados(semente=SEMENTE):
    """Gera todas as tabelas. A mesma semente sempre produz exatamente os mesmos dados."""
    rng = np.random.default_rng(semente)
    usuarios, linhas, nomes_usados = [], [], set()
    numero = 1
    for perfil in PERFIS:
        for indice in range(USUARIOS_POR_PERFIL):
            # O 2º usuário de cada perfil recebe entradas de origem desconhecida,
            # para garantir esse caso em todos os perfis.
            tem_renda_desconhecida = indice == 1
            # O 3º usuário de cada perfil com salário troca de emprego no meio do período
            troca_emprego = indice == 2 and PERFIS[perfil]["tipo_renda"] == "fixa"
            usuario, linhas_usuario = _gerar_usuario(
                f"U{numero:02d}", perfil, rng, nomes_usados, tem_renda_desconhecida, troca_emprego
            )
            usuarios.append(usuario)
            linhas += linhas_usuario
            numero += 1

    tabela = pd.DataFrame(linhas).sort_values(["id_usuario", "data"], kind="stable").reset_index(drop=True)
    tabela.insert(0, "id_transacao", [f"T{i:06d}" for i in range(1, len(tabela) + 1)])
    tabela["data"] = tabela["data"].map(date.isoformat)
    tabela["ambigua"] = tabela["ambigua"].map({True: "sim", False: "nao"})
    tabela["grupo"] = tabela["categoria"].map(CATEGORIAS)

    tabela_usuarios = pd.DataFrame(usuarios)
    return {
        "extrato": tabela[COLUNAS_EXTRATO],
        "usuarios": tabela_usuarios[["id_usuario", "nome"]],
        "verdade": tabela[COLUNAS_VERDADE],
        "usuarios_verdade": tabela_usuarios[["id_usuario", "perfil", "renda_base", "troca_emprego"]],
    }


def salvar_dados(dados, pasta=PASTA_PADRAO):
    """Grava cada tabela como CSV na pasta indicada."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    for nome, tabela in dados.items():
        tabela.to_csv(pasta / f"{nome}.csv", index=False)
    return pasta


def resumo(dados):
    """Texto curto com os números principais dos dados gerados."""
    extrato, verdade = dados["extrato"], dados["verdade"]
    pix = extrato["meio"] == "pix"
    ambiguos = verdade.loc[pix, "ambigua"].eq("sim").mean()
    anomalias = verdade["tipo_anomalia"].replace("", pd.NA).dropna().value_counts()
    linhas = [
        f"Usuários: {len(dados['usuarios'])} | Transações: {len(extrato)}",
        f"PIX ambíguos (pessoa física sem pista da finalidade): {ambiguos:.0%} dos PIX",
        "Transações anômalas plantadas por tipo:",
    ]
    linhas += [f"  - {tipo}: {quantidade}" for tipo, quantidade in anomalias.items()]
    return "\n".join(linhas)
