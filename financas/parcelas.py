"""Parcelas e compromissos futuros (Fase 5).

Uma compra parcelada aparece no extrato uma vez por mês, com o mesmo texto e "3/12" na
coluna parcela. O sistema junta essas linhas para saber:
- o valor total da compra (parcela x número de parcelas)
- quanto já foi pago e quanto falta
- até quando a parcela vai ocupar a renda
Dívidas pagas por boleto com número de parcela (empréstimos, financiamentos) entram do mesmo jeito.
"""

import pandas as pd

from financas.formatacao import mes_por_extenso, reais

MESES_A_FRENTE = 12
# Escolha de projeto (ajustável): a partir de 30% da renda em parcelas, o texto avisa
# "alto comprometimento da renda"
LIMITE_COMPROMETIMENTO_ALTO = 0.30

COLUNAS_PARCELAMENTOS = [
    "id_usuario", "descricao", "total_parcelas", "valor_parcela", "meio", "contraparte", "primeira_vista",
    "ultima_paga", "mes_ultima", "tipo", "valor_total", "parcelas_restantes", "valor_restante",
    "mes_final", "comecou_antes", "explicacao",
]


def _tipo(meio):
    return "compra parcelada no cartão" if meio == "cartao_credito" else "dívida/financiamento"


def _explicar(linha):
    if linha["meio"] == "cartao_credito":
        texto = f"{linha['contraparte']}: compra de {reais(linha['valor_total'])} em {linha['total_parcelas']}x de {reais(linha['valor_parcela'])}."
    else:
        texto = (
            f"{linha['contraparte']}: {linha['total_parcelas']} parcelas de {reais(linha['valor_parcela'])} "
            f"({reais(linha['valor_total'])} no total)."
        )
    if linha["parcelas_restantes"] == 0:
        return texto + " Já quitada."
    falta = "Falta" if linha["parcelas_restantes"] == 1 else "Faltam"
    return texto + (
        f" Pagas: {linha['ultima_paga']}. {falta} {linha['parcelas_restantes']} "
        f"({reais(linha['valor_restante'])}), até {mes_por_extenso(linha['mes_final'])}."
    )


def identificar_parcelamentos(classificado):
    """Uma linha por compra parcelada ou dívida, a partir das linhas com 'k/n' no extrato."""
    parceladas = classificado[classificado["parcela_total"].notna() & (classificado["valor"] < 0)]
    parceladas = parceladas.assign(valor_parcela=-parceladas["valor"])
    # A mesma compra repete o texto, o número total de parcelas e o valor da parcela
    chave = ["id_usuario", "descricao", "parcela_total", "valor_parcela"]
    tabela = parceladas.groupby(chave).agg(
        meio=("meio", "first"),
        contraparte=("contraparte", "first"),
        primeira_vista=("parcela_numero", "min"),
        ultima_paga=("parcela_numero", "max"),
        mes_ultima=("mes", "max"),
    ).reset_index()
    if tabela.empty:
        # Sem parcelas: tabela vazia, mas com as mesmas colunas, para as próximas contas funcionarem
        return pd.DataFrame(columns=COLUNAS_PARCELAMENTOS)

    tabela = tabela.rename(columns={"parcela_total": "total_parcelas"})
    tabela["total_parcelas"] = tabela["total_parcelas"].astype(int)
    tabela["ultima_paga"] = tabela["ultima_paga"].astype(int)
    tabela["tipo"] = tabela["meio"].map(_tipo)
    tabela["valor_total"] = (tabela["valor_parcela"] * tabela["total_parcelas"]).round(2)
    tabela["parcelas_restantes"] = tabela["total_parcelas"] - tabela["ultima_paga"]
    tabela["valor_restante"] = (tabela["valor_parcela"] * tabela["parcelas_restantes"]).round(2)
    tabela["mes_final"] = [
        str(pd.Period(mes, freq="M") + restantes)
        for mes, restantes in zip(tabela["mes_ultima"], tabela["parcelas_restantes"])
    ]
    tabela["comecou_antes"] = tabela["primeira_vista"] > 1  # 1ª parcela antes do período analisado
    tabela["explicacao"] = tabela.apply(_explicar, axis=1)
    return tabela


def proximos_meses(mes_atual, quantidade=MESES_A_FRENTE):
    inicio = pd.Period(mes_atual, freq="M") + 1
    return [str(inicio + i) for i in range(quantidade)]


def compromissos_futuros(parcelamentos, usuarios, mes_atual):
    """Tabela usuário x próximos 12 meses com o valor já comprometido com parcelas."""
    meses = proximos_meses(mes_atual)
    linhas = []
    for item in parcelamentos[parcelamentos["parcelas_restantes"] > 0].itertuples():
        for passo in range(1, item.parcelas_restantes + 1):
            mes = str(pd.Period(item.mes_ultima, freq="M") + passo)
            if mes in meses:
                linhas.append({"id_usuario": item.id_usuario, "mes": mes, "valor": item.valor_parcela})
    tabela = pd.DataFrame(linhas, columns=["id_usuario", "mes", "valor"])
    por_mes = tabela.pivot_table(index="id_usuario", columns="mes", values="valor", aggfunc="sum", fill_value=0)
    return por_mes.reindex(index=list(usuarios), columns=meses, fill_value=0).round(2)


def comprometimento_da_renda(parcelamentos, compromissos, perfis):
    """Por usuário: quanto da renda de referência já está comprometido no próximo mês."""
    referencia = perfis.set_index("id_usuario")["renda_referencia"]
    proximo_mes = compromissos.columns[0]
    linhas = []
    for usuario in compromissos.index:
        ativos = parcelamentos[(parcelamentos["id_usuario"] == usuario) & (parcelamentos["parcelas_restantes"] > 0)]
        valor_proximo = compromissos.loc[usuario, proximo_mes]
        renda = referencia.get(usuario, 0)
        percentual = valor_proximo / renda if renda > 0 else 0.0
        linha = {
            "id_usuario": usuario,
            "parcelamentos_ativos": len(ativos),
            "comprometido_proximo_mes": round(valor_proximo, 2),
            "renda_referencia": renda,
            "percentual_da_renda": round(percentual, 3),
            "total_restante": round(ativos["valor_restante"].sum(), 2),
            "ultimo_mes_com_parcela": ativos["mes_final"].max() if len(ativos) else "",
            "alto_comprometimento": percentual >= LIMITE_COMPROMETIMENTO_ALTO,
        }
        linha["explicacao"] = _explicar_comprometimento(linha, proximo_mes)
        linhas.append(linha)
    return pd.DataFrame(linhas)


def _explicar_comprometimento(linha, proximo_mes):
    if linha["parcelamentos_ativos"] == 0:
        return "Nenhuma parcela em aberto: a renda futura não está comprometida com parcelamentos."
    texto = (
        f"Em {mes_por_extenso(proximo_mes)}, {reais(linha['comprometido_proximo_mes'])} "
        f"({linha['percentual_da_renda']:.0%} da renda de referência) já estão comprometidos com "
        f"{linha['parcelamentos_ativos']} parcelamento(s). No total faltam {reais(linha['total_restante'])}; "
        f"a última parcela é em {mes_por_extenso(linha['ultimo_mes_com_parcela'])}."
    )
    if linha["alto_comprometimento"]:
        texto += " Isso indica alto comprometimento da renda."
    return texto
