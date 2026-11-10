"""Faturas de cartão em PDF: gerar faturas fictícias e ler faturas de qualquer origem.

O leitor é genérico: procura linhas no formato mais comum das faturas brasileiras,
"data  descrição  [parcela]  valor", por exemplo:
    05/03  SUPERMERCADO BOM PRECO  03/12  1.234,56
    05/03/2026  LOJA X  PARC 02 DE 05  R$ 89,90
Pagamentos, totais e créditos (valores negativos) são ignorados: só compras viram transações.

Faturas enviadas pela interface são lidas só em memória (bytes); nada é gravado em disco.
"""

import io
import re

import pandas as pd
import pdfplumber
from fpdf import FPDF

from financas.formatacao import reais
from financas.normalizacao import normalizar_texto

TAMANHO_DESCRICAO = 28  # faturas costumam cortar o nome da loja
# Linhas que COMEÇAM com estas palavras não são compras (uma loja "SAUDE TOTAL" continua valendo)
PALAVRAS_IGNORADAS = ("PAGAMENTO", "TOTAL", "SALDO", "LIMITE", "VENCIMENTO", "ENCARGOS", "JUROS", "CREDITO", "ESTORNO")

_DATA = r"(?P<dia>\d{2})/(?P<mes>\d{2})(?:/(?P<ano>\d{2,4}))?"
_VALOR = r"(?P<sinal>-)?\s*(?:R\$\s*)?(?P<sinal2>-)?(?P<valor>\d{1,3}(?:\.\d{3})*,\d{2})(?P<sinal3>-)?"
LINHA_DE_COMPRA = re.compile(rf"^{_DATA}\s+(?P<meio>.+?)\s+{_VALOR}$")
PARCELA = re.compile(r"\s*(?:PARC(?:ELA)?\.?\s*)?(?P<numero>\d{1,2})\s*(?:/|DE)\s*(?P<total>\d{1,2})$")
VENCIMENTO = re.compile(r"VENCIMENTO\D{0,15}(\d{2})/(\d{2})/(\d{4})")


# ---------- Gerar faturas fictícias ----------

def _texto_pdf(texto):
    """As fontes padrão do PDF só aceitam o alfabeto latino básico."""
    return texto.encode("latin-1", "replace").decode("latin-1")


def gerar_fatura_pdf(compras, nome, mes):
    """Gera uma fatura fictícia (bytes de um PDF) com as compras no cartão de um mês.

    compras: linhas do extrato com data, descricao, valor (negativo) e parcela.
    """
    periodo = pd.Period(mes, freq="M")
    vencimento = (periodo + 1).to_timestamp() + pd.Timedelta(days=9)
    total = -compras["valor"].sum()

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 10, _texto_pdf("FATURA DO CARTÃO DE CRÉDITO (FICTÍCIA)"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for texto in (
        f"Titular: {nome}",
        f"Período: 01/{periodo.month:02d}/{periodo.year} a {periodo.days_in_month}/{periodo.month:02d}/{periodo.year}",
        f"Vencimento: {vencimento:%d/%m/%Y}",
        f"Total da fatura: {reais(total)}",
    ):
        pdf.cell(0, 6, _texto_pdf(texto), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    for largura, titulo in ((22, "DATA"), (95, "DESCRIÇÃO"), (25, "PARCELA"), (35, "VALOR (R$)")):
        pdf.cell(largura, 7, _texto_pdf(titulo), border="B")
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(22, 6, f"{periodo.start_time:%d/%m}")
    pdf.cell(95, 6, "PAGAMENTO RECEBIDO - OBRIGADO")
    pdf.cell(25, 6, "")
    pdf.cell(35, 6, "-" + reais(total)[3:], align="R", new_x="LMARGIN", new_y="NEXT")
    for compra in compras.sort_values("data", kind="stable").itertuples():
        data = pd.Timestamp(compra.data)
        parcela = compra.parcela if isinstance(compra.parcela, str) and compra.parcela else ""
        if parcela:
            numero, total_parcelas = parcela.split("/")
            parcela = f"{int(numero):02d}/{int(total_parcelas):02d}"
        pdf.cell(22, 6, f"{data:%d/%m}")
        pdf.cell(95, 6, _texto_pdf(str(compra.descricao)[:TAMANHO_DESCRICAO]))
        pdf.cell(25, 6, parcela)
        pdf.cell(35, 6, reais(-compra.valor)[3:], align="R", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


# ---------- Ler faturas ----------

def extrair_texto(conteudo):
    """Texto de todas as páginas de um PDF (recebido como bytes)."""
    with pdfplumber.open(io.BytesIO(conteudo)) as pdf:
        return "\n".join(pagina.extract_text() or "" for pagina in pdf.pages)


def _valor(texto):
    return float(texto.replace(".", "").replace(",", "."))


def _ano_da_compra(mes, ano_escrito, vencimento):
    """Faturas costumam mostrar só dia/mês. O ano vem do vencimento (compras de meses depois dele são do ano anterior)."""
    if ano_escrito:
        ano = int(ano_escrito)
        return ano + 2000 if ano < 100 else ano
    if vencimento is None:
        return None
    mes_venc, ano_venc = vencimento
    return ano_venc if mes <= mes_venc else ano_venc - 1


def ler_linhas(texto, ano_padrao=None):
    """Transforma o texto de uma fatura em compras. Devolve (tabela, quantidade de linhas ignoradas)."""
    achado = VENCIMENTO.search(normalizar_texto(texto))
    vencimento = (int(achado.group(2)), int(achado.group(3))) if achado else None
    compras, ignoradas = [], 0
    for bruta in texto.splitlines():
        linha = normalizar_texto(bruta)
        encontrada = LINHA_DE_COMPRA.match(linha)
        if not encontrada:
            continue
        negativo = any(encontrada.group(nome) for nome in ("sinal", "sinal2", "sinal3"))
        descricao = encontrada.group("meio").strip()
        if negativo or descricao.startswith(PALAVRAS_IGNORADAS):
            ignoradas += 1
            continue
        parcela = ""
        achou_parcela = PARCELA.search(descricao)
        if achou_parcela and 1 <= int(achou_parcela.group("numero")) <= int(achou_parcela.group("total")):
            parcela = f"{int(achou_parcela.group('numero'))}/{int(achou_parcela.group('total'))}"
            descricao = descricao[: achou_parcela.start()].strip()
        mes = int(encontrada.group("mes"))
        ano = _ano_da_compra(mes, encontrada.group("ano"), vencimento) or ano_padrao
        if ano is None:
            ignoradas += 1
            continue
        compras.append({
            "data": f"{ano:04d}-{mes:02d}-{int(encontrada.group('dia')):02d}",
            "descricao": descricao,
            "parcela": parcela,
            "valor": _valor(encontrada.group("valor")),
        })
    return pd.DataFrame(compras, columns=["data", "descricao", "parcela", "valor"]), ignoradas


def ler_fatura_pdf(conteudo, ano_padrao=None):
    """Lê uma fatura em PDF (bytes). Devolve (compras, quantidade de linhas ignoradas)."""
    return ler_linhas(extrair_texto(conteudo), ano_padrao)


def fatura_para_extrato(compras, id_usuario="PDF"):
    """Converte as compras lidas para o formato do extrato usado pelo sistema."""
    return pd.DataFrame({
        "id_transacao": [f"F{i:05d}" for i in range(1, len(compras) + 1)],
        "id_usuario": id_usuario,
        "data": compras["data"].values,
        "descricao": compras["descricao"].values,
        "valor": -compras["valor"].values,
        "meio": "cartao_credito",
        "conta": "cartao",
        "parcela": compras["parcela"].values,
    })


def compras_no_cartao(extrato, id_usuario, mes):
    """Compras no cartão de um usuário num mês (o que vai para a fatura daquele mês)."""
    filtro = (extrato["id_usuario"] == id_usuario) & (extrato["meio"] == "cartao_credito") & (extrato["data"].str[:7] == mes)
    return extrato[filtro]


def ler_faturas_do_conjunto(extrato, usuarios):
    """Gera a fatura em PDF de cada usuário em cada mês e lê de volta (teste de ida e volta).

    Cada compra lida recebe o id da transação que a originou (id_origem), para conferir com a verdade.
    """
    nomes = usuarios.set_index("id_usuario")["nome"]
    meses = sorted(extrato["data"].str[:7].unique())
    partes = []
    for usuario in nomes.index:
        for mes in meses:
            compras = compras_no_cartao(extrato, usuario, mes).sort_values("data", kind="stable")
            if compras.empty:
                continue
            lidas, _ = ler_fatura_pdf(gerar_fatura_pdf(compras, nomes[usuario], mes))
            mesma_quantidade = len(lidas) == len(compras)
            partes.append(lidas.assign(
                id_usuario=usuario,
                mes_fatura=mes,
                id_origem=compras["id_transacao"].values if mesma_quantidade else None,
            ))
    return pd.concat(partes, ignore_index=True)
