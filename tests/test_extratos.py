"""Testes dos extratos de conta (PDF e CSV), da junção dos documentos e da comparação com o banco."""

import pandas as pd
import pytest
from fpdf import FPDF

from financas.comparacao_banco import comparar_com_banco
from financas.documentos import extrato_de_documentos
from financas.extratos import EXTRATO, FATURA, Documento, ler_csv, ler_documento, numero
from financas.faturas_pdf import ID_FATURA
from financas.normalizacao import separar_operacao
from financas.sistema import Sistema, treinar_modelo_da_base

# Extrato fictício: (data, descrição, tipo, categoria do banco, valor com sinal)
MOVIMENTOS = [
    ("02/06", "POSTO SHELL", "Debito cartao", "Transporte", -92.79),
    ("05/06", "SALARIO EMPRESA TESTE LTDA", "Credito salario", "Salario", 5000.00),
    ("10/06", "PIX ENVIADO - ROBERTO LIMA (ALUGUEL)", "Pix enviado", "Moradia", -1200.00),
    ("12/06", "SUPERMERCADO BOM PRECO", "Debito cartao", "Mercado", -310.50),
    ("17/06", "PIX RECEBIDO - MARIANA TESTE", "Pix recebido", "Transferencia recebida", 368.01),
    ("20/06", "APLICACAO RESERVA CDB", "Aplicacao", "Investimento", -200.00),
    ("28/06", "RENDIMENTO RESERVA CDB", "Rendimento", "Rendimentos", 1.70),
    ("03/07", "IPVA 2026 - PARCELA 1/3", "Pix enviado", "Impostos", -215.00),
    ("05/07", "SALARIO EMPRESA TESTE LTDA", "Credito salario", "Salario", 5000.00),
    ("10/07", "PAGAMENTO FATURA CARTAO", "Pagamento", "Cartao de credito", -850.00),
    ("12/07", "SUPERMERCADO BOM PRECO", "Debito cartao", "Mercado", -290.00),
]
SALDO_INICIAL = 1000.00


def _reais(valor):
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pdf_de_extrato(layout):
    """Gera um extrato fictício em PDF em 3 formatos: 'sinal', 'colunas' (Entrada/Saída) e 'saldo' (Valor + Saldo, sem sinal)."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=8)
    pdf.cell(0, 6, "Extrato de Conta Corrente (dados ficticios)", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "Periodo: 01/06/2026 a 31/07/2026", new_x="LMARGIN", new_y="NEXT")
    if layout == "sinal":
        larguras, titulos = (20, 110, 30), ("Data", "Descricao", "Valor")
    elif layout == "colunas":
        larguras, titulos = (14, 70, 28, 30, 24, 24), ("Data", "Descricao", "Tipo", "Categoria", "Entrada", "Saida")
    else:
        larguras, titulos = (16, 100, 30, 30), ("Data", "Descricao", "Valor", "Saldo")
        pdf.cell(0, 6, f"Saldo inicial: R$ {_reais(SALDO_INICIAL)}", new_x="LMARGIN", new_y="NEXT")
    for largura, titulo in zip(larguras, titulos):
        pdf.cell(largura, 6, titulo, align="R" if titulo in ("Valor", "Entrada", "Saida", "Saldo") else "L")
    pdf.ln()
    saldo = SALDO_INICIAL
    for data, descricao, tipo, categoria, valor in MOVIMENTOS:
        saldo += valor
        if layout == "sinal":
            celulas = (data + "/2026", descricao, _reais(valor) if valor > 0 else "-" + _reais(-valor))
        elif layout == "colunas":
            celulas = (data, descricao, tipo, categoria, _reais(valor) if valor > 0 else "", _reais(-valor) if valor < 0 else "")
        else:
            celulas = (data, descricao, _reais(abs(valor)), _reais(saldo))
        for indice, (largura, texto) in enumerate(zip(larguras, celulas)):
            numerica = titulos[indice] in ("Valor", "Entrada", "Saida", "Saldo")
            pdf.cell(largura, 6, texto, align="R" if numerica else "L")
        pdf.ln()
    return bytes(pdf.output())


@pytest.fixture(scope="module")
def modelo():
    return treinar_modelo_da_base()


# ---------- Leitura ----------

def test_numero_entende_varios_formatos():
    assert numero("1.234,56") == 1234.56
    assert numero("-92,79") == -92.79
    assert numero("R$ 5.000,00") == 5000.0
    assert numero("1234.56") == 1234.56
    assert numero("1,234.56") == 1234.56
    assert numero("92,79 D") == -92.79
    assert numero("5.000,00 C") == 5000.0
    assert numero("(10,00)") == -10.0
    assert numero("abc") is None


@pytest.mark.parametrize("layout", ["sinal", "colunas", "saldo"])
def test_extrato_em_pdf_separa_entradas_e_saidas(layout):
    documento = ler_documento(_pdf_de_extrato(layout), f"extrato_{layout}.pdf")
    assert documento.tipo == EXTRATO
    assert documento.ficticio
    movimentos = documento.movimentos
    assert len(movimentos) == len(MOVIMENTOS)
    assert documento.ignoradas == 0
    assert list(movimentos["valor"]) == pytest.approx([m[4] for m in MOVIMENTOS])
    assert list(movimentos["data"].str[:7]) == ["2026-06"] * 7 + ["2026-07"] * 4  # ano vem do período


def test_extrato_com_colunas_guarda_tipo_e_categoria_do_banco():
    movimentos = ler_documento(_pdf_de_extrato("colunas"), "extrato.pdf").movimentos
    salario = movimentos[movimentos["descricao"].str.startswith("SALARIO")].iloc[0]
    assert salario["categoria_banco"] == "Salario"
    assert salario["tipo_banco"] == "Credito salario"
    assert salario["descricao"] == "SALARIO EMPRESA TESTE LTDA"


def test_parcela_escrita_na_descricao_vira_parcela():
    movimentos = ler_documento(_pdf_de_extrato("sinal"), "extrato.pdf").movimentos
    ipva = movimentos[movimentos["descricao"].str.startswith("IPVA")].iloc[0]
    assert ipva["parcela"] == "1/3"
    assert "PARCELA" not in ipva["descricao"]


def test_csv_com_valor_com_sinal_e_virgula_decimal():
    conteudo = "Data;Descrição;Valor\n05/06/2026;SALARIO EMPRESA;5.000,00\n06/06/2026;PADARIA;-12,50\n".encode("utf-8")
    documento = ler_csv(conteudo, "extrato.csv")
    assert documento.tipo == EXTRATO
    assert list(documento.movimentos["valor"]) == [5000.0, -12.5]


def test_csv_com_entrada_e_saida_separadas_em_latin1_e_linhas_de_apresentacao():
    texto = (
        "Banco Ficticio S.A.\nExtrato de conta\n\n"
        "Data,Histórico,Crédito,Débito,Saldo\n"
        "2026-06-05,SALARIO EMPRESA,5000.00,,6000.00\n"
        "2026-06-06,PADARIA,,12.50,5987.50\n"
    )
    documento = ler_csv(texto.encode("latin-1"), "extrato.csv")
    assert documento.tipo == EXTRATO
    assert list(documento.movimentos["valor"]) == [5000.0, -12.5]
    assert list(documento.movimentos["data"]) == ["2026-06-05", "2026-06-06"]


def test_csv_com_coluna_credito_debito():
    texto = "Data;Descricao;Valor;Tipo\n05/06/2026;SALARIO;5000,00;C\n06/06/2026;PADARIA;12,50;D\n"
    documento = ler_csv(texto.encode("utf-8"), "conta.csv")
    assert list(documento.movimentos["valor"]) == [5000.0, -12.5]


def test_csv_de_fatura_tem_compras_positivas():
    texto = "date,title,amount\n2026-06-02,IFOOD,45.90\n2026-06-03,NETFLIX,39.90\n2026-06-10,Pagamento recebido,-85.80\n"
    documento = ler_csv(texto.encode("utf-8"), "nubank-2026-06.csv")
    assert documento.tipo == FATURA
    assert list(documento.movimentos["valor"]) == [45.9, 39.9]
    assert documento.ignoradas == 1


def test_csv_sem_cabecalho_reconhecivel_fica_vazio():
    documento = ler_csv(b"a;b;c\n1;2;3\n", "qualquer.csv")
    assert documento.vazio


def test_pix_com_traco_separa_o_nome_da_pessoa():
    assert separar_operacao("PIX ENVIADO - MARIA SOUZA") == ("pix_enviado", "MARIA SOUZA")


# ---------- Junção dos documentos ----------

def _extrato(layout="sinal"):
    return ler_documento(_pdf_de_extrato(layout), f"extrato_{layout}.pdf")


def test_renda_digitada_nao_duplica_salario_do_extrato(modelo):
    extrato, usuarios, avisos = extrato_de_documentos([_extrato()], "CARLOS", renda_mensal=5000)
    assert not extrato["descricao"].str.contains("RENDA INFORMADA").any()
    assert any("já mostra renda" in aviso for aviso in avisos)
    linha = Sistema(extrato, usuarios, modelo).diagnosticar()[0].set_index("id_usuario").loc[ID_FATURA]
    assert linha["renda_media"] == pytest.approx(5000)  # rendimento e PIX recebido não contam como renda


def test_renda_digitada_entra_so_nos_meses_sem_renda():
    sem_salario_em_julho = Documento(
        "extrato.csv", EXTRATO,
        ler_csv(
            "Data;Descricao;Valor\n05/06/2026;SALARIO EMPRESA;5000,00\n06/06/2026;PADARIA;-12,50\n06/07/2026;PADARIA;-15,00\n".encode(),
            "extrato.csv",
        ).movimentos,
        0, True,
    )
    extrato, _, avisos = extrato_de_documentos([sem_salario_em_julho], "CARLOS", renda_mensal=4000)
    informada = extrato[extrato["descricao"].str.contains("RENDA INFORMADA")]
    assert list(informada["data"].str[:7]) == ["2026-07"]
    assert "1 mês(es) sem renda" in avisos[0]


def test_mesmo_extrato_em_formatos_diferentes_conta_uma_vez():
    um, _, _ = extrato_de_documentos([_extrato("sinal")], "CARLOS")
    tres, _, _ = extrato_de_documentos([_extrato("sinal"), _extrato("colunas"), _extrato("saldo")], "CARLOS")
    assert len(tres) == len(um)


def test_repeticao_dentro_do_mesmo_arquivo_continua():
    texto = "Data;Descricao;Valor\n05/06/2026;IFOOD;-30,00\n05/06/2026;IFOOD;-30,00\n"
    documento = ler_csv(texto.encode(), "extrato.csv")
    extrato, _, _ = extrato_de_documentos([documento], "CARLOS")
    assert len(extrato) == 2  # pode ser uma cobrança duplicada: a pessoa precisa ver


def test_pagamento_de_fatura_nao_conta_como_gasto_e_gera_aviso(modelo):
    extrato, usuarios, avisos = extrato_de_documentos([_extrato()], "CARLOS")
    assert any("pagamentos de fatura" in aviso and "envie também as faturas" in aviso for aviso in avisos)
    saidas = Sistema(extrato, usuarios, modelo).saidas()
    fatura = saidas[saidas["descricao"] == "PAGAMENTO FATURA CARTAO"].iloc[0]
    assert fatura["categoria_final"] == "pagamento_fatura"


def test_extrato_e_fatura_juntos_avisam_que_o_pagamento_nao_foi_somado():
    fatura = Documento(
        "fatura.pdf", FATURA,
        pd.DataFrame({"data": ["2026-07-02"], "descricao": ["IFOOD"], "parcela": [""], "valor": [850.0]}), 1, True,
    )
    _, _, avisos = extrato_de_documentos([_extrato(), fatura], "CARLOS")
    assert any("não foram somados" in aviso for aviso in avisos)


def test_aplicacao_conta_como_reserva_e_nao_como_gasto(modelo):
    extrato, usuarios, _ = extrato_de_documentos([_extrato()], "CARLOS")
    linha = Sistema(extrato, usuarios, modelo).diagnosticar()[0].set_index("id_usuario").loc[ID_FATURA]
    assert linha["poupanca_por_mes"] == pytest.approx(100)  # 200 em 2 meses
    saidas = Sistema(extrato, usuarios, modelo).saidas()
    aplicacao = saidas[(saidas["descricao"] == "APLICACAO RESERVA CDB") & (saidas["conta"] == "corrente")].iloc[0]
    assert aplicacao["categoria_final"] == "guardar_investir"


# ---------- Comparação com o banco ----------

def test_comparacao_com_a_categoria_do_banco(modelo):
    extrato, usuarios, _ = extrato_de_documentos([_extrato("colunas")], "CARLOS")
    comparacao = comparar_com_banco(Sistema(extrato, usuarios, modelo).saidas())
    assert comparacao is not None
    # Posto, mercado (2x), aluguel, aplicação, pagamento da fatura e IPVA ("Impostos" no banco) têm equivalente
    assert comparacao["comparaveis"] + comparacao["pendentes"] == 7
    assert comparacao["categorias_sem_equivalente"] == []
    assert comparacao["concordam"] == comparacao["comparaveis"]  # todas resolvidas por regras claras
    assert comparacao["taxa"] == 1.0


def test_sem_categoria_do_banco_nao_ha_comparacao(modelo):
    extrato, usuarios, _ = extrato_de_documentos([_extrato("sinal")], "CARLOS")
    assert comparar_com_banco(Sistema(extrato, usuarios, modelo).saidas()) is None
