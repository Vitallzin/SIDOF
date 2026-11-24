"""Catálogo fictício usado pelo gerador: lojas, empresas, contas e nomes de pessoas.

Todos os nomes são inventados. Valores em reais.
"""

# Gastos do dia a dia: categoria -> lista de (nome da loja, valor mínimo, valor máximo)
ESTABELECIMENTOS = {
    "alimentacao_basica": [
        ("SUPERMERCADO BOM PRECO", 80, 300),
        ("ATACADAO DO POVO", 120, 400),
        ("MERCADINHO SAO JORGE", 20, 100),
        ("HORTIFRUTI VERDE VIDA", 25, 80),
        ("PADARIA PAO DOURADO", 10, 40),
        ("ACOUGUE BOI NOBRE", 40, 150),
        # Nomes sem palavra-chave óbvia
        ("EMPORIO DONA ROSA", 30, 180),
        ("QUITANDA DO VALE", 20, 90),
        ("SACOLAO BARATAO", 40, 160),
    ],
    # Transporte: ônibus, metrô, trem e corridas por aplicativo
    "transporte": [
        ("APP CORRIDA *VIAGEM", 12, 40),
        ("RECARGA BILHETE TRANSPORTE", 50, 120),
        ("METRO LINHA AZUL", 5, 20),
        ("PASSE ONIBUS URBANO", 5, 25),
        ("MOBI APP *TRIP", 10, 35),  # sem palavra-chave óbvia
    ],
    # Veículo próprio: combustível, manutenção, estacionamento e pedágio (só para quem tem carro)
    "veiculos": [
        ("POSTO COMBUSTIVEL ESTRELA", 80, 220),
        ("AUTOPOSTO TREVO", 80, 220),
        ("ESTACIONAMENTO CENTRAL", 10, 30),
        ("TAG PEDAGIO RODOVIA", 15, 60),
        ("OFICINA MECANICA DO TIAO", 120, 600),
        ("AUTO PECAS RODA VIVA", 40, 300),
        ("GASOLINA E CIA", 80, 220),  # sem palavra-chave óbvia
    ],
    "saude": [
        ("DROGARIA SAUDE TOTAL", 15, 120),
        ("FARMACIA DO BAIRRO", 10, 80),
        ("LAB ANALISES VIDA", 50, 200),
        ("DROGAMAIS", 15, 100),
    ],
    "restaurantes_bares": [
        ("RESTAURANTE SABOR CASEIRO", 25, 70),
        ("BAR DO ZECA", 30, 110),
        ("PIZZARIA FORNO A LENHA", 50, 120),
        ("DLV*APP ENTREGA COMIDA", 30, 80),
        ("LANCHONETE ESQUINA", 15, 40),
        ("HAMBURGUERIA DO CHEF", 35, 85),
        ("CANTINA NONNA ITALIA", 50, 140),
        ("SUSHI KAZU", 60, 150),
        ("BOTECO DO ALEMAO", 30, 100),
        ("ACAI DA PRAIA", 15, 35),
    ],
    "lazer": [
        ("CINEMA SHOPPING PLAZA", 30, 80),
        ("INGRESSOS EVENTOS *SHOW", 80, 250),
        ("PARQUE AQUATICO SOL", 60, 150),
        ("TEATRO MUNICIPAL BILHETERIA", 40, 120),
        ("BOLICHE STRIKE", 40, 120),
        ("KARAOKE NOTURNO", 50, 150),
    ],
    "jogos": [
        ("LOJA JOGOS DIGITAIS *ONLINE", 20, 180),
        ("RECARGA CREDITOS GAME", 15, 90),
        ("PIXEL GAMES STORE", 20, 150),
    ],
    "compras": [
        ("LOJA DEPARTAMENTO MODA", 60, 250),
        ("MKTPLACE*PEDIDO", 30, 200),
        ("CALCADOS PASSO FIRME", 90, 250),
        ("PAPELARIA ESCOLAR", 15, 70),
        ("UTILIDADES DO LAR", 20, 120),
        ("BAZAR DA ESQUINA", 15, 80),
        ("BRECHO VINTAGE", 30, 150),
        ("PERFUMARIA AROMA", 40, 200),
        ("AUTO SHOP ACESSORIOS", 30, 150),  # kit de limpeza e acessórios do carro: é compra, não veículo
    ],
}

# Lojas que nunca aparecem no dia a dia. Usadas só na anomalia "estabelecimento novo com valor alto".
ESTABELECIMENTOS_NOVOS = [
    "ELETRONICOS IMPORTADOS LTDA",
    "JOALHERIA BRILHO ETERNO",
    "LOJA TECH PREMIUM",
    "ARTIGOS ESPORTIVOS RADICAL",
]

# Contas mensais: (nome da empresa, valor mínimo, valor máximo)
IMOBILIARIAS = ["IMOBILIARIA LAR DOCE LAR", "IMOBILIARIA CHAVE CERTA"]
CONTA_ENERGIA = "CIA ENERGIA ELETRICA"
CONTA_AGUA = "SANEAMENTO AGUAS CLARAS"
CONTA_TELECOM = "OPERADORA CONECTA TELECOM"
ESCOLAS = [
    ("FACULDADE SABER", 450, 900),
    ("CURSO IDIOMAS FALE BEM", 150, 350),
]
PLANOS_SAUDE = [("PLANO SAUDE VIDA PLENA", 200, 500)]
# Cobranças recorrentes que só aparecem como anomalia não prevista
COBRANCAS_NOVAS = [
    ("APPDIGITAL*PREMIUM", 19.90, 39.90),
    ("CLUBE VANTAGENS MENSAL", 29.90, 49.90),
    ("SEGURO CELULAR MENSAL", 24.90, 59.90),
]

ASSINATURAS = [
    ("STREAMING FILMES MAIS", 39.90),
    ("MUSICA PREMIUM", 21.90),
    ("NUVEM ARMAZENAMENTO", 9.90),
    ("ACADEMIA CORPO ATIVO", 99.90),
    ("CLUBE LIVROS DO MES", 49.90),
]

# Veículo: seguro mensal, IPVA em 3 parcelas (jan-mar) e licenciamento (abril)
SEGUROS_AUTO = [("SEGURO AUTO PROTEGE", 120, 280), ("SEGURO AUTO TRANQUILO", 100, 250)]
IPVA = "IPVA 2026 DETRAN"
LICENCIAMENTO = "LICENCIAMENTO 2026 DETRAN"

# Impostos, contribuições e tarifas
DAS_MEI = ("DAS MEI SIMPLES NACIONAL", 70, 82)
IPTU = "IPTU 2026 PREFEITURA"
DARF_IRPF = "DARF IRPF 2026"
TARIFAS = [("TARIFA PACOTE SERVICOS", 15, 45), ("TARIFA CESTA DE SERVICOS", 20, 40)]
JUROS_CHEQUE_ESPECIAL = "JUROS CHEQUE ESPECIAL"

# Saques e aplicações
SAQUES = ["SAQUE 24H BANCO", "SAQUE CAIXA ELETRONICO", "SAQUE BANCO 24 HORAS"]
APLICACOES = ["APLICACAO RESERVA CDB", "APLICACAO POUPANCA PROGRAMADA"]

# Dívidas pagas por boleto: (nome, parcela mínima, parcela máxima, total de parcelas)
DIVIDAS = [
    ("EMPRESTIMO PESSOAL BANCO FACIL", 250, 600, 24),
    ("ACORDO RENEGOCIACAO CARTAO", 150, 400, 12),
    ("FINANCIAMENTO MOTO VELOZ", 300, 550, 36),
]

# Compras parceladas no cartão: (loja, valor total mínimo, valor total máximo, categoria)
COMPRAS_PARCELADAS = [
    ("MAGAZINE ELETRO LAR", 800, 3000, "compras"),
    ("MOVEIS CASA BELA", 1000, 3500, "compras"),
    ("CELULARES CONECTADOS", 1200, 3000, "compras"),
    ("CLINICA ODONTO SORRIR", 600, 2400, "saude"),
    ("CURSO ONLINE CERTIFICA", 400, 1500, "educacao"),
    ("AGENCIA VIAGENS DESTINO", 1500, 4000, "lazer"),
]

# Finalidades reais de PIX enviados para pessoas: (categoria, valor mínimo, valor máximo)
# O extrato só mostra o nome da pessoa, por isso esses PIX são ambíguos.
FINALIDADES_PIX = [
    ("alimentacao_basica", 30, 150),  # feira, vizinho que vende comida
    ("restaurantes_bares", 20, 80),  # dividir a conta com amigos
    ("pagamento_dividas", 100, 400),  # devolver dinheiro emprestado
    ("lazer", 30, 150),  # rachar viagem ou ingresso
    ("compras", 50, 300),  # compra de usado
    ("saude", 100, 250),  # consulta particular
    ("transporte", 20, 60),  # carona
]

# Empregadores fictícios, escritos como os bancos mostram (com S.A., LTDA, EIRELI...)
EMPRESAS_EMPREGADORAS = [
    "METALURGICA ALFA LTDA",
    "COMERCIAL BETA S.A.",
    "HOSPITAL SAO LUCAS LTDA",
    "LOGISTICA RAPIDA LTDA",
    "ESCOLA MUNDO NOVO EIRELI",
    "SUPERMERCADOS PRECO BOM S/A",
    "TRANSPORTADORA CAMINHO CERTO LTDA",
    "PREFEITURA MUNICIPAL DE VILA NOVA",
    "TECH SOLUCOES DIGITAIS LTDA",
    "CONFECCOES ESTRELA ME",
]

# Como o salário aparece no extrato: (formato, meio). Muitos bancos NÃO escrevem "salário".
FORMATOS_SALARIO = [
    ("CREDITO SALARIO {}", "ted"),
    ("PAGAMENTO SALARIO {}", "ted"),
    ("TED RECEBIDA {}", "ted"),
    ("CRED TED {}", "ted"),
    ("PIX RECEBIDO {}", "pix"),
]

# Empresas que contratam autônomos
EMPRESAS_CLIENTES = [
    "AGENCIA CRIATIVA ME",
    "STUDIO DESIGN LTDA",
    "CONSTRUTORA HORIZONTE",
    "ESCRITORIO CONTABIL PRECISO",
    "EVENTOS E FESTAS ALEGRIA",
]

PRIMEIROS_NOMES = [
    "MARIA", "JOSE", "ANA", "JOAO", "FRANCISCA", "ANTONIO", "ADRIANA", "CARLOS",
    "JULIANA", "PAULO", "MARCIA", "PEDRO", "FERNANDA", "LUCAS", "PATRICIA", "RAFAEL",
    "ALINE", "MARCOS", "CAMILA", "BRUNO", "LETICIA", "DIEGO", "BEATRIZ", "THIAGO",
    "VANESSA", "RODRIGO", "SIMONE", "GABRIEL", "LUANA", "FELIPE",
]

SOBRENOMES = [
    "SILVA", "SANTOS", "OLIVEIRA", "SOUZA", "RODRIGUES", "FERREIRA", "ALVES", "PEREIRA",
    "LIMA", "GOMES", "COSTA", "RIBEIRO", "MARTINS", "CARVALHO", "ALMEIDA", "LOPES",
    "SOARES", "FERNANDES", "VIEIRA", "BARBOSA", "ROCHA", "DIAS", "NASCIMENTO", "MOREIRA",
]
