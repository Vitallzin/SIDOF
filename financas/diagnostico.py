"""Indicadores e diagnóstico (Fase 6).

Junta tudo o que as fases anteriores descobriram e mostra, para cada usuário,
para onde foi o dinheiro em média por mês, como isso mudou e o que já está comprometido.

Para não contar o mesmo dinheiro duas vezes:
- transferências entre contas próprias não são gasto nem renda
- o pagamento da fatura não é gasto (as compras do cartão já foram contadas uma a uma)
- toda linha com parcela (compra parcelada ou dívida) vai para o bloco "parcelas e dívidas"
"""

import pandas as pd

from financas.categorias import CATEGORIAS
from financas.formatacao import mes_por_extenso, reais
from financas.parcelas import comprometimento_da_renda, compromissos_futuros, identificar_parcelamentos
from financas.regras import CONFIANCA_MINIMA
from financas.renda import CATEGORIAS_RENDA_EFETIVA, classificar_entradas, perfil_de_renda, transferencias_por_par

# Blocos do diagnóstico, na ordem em que aparecem: (nome, rótulo para o usuário)
BLOCOS = [
    ("essenciais", "Essenciais (moradia, contas, mercado, transporte)"),
    ("prioritarios", "Prioritários (educação, saúde, dívidas avulsas)"),
    ("discricionarios", "Discricionários (restaurantes, lazer, compras...)"),
    ("parcelas", "Parcelas e dívidas"),
    ("a_confirmar", "A confirmar (sem categoria ainda)"),
]
NOMES_BLOCOS = [nome for nome, _ in BLOCOS]
GRUPO_PARA_BLOCO = {"essencial": "essenciais", "prioritario": "prioritarios", "discricionario": "discricionarios"}
FORA_DOS_GASTOS = ("transferencia_interna", "pagamento_fatura")

# Limites dos "pontos de atenção" (escolhas de projeto, ajustáveis)
VARIACAO_ESTAVEL = 0.05  # mudanças menores que 5% contam como "estável"
AUMENTO_RELEVANTE = 0.20
SOBRA_BAIXA = 0.10
A_CONFIRMAR_RELEVANTE = 0.10


def _bloco(categoria, parcela):
    if categoria in FORA_DOS_GASTOS:
        return None
    if parcela:
        return "parcelas"
    return GRUPO_PARA_BLOCO.get(CATEGORIAS.get(categoria), "a_confirmar")


def saidas_pelas_regras(classificado):
    """Saídas com a categoria das regras; o que vai virar pergunta fica como 'não identificado'."""
    saidas = classificado[classificado["direcao"] == "saida"].copy()
    saidas["categoria_final"] = saidas["categoria_regra"].where(saidas["confianca"] >= CONFIANCA_MINIMA, "nao_identificado")
    return saidas


def gastos_por_bloco(saidas, meses, coluna_categoria="categoria_final"):
    """Tabela longa: usuário, mês, bloco e valor gasto (positivo)."""
    tabela = saidas.assign(
        bloco=[_bloco(categoria, parcela) for categoria, parcela in zip(saidas[coluna_categoria], saidas["parcela"].fillna(""))],
        gasto=-saidas["valor"],
    ).dropna(subset=["bloco"])
    soma = tabela.groupby(["id_usuario", "mes", "bloco"])["gasto"].sum()
    usuarios = sorted(saidas["id_usuario"].unique())
    completo = pd.MultiIndex.from_product([usuarios, meses, NOMES_BLOCOS], names=["id_usuario", "mes", "bloco"])
    return soma.reindex(completo, fill_value=0).rename("valor").reset_index()


def renda_por_mes(entradas, meses):
    """Renda efetiva (salário + trabalho) de cada usuário em cada mês."""
    efetiva = entradas[entradas["categoria_renda"].isin(CATEGORIAS_RENDA_EFETIVA)]
    tabela = efetiva.pivot_table(index="id_usuario", columns="mes", values="valor", aggfunc="sum", fill_value=0)
    return tabela.reindex(index=sorted(entradas["id_usuario"].unique()), columns=meses, fill_value=0)


def movimentos_da_poupanca(classificado):
    """Transferências entre contas próprias do lado da poupança (+ entrou, - saiu)."""
    internas = classificado["regra"].isin(["transferencia_propria", "pix_proprio_nome"]) | classificado["id_transacao"].isin(
        transferencias_por_par(classificado)
    )
    return classificado[internas & (classificado["conta"] == "poupanca")]


def poupanca_por_usuario(classificado):
    """Saldo líquido que foi para a poupança via transferências entre contas próprias."""
    return movimentos_da_poupanca(classificado).groupby("id_usuario")["valor"].sum()


def _variacao(antes, depois):
    return (depois - antes) / antes if antes > 0 else 0.0


def outras_entradas_por_usuario(entradas):
    """Ajudas e entradas de origem não identificada: entram dinheiro, mas não contam como renda."""
    outras = entradas[entradas["categoria_renda"].isin(["renda_eventual", "renda_nao_identificada"])]
    return outras.groupby("id_usuario")["valor"].sum()


def indicadores(gastos, renda, perfis, comprometimento, poupanca, outras_entradas, meses):
    """Uma linha por usuário com os números do diagnóstico (médias mensais)."""
    metade = len(meses) // 2
    primeiros, ultimos = meses[:metade], meses[metade:]
    perfis = perfis.set_index("id_usuario")
    comprometimento = comprometimento.set_index("id_usuario")
    linhas = []
    for usuario in renda.index:
        do_usuario = gastos[gastos["id_usuario"] == usuario]
        por_bloco = do_usuario.groupby("bloco")["valor"].sum() / len(meses)
        por_mes = do_usuario.groupby("mes")["valor"].sum()
        renda_media = renda.loc[usuario].mean()
        gastos_total = por_bloco.sum()
        bloco_antes = do_usuario[do_usuario["mes"].isin(primeiros)].groupby("bloco")["valor"].sum()
        bloco_depois = do_usuario[do_usuario["mes"].isin(ultimos)].groupby("bloco")["valor"].sum()
        linha = {
            "id_usuario": usuario,
            "tipo_renda": perfis.loc[usuario, "tipo_renda"],
            "renda_media": round(renda_media, 2),
            "renda_referencia": perfis.loc[usuario, "renda_referencia"],
            "variacao_renda": perfis.loc[usuario, "variacao"],
            **{bloco: round(por_bloco.get(bloco, 0.0), 2) for bloco in NOMES_BLOCOS},
            "gastos_total": round(gastos_total, 2),
            "sobra_media": round(renda_media - gastos_total, 2),
            "taxa_de_sobra": round((renda_media - gastos_total) / renda_media, 3) if renda_media > 0 else 0.0,
            "variacao_gastos": round(_variacao(por_mes[primeiros].sum(), por_mes[ultimos].sum()), 3),
            **{
                f"variacao_{bloco}": round(_variacao(bloco_antes.get(bloco, 0), bloco_depois.get(bloco, 0)), 3)
                for bloco in NOMES_BLOCOS
            },
            "outras_entradas_por_mes": round(outras_entradas.get(usuario, 0.0) / len(meses), 2),
            "poupanca_por_mes": round(poupanca.get(usuario, 0.0) / len(meses), 2),
            "comprometido_proximo_mes": comprometimento.loc[usuario, "comprometido_proximo_mes"],
            "percentual_comprometido": comprometimento.loc[usuario, "percentual_da_renda"],
            "alto_comprometimento": comprometimento.loc[usuario, "alto_comprometimento"],
        }
        linhas.append(linha)
    return pd.DataFrame(linhas)


def _sentido(variacao):
    if abs(variacao) < VARIACAO_ESTAVEL:
        return "ficaram estáveis"
    return f"subiram {variacao:.0%}" if variacao > 0 else f"caíram {-variacao:.0%}"


def _maior_categoria_discricionaria(saidas, usuario, meses, coluna_categoria):
    """Categoria discricionária que mais cresceu do 1º para o 2º trimestre."""
    metade = len(meses) // 2
    discricionarias = saidas[
        (saidas["id_usuario"] == usuario)
        & (saidas[coluna_categoria].map(CATEGORIAS) == "discricionario")
        & (saidas["parcela"].fillna("") == "")
    ]
    antes = discricionarias[discricionarias["mes"].isin(meses[:metade])].groupby(coluna_categoria)["valor"].sum()
    depois = discricionarias[discricionarias["mes"].isin(meses[metade:])].groupby(coluna_categoria)["valor"].sum()
    indice = antes.index.union(depois.index)
    # Saídas são negativas: gasto a mais no 2º trimestre = antes - depois
    aumento = antes.reindex(indice, fill_value=0) - depois.reindex(indice, fill_value=0)
    if aumento.empty or aumento.max() <= 0:
        return None
    return aumento.idxmax().replace("_", " "), aumento.max() / metade


def _pontos_de_atencao(linha, perfil, a_confirmar_pct):
    pontos = []
    if linha["sobra_media"] < 0:
        pontos.append(f"Em média, as saídas superaram a renda efetiva em {reais(-linha['sobra_media'])} por mês.")
    elif linha["taxa_de_sobra"] < SOBRA_BAIXA:
        pontos.append(f"Baixa capacidade de reserva: a sobra média foi {linha['taxa_de_sobra']:.0%} da renda.")
    if linha["alto_comprometimento"]:
        pontos.append(f"Alto comprometimento da renda: {linha['percentual_comprometido']:.0%} já está reservado para parcelas no próximo mês.")
    if linha["tipo_renda"] != "fixa":
        pontos.append(f"Renda com alta variação: o menor mês foi {reais(perfil['minima'])}, contra média de {reais(perfil['media'])}.")
    if perfil["troca_emprego"]:
        pontos.append("Houve período sem salário por causa da troca de emprego.")
    if linha["variacao_discricionarios"] > AUMENTO_RELEVANTE:
        pontos.append(f"Aumento dos gastos discricionários: {linha['variacao_discricionarios']:.0%} a mais no último trimestre.")
    if a_confirmar_pct > A_CONFIRMAR_RELEVANTE:
        pontos.append(f"{a_confirmar_pct:.0%} dos gastos ainda não têm categoria; confirmar essas transações deixa o diagnóstico mais preciso.")
    return pontos


def texto_diagnostico(linha, perfil, comprometimento, saidas, meses, coluna_categoria="categoria_final"):
    """Relatório em texto, neutro, de um usuário."""
    base = linha["renda_media"] if linha["renda_media"] > 0 else 1
    periodo = f"{mes_por_extenso(meses[0]).split()[0]} a {mes_por_extenso(meses[-1])}"
    linhas = [f"=== Diagnóstico de {linha['id_usuario']} ({periodo}) ===", f"Renda: {perfil['explicacao']}", ""]
    linhas.append("Para onde foi o dinheiro (média por mês, % da renda efetiva):")
    for nome, rotulo in BLOCOS:
        linhas.append(f"  {rotulo:<52} {reais(linha[nome]):>14}  {linha[nome] / base:>4.0%}")
    linhas.append(f"  {'Sobra (renda efetiva - gastos)':<52} {reais(linha['sobra_media']):>14}  {linha['sobra_media'] / base:>4.0%}")
    if linha["outras_entradas_por_mes"] > 0:
        linhas.append(
            f"Além da renda efetiva, entraram em média {reais(linha['outras_entradas_por_mes'])} por mês "
            "de ajudas ou de origem não identificada (não contam como renda)."
        )
    linhas.append("")

    metade = len(meses) // 2
    trimestre_1 = f"{mes_por_extenso(meses[0]).split()[0]}–{mes_por_extenso(meses[metade - 1]).split()[0]}"
    trimestre_2 = f"{mes_por_extenso(meses[metade]).split()[0]}–{mes_por_extenso(meses[-1]).split()[0]}"
    evolucao = f"Evolução: comparando {trimestre_2} com {trimestre_1}, os gastos totais {_sentido(linha['variacao_gastos'])}"
    mudancas = [
        f"{rotulo.split(' (')[0].lower()} {_sentido(linha[f'variacao_{nome}'])}"
        for nome, rotulo in BLOCOS[:4]
        if abs(linha[f"variacao_{nome}"]) >= VARIACAO_ESTAVEL
    ]
    evolucao += f" ({'; '.join(mudancas)})." if mudancas else "."
    maior = _maior_categoria_discricionaria(saidas, linha["id_usuario"], meses, coluna_categoria)
    if maior and linha["variacao_discricionarios"] >= VARIACAO_ESTAVEL:
        evolucao += f" O que mais cresceu foi {maior[0]}: cerca de {reais(maior[1])} a mais por mês."
    linhas += [evolucao, "", f"Compromissos futuros: {comprometimento['explicacao']}"]

    if linha["poupanca_por_mes"] > 0:
        linhas.append(f"Reserva: em média {reais(linha['poupanca_por_mes'])} por mês foram para a poupança.")
    else:
        linhas.append("Reserva: no período não houve saldo líquido transferido para a poupança.")

    a_confirmar_pct = linha["a_confirmar"] / linha["gastos_total"] if linha["gastos_total"] > 0 else 0
    pontos = _pontos_de_atencao(linha, perfil, a_confirmar_pct)
    linhas += ["", "Pontos de atenção:"] + ([f"  - {ponto}" for ponto in pontos] or ["  - Nenhum ponto de atenção no período."])
    linhas += [
        "",
        "De onde vêm os números: renda efetiva = salário e pagamentos por trabalho (sem ajudas nem entradas "
        "não identificadas). Gastos não incluem transferências entre suas contas nem o pagamento da fatura, "
        "porque as compras do cartão já foram contadas uma a uma. 'A confirmar' são transações que o sistema vai perguntar a você.",
    ]
    return "\n".join(linhas)


def diagnosticar(classificado, usuarios, saidas=None, coluna_categoria="categoria_final"):
    """Roda renda, parcelas e diagnóstico. Sem 'saidas', usa só as regras para categorizar os gastos.

    Devolve (tabela de indicadores, dicionário {usuário: texto}).
    """
    meses = sorted(classificado["mes"].unique())
    saidas = saidas_pelas_regras(classificado) if saidas is None else saidas
    entradas = classificar_entradas(classificado, usuarios)
    perfis = perfil_de_renda(entradas, meses)
    parcelamentos = identificar_parcelamentos(classificado)
    compromissos = compromissos_futuros(parcelamentos, sorted(classificado["id_usuario"].unique()), meses[-1])
    comprometimento = comprometimento_da_renda(parcelamentos, compromissos, perfis)

    gastos = gastos_por_bloco(saidas, meses, coluna_categoria)
    tabela = indicadores(
        gastos, renda_por_mes(entradas, meses), perfis, comprometimento,
        poupanca_por_usuario(classificado), outras_entradas_por_usuario(entradas), meses,
    )
    perfis_por_id = perfis.set_index("id_usuario")
    comprometimento_por_id = comprometimento.set_index("id_usuario")
    textos = {
        linha["id_usuario"]: texto_diagnostico(
            linha, perfis_por_id.loc[linha["id_usuario"]], comprometimento_por_id.loc[linha["id_usuario"]], saidas, meses, coluna_categoria
        )
        for linha in tabela.to_dict("records")
    }
    return tabela, textos
