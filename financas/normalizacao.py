"""Normalização do extrato (Fase 2): limpa e organiza os dados antes de classificar.

Linhas repetidas NÃO são removidas: uma repetição pode ser uma cobrança duplicada
que o usuário precisa ver.
"""

import re
import unicodedata
from pathlib import Path

import pandas as pd

from financas.gerador import PASTA_PADRAO

# Prefixos que o banco coloca na descrição: (texto, nome da operação)
PREFIXOS_OPERACAO = [
    ("COMPRA DEBITO ", "compra_debito"),
    ("PIX ENVIADO ", "pix_enviado"),
    ("PIX ENVIADO-", "pix_enviado"),
    ("PIX RECEBIDO ", "pix_recebido"),
    ("PAGTO BOLETO ", "pagto_boleto"),
    ("CREDITO SALARIO ", "credito_salario"),
    ("PAGAMENTO SALARIO ", "credito_salario"),
    ("TED RECEBIDA ", "ted_recebida"),
    ("CRED TED ", "ted_recebida"),
]


def normalizar_texto(texto):
    """Maiúsculas, sem acentos e sem espaços repetidos. Ex.: ' Pão  de Açúcar' -> 'PAO DE ACUCAR'."""
    if pd.isna(texto):
        return ""
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", sem_acento).strip().upper()


def chave_de_loja(contraparte):
    """Forma "limpa" do nome para comparar lojas: sem prefixo de maquininha, números e espaços.

    Ex.: "LV*SUSHIKAZU" e "SUSHI KAZU 1234" viram ambos "SUSHIKAZU".
    """
    sem_prefixo = re.sub(r"^[A-Z]{1,10}\*", "", contraparte)
    return re.sub(r"[^A-Z]", "", sem_prefixo)


def separar_operacao(descricao):
    """Separa o prefixo do banco da contraparte (quem recebeu ou pagou)."""
    for prefixo, operacao in PREFIXOS_OPERACAO:
        if descricao.startswith(prefixo):
            # "PIX ENVIADO - MARIA SOUZA" -> contraparte "MARIA SOUZA"
            return operacao, descricao[len(prefixo):].lstrip("- ").strip()
    return "outra", descricao


def _separar_parcela(parcela):
    """'3/12' -> (3, 12). Vazio -> (None, None)."""
    texto = "" if pd.isna(parcela) else str(parcela).strip()
    if not re.fullmatch(r"\d+/\d+", texto):
        return None, None
    numero, total = texto.split("/")
    return int(numero), int(total)


def normalizar(extrato):
    """Devolve uma cópia do extrato limpa e com colunas auxiliares."""
    from financas.pessoas import extrair_documento  # aqui dentro: pessoas.py também usa este módulo

    tabela = extrato.copy()
    tabela["descricao"] = tabela["descricao"].map(normalizar_texto)
    # CPF/CNPJ na descrição: vira só "pessoa" ou "empresa" e o número é apagado (nunca é guardado nem mostrado)
    documentos = tabela["descricao"].map(extrair_documento)
    tabela["descricao"] = documentos.str[0]
    tabela["tipo_documento"] = documentos.str[1]
    tabela["data"] = pd.to_datetime(tabela["data"])
    tabela["mes"] = tabela["data"].dt.strftime("%Y-%m")
    tabela["valor"] = tabela["valor"].astype(float)
    tabela["direcao"] = tabela["valor"].map(lambda valor: "entrada" if valor > 0 else "saida")

    operacoes = tabela["descricao"].map(separar_operacao)
    tabela["operacao"] = operacoes.str[0]
    tabela["contraparte"] = operacoes.str[1]

    parcelas = tabela["parcela"].map(_separar_parcela)
    tabela["parcela"] = tabela["parcela"].fillna("").astype(str)
    tabela["parcela_numero"] = pd.array(parcelas.str[0], dtype="Int64")
    tabela["parcela_total"] = pd.array(parcelas.str[1], dtype="Int64")
    return tabela


def carregar_dados(pasta=PASTA_PADRAO):
    """Lê os CSVs que o sistema pode ver (extrato e usuários)."""
    pasta = Path(pasta)
    extrato = pd.read_csv(pasta / "extrato.csv", dtype={"parcela": str})
    usuarios = pd.read_csv(pasta / "usuarios.csv")
    return extrato, usuarios
