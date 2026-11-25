"""Extratos de conta e faturas enviados pela pessoa, em PDF ou CSV.

Fatura e extrato usam o sinal do valor de formas opostas:
- fatura de cartão: o valor positivo é compra; o negativo é pagamento ou estorno (ignorado)
- extrato de conta: o valor negativo é saída; o positivo é entrada (salário, PIX recebido...)

Por isso o primeiro passo é descobrir o tipo do documento. Depois, em cada linha do extrato,
o sistema descobre se o dinheiro entrou ou saiu, do jeito mais seguro para o mais fraco:
1. coluna "Entrada"/"Saída" (pela posição do número na página, no PDF)
2. sinal escrito no valor ("-92,79", "+5.000,00", "92,79 D", "5.000,00 C")
3. saldo: se o saldo subiu, foi entrada; se desceu, foi saída
4. palavras: "PIX RECEBIDO", "SALARIO", "Crédito"... (último recurso)

Tudo é lido só em memória (bytes): nada é gravado em disco.
"""

import csv
import io
import re
from dataclasses import dataclass

import pandas as pd
import pdfplumber

from financas.faturas_pdf import extrair_texto, ler_linhas
from financas.normalizacao import normalizar_texto

FATURA, EXTRATO = "fatura", "extrato"
COLUNAS_MOVIMENTOS = ["data", "descricao", "parcela", "valor", "tipo_banco", "categoria_banco"]

# Nome da coluna no documento -> papel dela
NOMES_DE_COLUNA = {
    "DATA": "data", "DATE": "data", "DATA LANCAMENTO": "data", "DATA DO LANCAMENTO": "data", "DATA MOVIMENTO": "data",
    "DESCRICAO": "descricao", "HISTORICO": "descricao", "LANCAMENTO": "descricao", "ESTABELECIMENTO": "descricao",
    "TITLE": "descricao", "MEMO": "descricao", "DESCRIPTION": "descricao", "IDENTIFICACAO": "descricao",
    "TIPO": "tipo", "NATUREZA": "tipo", "D/C": "tipo", "C/D": "tipo",
    "CATEGORIA": "categoria", "CATEGORY": "categoria",
    "ENTRADA": "entrada", "ENTRADAS": "entrada", "CREDITO": "entrada", "CREDITOS": "entrada", "CREDITO (R$)": "entrada",
    "SAIDA": "saida", "SAIDAS": "saida", "DEBITO": "saida", "DEBITOS": "saida", "DEBITO (R$)": "saida",
    "VALOR": "valor", "VALOR (R$)": "valor", "AMOUNT": "valor", "QUANTIA": "valor",
    "SALDO": "saldo", "SALDO (R$)": "saldo",
    "PARCELA": "parcela", "PARCELAS": "parcela", "INSTALLMENT": "parcela",
    "CPF/CNPJ": "documento", "CPF": "documento", "CNPJ": "documento", "DOCUMENTO": "documento", "CPF CNPJ": "documento",
}
COLUNAS_NUMERICAS = ("entrada", "saida", "valor", "saldo")
COLUNAS_DE_TEXTO = ("data", "descricao", "tipo", "categoria", "parcela")

# Palavras que indicam entrada quando nada mais resolve (no tipo da linha, aceita também "CREDITO")
PALAVRAS_DE_ENTRADA = ("RECEBIDO", "RECEBIDA", "SALARIO", "DEPOSITO", "RENDIMENTO", "REEMBOLSO", "ESTORNO", "RESGATE", "PROVENTO")
PALAVRAS_DE_ENTRADA_NO_TIPO = PALAVRAS_DE_ENTRADA + ("CREDITO", "ENTRADA")

MESES = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6,
    "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}
_VALOR = re.compile(r"^(?P<s1>[+-])?(?:R\$)?(?P<s2>[+-])?(?P<numero>\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})(?P<s3>[+-])?$")
_DATA_NO_INICIO = re.compile(r"^(?P<dia>\d{2})/(?P<mes>\d{2})(?:/(?P<ano>\d{2,4}))?$")
_MES_ANO = re.compile(rf"^({'|'.join(MESES)})\s*(?:/|DE)?\s*(\d{{4}})")
_PERIODO = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s*(?:A|ATE|-)\s*\d{2}/\d{2}/\d{4}")
_SALDO_INICIAL = re.compile(r"SALDO (?:INICIAL|ANTERIOR)\W*(?:R\$)?\s*(-?\s*[\d.]+,\d{2})")
_PARCELA = re.compile(r"\s*-?\s*PARC(?:ELA)?\.?\s*(\d{1,2})\s*(?:/|DE)\s*(\d{1,2})\b")
# Sem a palavra "parcela": "LOJA X 05/18" no fim da descrição também indica parcela
_PARCELA_NO_FIM = re.compile(r"\s+(\d{1,2})\s*/\s*(\d{1,2})$")
_FICTICIO = re.compile(r"FICTICI[AO]")
# Numa fatura, negativos são só pagamentos e estornos: bem menos de 15% das linhas
PROPORCAO_MAXIMA_NEGATIVOS_FATURA = 0.15
_VALOR_NEGATIVO_NO_FIM = re.compile(r"(?:-\s*(?:R\$\s*)?\d{1,3}(?:\.\d{3})*,\d{2}|\d{1,3}(?:\.\d{3})*,\d{2}\s*-|\d,\d{2}\s+D)$")
_VALOR_NO_FIM = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}\s*[-CD]?$")


@dataclass
class Documento:
    """Um arquivo enviado, já lido."""
    nome: str
    tipo: str  # FATURA ou EXTRATO
    movimentos: pd.DataFrame  # fatura: valor + = compra. extrato: valor + = entrada, - = saída
    ignoradas: int  # linhas com data que não viraram movimento
    ficticio: bool  # documento de exemplo (o voto no aprendizado não conta como dado real)

    @property
    def vazio(self):
        return self.movimentos.empty


# ---------- Peças comuns ----------

def numero(texto):
    """'1.234,56', '-92,79', 'R$ 5.000,00', '1234.56', '92,79 D', '(10,00)' -> float com sinal. None se não for número."""
    bruto = str(texto).strip().upper().replace("R$", "").replace(" ", "")
    if not bruto:
        return None
    negativo = bruto.startswith("-") or bruto.endswith("-") or bruto.endswith("D") or (bruto.startswith("(") and bruto.endswith(")"))
    bruto = bruto.strip("+-()CD")
    if not re.fullmatch(r"[\d.,]+", bruto) or not re.search(r"\d", bruto):
        return None
    if "," in bruto and "." in bruto:
        decimal = "," if bruto.rfind(",") > bruto.rfind(".") else "."
    elif "," in bruto:
        decimal = "," if len(bruto.split(",")[-1]) <= 2 else ""
    elif "." in bruto:
        # "1.234" (milhar) x "1234.5" (decimal): 3 dígitos depois do ponto = milhar
        decimal = "" if len(bruto.split(".")[-1]) == 3 else "."
    else:
        decimal = ""
    milhar = {",": ".", ".": ",", "": ".,"}[decimal]
    for separador in milhar:
        bruto = bruto.replace(separador, "")
    valor = float(bruto.replace(",", ".")) if bruto else None
    return -valor if (valor is not None and negativo) else valor


def _data(texto, ano_padrao=None):
    """'05/06/2026', '05/06/26', '2026-06-05', '05-06-2026' ou '05/06' (com ano_padrao) -> 'AAAA-MM-DD'."""
    texto = str(texto).strip()
    for padrao, ordem in ((r"(\d{4})-(\d{2})-(\d{2})", "amd"), (r"(\d{2})[/-](\d{2})[/-](\d{2,4})", "dma"), (r"(\d{2})/(\d{2})", "dm")):
        achado = re.match(padrao + r"\b", texto)
        if not achado:
            continue
        partes = dict(zip(ordem, achado.groups()))
        ano = int(partes.get("a", ano_padrao or 0))
        ano = ano + 2000 if 0 < ano < 100 else ano
        if not ano:
            return None
        try:
            return pd.Timestamp(year=ano, month=int(partes["m"]), day=int(partes["d"])).strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def _separar_parcela(descricao):
    """'IPVA 2026 - PARCELA 3/3 (SEFAZ)' -> ('IPVA 2026 (SEFAZ)', '3/3'). Sem a parcela, a mesma compra fica com o mesmo texto todo mês."""
    achado = _PARCELA.search(descricao) or _PARCELA_NO_FIM.search(descricao)
    if not achado or not 1 <= int(achado.group(1)) <= int(achado.group(2)) or int(achado.group(2)) < 2:
        return descricao, ""
    limpa = (descricao[: achado.start()] + " " + descricao[achado.end():]).strip(" -")
    return re.sub(r"\s+", " ", limpa), f"{int(achado.group(1))}/{int(achado.group(2))}"


def _entrou_pelas_palavras(descricao, tipo=""):
    tipo, descricao = normalizar_texto(tipo), normalizar_texto(descricao)
    if tipo:
        if any(palavra in tipo for palavra in PALAVRAS_DE_ENTRADA_NO_TIPO):
            return True
        if any(palavra in tipo for palavra in ("DEBITO", "SAIDA", "ENVIADO", "PAGAMENTO", "SAQUE", "TARIFA")):
            return False
    return any(re.search(rf"\b{palavra}\b", descricao) for palavra in PALAVRAS_DE_ENTRADA)


def _movimento(data, descricao, valor, tipo="", categoria="", parcela_escrita=""):
    descricao, parcela = _separar_parcela(normalizar_texto(descricao))
    if not parcela and parcela_escrita:
        # Coluna "Parcela" do documento: "05/18", "5 de 18" ou "PARC 5/18"
        _, parcela = _separar_parcela("X PARCELA " + normalizar_texto(parcela_escrita).replace("PARCELA", "").replace("PARC", "").strip())
    return {
        "data": data, "descricao": descricao, "parcela": parcela, "valor": round(valor, 2),
        "tipo_banco": str(tipo or "").strip(), "categoria_banco": str(categoria or "").strip(),
    }


def _tabela(movimentos):
    return pd.DataFrame(movimentos, columns=COLUNAS_MOVIMENTOS)


# ---------- Extrato em PDF ----------

def _linhas_da_pagina(pagina, tolerancia=3):
    """Palavras da página agrupadas em linhas, cada palavra com sua posição (x0, x1)."""
    palavras = sorted(pagina.extract_words(), key=lambda p: (round(p["top"]), p["x0"]))
    linhas, atual, topo = [], [], None
    for palavra in palavras:
        if topo is not None and abs(palavra["top"] - topo) > tolerancia:
            linhas.append(sorted(atual, key=lambda p: p["x0"]))
            atual = []
        if not atual:
            topo = palavra["top"]
        atual.append(palavra)
    if atual:
        linhas.append(sorted(atual, key=lambda p: p["x0"]))
    return linhas


def _cabecalho(palavras):
    """Se a linha for o cabeçalho da tabela ('Data Descrição Entrada Saída Saldo'), devolve as colunas com a posição."""
    colunas = {}
    for palavra in palavras:
        papel = NOMES_DE_COLUNA.get(normalizar_texto(palavra["text"]))
        if papel and papel not in colunas:
            colunas[papel] = (palavra["x0"], palavra["x1"])
    tem_valor = any(nome in colunas for nome in ("valor", "entrada", "saida"))
    return colunas if "data" in colunas and "descricao" in colunas and tem_valor else None


def _ler_linha_com_colunas(palavras, colunas):
    """Separa as palavras da linha por coluna: texto (descrição, tipo, categoria) e números (entrada, saída, valor, saldo)."""
    numericas = {nome: pos for nome, pos in colunas.items() if nome in COLUNAS_NUMERICAS}
    de_texto = sorted(((pos[0], nome) for nome, pos in colunas.items() if nome in COLUNAS_DE_TEXTO))
    inicio_dos_numeros = min(pos[0] for pos in numericas.values()) - 40
    textos, numeros, marcador = {}, {}, None
    for palavra in palavras[1:]:  # a primeira é a data
        texto = palavra["text"]
        if texto in ("R$",):
            continue
        if palavra["x1"] >= inicio_dos_numeros and _VALOR.match(texto):
            centro = (palavra["x0"] + palavra["x1"]) / 2
            nome = min(numericas, key=lambda n: abs((numericas[n][0] + numericas[n][1]) / 2 - centro))
            numeros[nome] = texto
            continue
        if palavra["x1"] >= inicio_dos_numeros and texto.upper() in ("C", "D"):
            marcador = texto.upper()
            continue
        nome = "descricao"
        for x0, coluna in de_texto:
            if palavra["x0"] + 2 >= x0 and coluna != "data":
                nome = coluna
        textos.setdefault(nome, []).append(texto)
    return {nome: " ".join(partes) for nome, partes in textos.items()}, numeros, marcador


def _ler_linha_sem_colunas(palavras):
    """Sem cabeçalho: os números no fim da linha são o valor (e o saldo, se houver dois)."""
    restantes = [p["text"] for p in palavras[1:] if p["text"] != "R$"]
    marcador = None
    if restantes and restantes[-1].upper() in ("C", "D"):
        marcador = restantes.pop().upper()
    finais = []
    while restantes and _VALOR.match(restantes[-1]) and len(finais) < 2:
        finais.insert(0, restantes.pop())
    numeros = {}
    if finais:
        numeros["valor"] = finais[0]
        if len(finais) == 2:
            numeros["saldo"] = finais[1]
    return {"descricao": " ".join(restantes)}, numeros, marcador


def _valor_com_sinal(numeros, marcador, saldo_anterior, descricao, tipo):
    """Decide entrada (+) ou saída (-), do jeito mais seguro para o mais fraco."""
    if "entrada" in numeros:
        return abs(numero(numeros["entrada"]))
    if "saida" in numeros:
        return -abs(numero(numeros["saida"]))
    if "valor" not in numeros:
        return None
    escrito = numeros["valor"]
    valor = abs(numero(escrito))
    if escrito.strip().startswith(("-", "+")) or escrito.strip().endswith(("-", "+")) or marcador:
        entrou = not (escrito.strip().startswith("-") or escrito.strip().endswith("-") or marcador == "D")
        return valor if entrou else -valor
    if "saldo" in numeros and saldo_anterior is not None:
        diferenca = numero(numeros["saldo"]) - saldo_anterior
        if abs(diferenca - valor) < 0.015:
            return valor
        if abs(diferenca + valor) < 0.015:
            return -valor
    return valor if _entrou_pelas_palavras(descricao, tipo) else -valor


def _ano_inicial(texto_normalizado):
    """Ano do período do extrato ('01/06/2026 A 24/11/2026') ou o primeiro ano que aparecer no cabeçalho."""
    periodo = _PERIODO.search(texto_normalizado)
    if periodo:
        return int(periodo.group(3)), int(periodo.group(2))
    ano = re.search(r"\b(20\d{2})\b", texto_normalizado[:800])
    return (int(ano.group(1)), None) if ano else (None, None)


def ler_extrato_pdf(conteudo):
    """Lê um extrato de conta em PDF. Devolve (movimentos, linhas ignoradas)."""
    movimentos, ignoradas = [], 0
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        texto = normalizar_texto(" ".join(pagina.extract_text() or "" for pagina in pdf.pages[:1]))
        ano, mes_inicial = _ano_inicial(texto)
        mes_anterior = mes_inicial
        colunas, saldo_anterior = None, None
        for pagina in pdf.pages:
            for palavras in _linhas_da_pagina(pagina):
                linha = normalizar_texto(" ".join(p["text"] for p in palavras))
                novas_colunas = _cabecalho(palavras)
                if novas_colunas:
                    colunas = novas_colunas
                    continue
                titulo_do_mes = _MES_ANO.match(linha)
                if titulo_do_mes:
                    ano, mes_anterior = int(titulo_do_mes.group(2)), MESES[titulo_do_mes.group(1)]
                saldo = _SALDO_INICIAL.search(linha)
                if saldo:
                    saldo_anterior = numero(saldo.group(1))
                data_escrita = _DATA_NO_INICIO.match(palavras[0]["text"])
                if not data_escrita:
                    continue
                mes = int(data_escrita.group("mes"))
                if not data_escrita.group("ano") and ano and mes_anterior and mes < mes_anterior - 6:
                    ano += 1  # virada do ano num extrato sem títulos de mês (dezembro -> janeiro)
                mes_anterior = mes
                data = _data(palavras[0]["text"], ano)
                textos, numeros, marcador = (
                    _ler_linha_com_colunas(palavras, colunas) if colunas else _ler_linha_sem_colunas(palavras)
                )
                descricao, tipo = textos.get("descricao", ""), textos.get("tipo", "")
                valor = _valor_com_sinal(numeros, marcador, saldo_anterior, descricao, tipo)
                if "saldo" in numeros:
                    saldo_anterior = numero(numeros["saldo"])
                if data is None or valor is None or not descricao or normalizar_texto(descricao).startswith("SALDO"):
                    ignoradas += 1
                    continue
                movimentos.append(_movimento(data, descricao, valor, tipo, textos.get("categoria", ""), textos.get("parcela", "")))
    return _tabela(movimentos), ignoradas


def parece_extrato(texto):
    """O documento é um extrato de conta (e não uma fatura de cartão)?"""
    inicio = normalizar_texto(texto)[:800]
    if re.search(r"\bEXTRATO\b", inicio):
        return True
    if re.search(r"\bFATURA\b", inicio):
        return False
    # Sem título: um cabeçalho com Entrada/Saída ou Saldo é de extrato
    return bool(re.search(r"\b(ENTRADAS?|SAIDAS?|SALDO)\b", normalizar_texto(texto)))


# ---------- CSV ----------

def _texto_do_csv(conteudo):
    for codificacao in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return conteudo.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("latin-1", "replace")


def _separador(texto):
    amostra = "\n".join(texto.splitlines()[:30])
    try:
        return csv.Sniffer().sniff(amostra, delimiters=";,\t|").delimiter
    except csv.Error:
        return max(";,\t", key=amostra.count)


def _colunas_do_csv(linha):
    """Papel de cada coluna pelo nome. Devolve None se a linha não for um cabeçalho."""
    colunas = {}
    for indice, nome in enumerate(linha):
        papel = NOMES_DE_COLUNA.get(normalizar_texto(nome))
        if papel and papel not in colunas:
            colunas[papel] = indice
    tem_valor = any(nome in colunas for nome in ("valor", "entrada", "saida"))
    return colunas if "data" in colunas and "descricao" in colunas and tem_valor else None


def _com_documento(descricao, documento):
    """Junta o CPF/CNPJ de uma coluna própria à descrição, no formato que o sistema reconhece."""
    numeros = re.sub(r"\D", "", documento or "")
    if len(numeros) == 14:
        return f"{descricao} - CNPJ {numeros[:2]}.{numeros[2:5]}.{numeros[5:8]}/{numeros[8:12]}-{numeros[12:]}"
    if len(numeros) == 11:
        return f"{descricao} - CPF {numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"
    if "*" in (documento or "") and "." in documento:
        return f"{descricao} - CPF {documento.strip()}"
    return descricao


def eh_texto_de_entrada(descricao):
    """Descrição típica de dinheiro entrando na conta (nunca aparece numa compra de cartão)."""
    return bool(re.search(r"\b(RECEBIDO|RECEBIDA|DEPOSITO|SALARIO|MAQUININHA|VENDAS|TED RECEBIDA|CRED TED)\b", normalizar_texto(descricao)))


def _parece_fatura(nome_arquivo, linhas, negativos, recebimentos):
    """Fatura: valores positivos são compras e quase não há negativos (só 1 ou 2 pagamentos por mês).

    Extrato: tem bastante linha negativa (saídas) ou linhas de recebimento ("PIX RECEBIDO", "DEPOSITO"...).
    Quem recebe muitos PIX (ex.: vende salgados) tem metade das linhas positivas, e mesmo assim é extrato.
    """
    nome = normalizar_texto(nome_arquivo)
    if "EXTRATO" in nome:
        return False
    if "FATURA" in nome:
        return True
    if not linhas:
        return False
    return negativos / linhas < PROPORCAO_MAXIMA_NEGATIVOS_FATURA and recebimentos / linhas < 0.05


def ler_csv(conteudo, nome_arquivo=""):
    """Lê um extrato ou uma fatura em CSV. Devolve um Documento."""
    texto = _texto_do_csv(conteudo)
    linhas = list(csv.reader(io.StringIO(texto), delimiter=_separador(texto)))
    ficticio = bool(_FICTICIO.search(normalizar_texto(nome_arquivo + " " + texto[:500])))
    # O cabeçalho pode vir depois de algumas linhas de apresentação do banco
    inicio, colunas = next(((i, c) for i, linha in enumerate(linhas[:30]) if (c := _colunas_do_csv(linha))), (None, None))
    if colunas is None:
        return Documento(nome_arquivo, EXTRATO, _tabela([]), len(linhas), ficticio)

    def campo(linha, papel):
        indice = colunas.get(papel)
        return linha[indice].strip() if indice is not None and indice < len(linha) else ""

    brutos, ignoradas = [], 0
    for linha in linhas[inicio + 1:]:
        if not any(celula.strip() for celula in linha):
            continue
        data = _data(campo(linha, "data"))
        entrada, saida, valor = (numero(campo(linha, papel)) for papel in ("entrada", "saida", "valor"))
        descricao = _com_documento(campo(linha, "descricao"), campo(linha, "documento"))
        if data is None or not descricao or (entrada is None and saida is None and valor is None):
            ignoradas += 1
            continue
        brutos.append((data, descricao, entrada, saida, valor, campo(linha, "tipo"), campo(linha, "categoria"), campo(linha, "parcela")))

    tipos = {normalizar_texto(b[5]) for b in brutos} - {""}
    tipo_c_d = bool(tipos) and tipos <= {"C", "D", "CREDITO", "DEBITO", "ENTRADA", "SAIDA"}
    so_valor = "entrada" not in colunas and "saida" not in colunas
    negativos = sum(1 for b in brutos if b[4] is not None and b[4] < 0)
    recebimentos = sum(1 for b in brutos if b[4] is not None and b[4] > 0 and eh_texto_de_entrada(b[1]))
    eh_fatura = so_valor and not tipo_c_d and _parece_fatura(nome_arquivo, len(brutos), negativos, recebimentos)

    movimentos = []
    for data, descricao, entrada, saida, valor, tipo, categoria, parcela in brutos:
        if eh_fatura:
            if valor is None or valor <= 0 or normalizar_texto(descricao).startswith(("PAGAMENTO", "ESTORNO", "CREDITO")):
                ignoradas += 1
                continue
            movimentos.append(_movimento(data, descricao, valor, tipo, categoria, parcela))
            continue
        if entrada:
            final = abs(entrada)
        elif saida:
            final = -abs(saida)
        elif tipo_c_d:
            final = abs(valor) if normalizar_texto(tipo)[:1] in ("C", "E") else -abs(valor)
        else:
            final = valor
        if not final:
            ignoradas += 1
            continue
        movimentos.append(_movimento(data, descricao, final, tipo, categoria, parcela))
    tabela = _tabela(movimentos)
    if eh_fatura:
        tabela = tabela[["data", "descricao", "parcela", "valor"]]
    return Documento(nome_arquivo, FATURA if eh_fatura else EXTRATO, tabela, ignoradas, ficticio)


# ---------- Qualquer arquivo ----------

def _pdf_com_cara_de_extrato(texto):
    """Sem título nem colunas: muitas linhas terminando com valor negativo, ou linhas de recebimento, indicam extrato."""
    linhas = [normalizar_texto(linha) for linha in texto.splitlines()]
    com_valor = [linha for linha in linhas if re.match(r"^\d{2}/\d{2}", linha) and _VALOR_NO_FIM.search(linha)]
    if not com_valor:
        return False
    negativas = sum(1 for linha in com_valor if _VALOR_NEGATIVO_NO_FIM.search(linha))
    recebimentos = sum(1 for linha in com_valor if eh_texto_de_entrada(linha))
    return not _parece_fatura("", len(com_valor), negativas, recebimentos)


def ler_documento(conteudo, nome_arquivo=""):
    """Lê um PDF ou CSV enviado (fatura ou extrato) e devolve um Documento."""
    if nome_arquivo.lower().endswith(".csv"):
        return ler_csv(conteudo, nome_arquivo)
    texto = extrair_texto(conteudo)
    ficticio = bool(_FICTICIO.search(normalizar_texto(texto[:1500])))
    if parece_extrato(texto) or _pdf_com_cara_de_extrato(texto):
        movimentos, ignoradas = ler_extrato_pdf(conteudo)
        return Documento(nome_arquivo, EXTRATO, movimentos, ignoradas, ficticio)
    compras, ignoradas = ler_linhas(texto)
    return Documento(nome_arquivo, FATURA, compras, ignoradas, ficticio)
