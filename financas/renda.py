"""Renda e transferências internas (Fase 4).

Nem toda entrada de dinheiro é renda. Para cada entrada o sistema decide entre:
- transferencia_interna: dinheiro do próprio usuário mudando de conta
- renda_fixa: salário
- renda_variavel: pagamento por trabalho ou serviço (clientes de autônomo, empresas)
- renda_eventual: ajuda pontual, por exemplo da família
- renda_nao_identificada: origem desconhecida (nunca tratada como irregularidade)

Depois, com a renda efetiva (fixa + variável), calcula o perfil de renda de cada
usuário: média, menor mês, maior mês e variação mensal.
"""

import pandas as pd

from financas.formatacao import mes_por_extenso, reais
from financas.normalizacao import normalizar_texto
from financas.regras import CONFIANCA_MINIMA, MARCAS_DE_EMPRESA, REGRAS_INTERNAS

# Palavras comuns em nomes de empresas (além de LTDA, ME, SA...)
PALAVRAS_DE_EMPRESA = set(MARCAS_DE_EMPRESA) | {
    "COMERCIO", "CONSTRUTORA", "ESCRITORIO", "AGENCIA", "STUDIO", "EVENTOS",
    "CONSULTORIA", "INDUSTRIA", "DISTRIBUIDORA", "ASSOCIACAO", "INSTITUTO",
}
LIMITE_RENDA_FIXA = 0.10  # variação mensal até 10% = renda fixa
VARIACAO_DE_CLIENTE = 0.25  # valores de uma mesma fonte que variam mais que isso parecem pagamentos por serviço
MINIMO_FONTES_AUTONOMO = 3  # sem salário e com 3+ fontes pagadoras = perfil de autônomo
MESES_RECORRENTE = 3  # uma fonte que aparece em 3+ meses é recorrente
# Salário sem a palavra "salário": empresa que paga 1 vez por mês, em 2+ meses,
# sempre perto do mesmo dia e com valor estável
MESES_SALARIO = 2
VARIACAO_SALARIO = 0.10
VARIACAO_DIA_SALARIO = 3  # dias

CATEGORIAS_RENDA_EFETIVA = ["renda_fixa", "renda_variavel"]


def parece_empresa(contraparte):
    # "S.A." e "S/A" viram "SA"
    palavras = [palavra.replace(".", "").replace("/", "") for palavra in contraparte.split()]
    return len(palavras) > 3 or any(palavra in PALAVRAS_DE_EMPRESA for palavra in palavras)


def transferencias_por_par(tabela):
    """Ids de entradas e saídas que formam um par: mesmo usuário, mesmo dia, mesmo valor, contas diferentes.

    Pega transferências entre contas próprias mesmo quando a descrição não ajuda.
    Compras no cartão de crédito ficam de fora (cartão não é uma conta para onde se transfere).
    """
    colunas = ["id_transacao", "id_usuario", "data", "valor", "conta"]
    contas = tabela[tabela["conta"] != "cartao"]
    entradas = contas.loc[contas["valor"] > 0, colunas]
    saidas = contas.loc[contas["valor"] < 0, colunas].assign(valor=lambda t: -t["valor"])
    pares = entradas.merge(saidas, on=["id_usuario", "data", "valor"], suffixes=("_entrada", "_saida"))
    pares = pares[pares["conta_entrada"] != pares["conta_saida"]]
    # Cada transação só pode fazer parte de um par
    pares = pares.drop_duplicates("id_transacao_entrada").drop_duplicates("id_transacao_saida")
    return set(pares["id_transacao_entrada"]) | set(pares["id_transacao_saida"])


def _resumo_das_fontes(entradas):
    """Por usuário e contraparte: em quantos meses aparece, quantas vezes e quanto os valores variam."""
    return entradas.assign(dia=entradas["data"].dt.day).groupby(["id_usuario", "contraparte"]).agg(
        meses=("mes", "nunique"),
        vezes=("valor", "size"),
        variacao=("valor", lambda valores: valores.std() / valores.mean() if len(valores) > 1 else float("nan")),
        variacao_dia=("dia", "std"),
    )


def _parece_salario(contraparte, fonte):
    """Empresa que paga uma vez por mês, no mesmo período do mês e com valor estável."""
    return (
        parece_empresa(contraparte)
        and fonte["meses"] >= MESES_SALARIO
        and fonte["vezes"] == fonte["meses"]
        and fonte["variacao"] <= VARIACAO_SALARIO
        and fonte["variacao_dia"] <= VARIACAO_DIA_SALARIO
    )


def _decidir(linha, sobrenome_usuario, fonte, varias_fontes, eh_par):
    """Devolve (categoria, confiança, explicação) para uma entrada."""
    contraparte = linha["contraparte"]

    if linha["regra"] == "aplicacao_propria":
        return "guardar_investir", linha["confianca"], "Aplicação ou resgate de investimento seu: dinheiro guardado, não é renda."
    if linha["regra"] in REGRAS_INTERNAS:
        return "transferencia_interna", linha["confianca"], linha["explicacao"]
    if linha["regra"] == "rendimento":
        return "renda_eventual", 0.90, "Rendimento de aplicação: entra dinheiro, mas não é renda do trabalho."
    if linha["regra"] == "reembolso":
        return "renda_eventual", 0.85, "Reembolso ou estorno: devolve um gasto, não é renda do trabalho."
    if eh_par:
        return "transferencia_interna", 0.85, "Saiu o mesmo valor de outra conta sua no mesmo dia: transferência entre contas."
    if linha["regra"] == "salario":
        return "renda_fixa", 0.95, f"Crédito de salário ({contraparte})."
    if _parece_salario(contraparte, fonte):
        return "renda_fixa", 0.85, (
            f'"{contraparte}" paga uma vez por mês, perto do dia {linha["data"].day} e com valor estável: tratado como salário.'
        )
    if parece_empresa(contraparte):
        return "renda_variavel", 0.80, f'Pagamento de uma empresa ("{contraparte}") sem indicação de salário: renda de trabalho ou serviço.'
    if sobrenome_usuario and contraparte.split()[-1:] == [sobrenome_usuario]:
        return "renda_eventual", 0.60, f'"{contraparte}" tem o mesmo sobrenome que você: pode ser ajuda da família. Confirme.'

    recorrente_e_estavel = fonte["meses"] >= MESES_RECORRENTE and not fonte["variacao"] > VARIACAO_DE_CLIENTE
    if varias_fontes and not recorrente_e_estavel:
        return "renda_variavel", 0.60, f'Você recebe de várias fontes; "{contraparte}" pode ser um cliente. Confirme.'
    if fonte["meses"] >= MESES_RECORRENTE:
        explicacao = (
            f'Entradas de "{contraparte}" em {fonte["meses"]} meses, sem origem identificada. '
            "Se for pagamento por trabalho ou serviço, vale verificar suas obrigações fiscais."
        )
    else:
        explicacao = f'Entrada de "{contraparte}" sem origem conhecida: pode ser ajuda, reembolso ou outra coisa. Confirme.'
    return "renda_nao_identificada", 0.30, explicacao


def classificar_entradas(classificado, usuarios):
    """Classifica a origem de cada entrada de dinheiro. Recebe a saída de classificar_por_regras."""
    sobrenomes = usuarios.set_index("id_usuario")["nome"].map(lambda nome: normalizar_texto(nome).split()[-1])
    pares = transferencias_por_par(classificado)
    entradas = classificado[classificado["direcao"] == "entrada"].copy()

    internas = entradas["regra"].isin(REGRAS_INTERNAS) | entradas["id_transacao"].isin(pares)
    fontes = _resumo_das_fontes(entradas[~internas])
    # Quem tem salário (com ou sem a palavra) não é tratado como autônomo
    salario_sem_palavra = {
        usuario for (usuario, contraparte), fonte in fontes.iterrows() if _parece_salario(contraparte, fonte)
    }
    tem_salario = set(entradas.loc[entradas["regra"] == "salario", "id_usuario"]) | salario_sem_palavra
    quantidade_de_fontes = fontes.groupby("id_usuario").size()

    resultados = []
    for linha in entradas.to_dict("records"):
        usuario = linha["id_usuario"]
        chave = (usuario, linha["contraparte"])
        vazia = {"meses": 0, "vezes": 0, "variacao": float("nan"), "variacao_dia": float("nan")}
        fonte = fontes.loc[chave] if chave in fontes.index else vazia
        varias_fontes = usuario not in tem_salario and quantidade_de_fontes.get(usuario, 0) >= MINIMO_FONTES_AUTONOMO
        categoria, confianca, explicacao = _decidir(
            linha, sobrenomes.get(usuario, ""), fonte, varias_fontes, linha["id_transacao"] in pares
        )
        resultados.append({"categoria_renda": categoria, "confianca_renda": confianca, "explicacao_renda": explicacao})

    colunas = ["categoria_renda", "confianca_renda", "explicacao_renda"]
    entradas = pd.concat([entradas.reset_index(drop=True), pd.DataFrame(resultados, columns=colunas)], axis=1)
    entradas["perguntar_usuario"] = entradas["confianca_renda"] < CONFIANCA_MINIMA
    return entradas


def _tipo_de_renda(tem_salario, troca, fontes_efetivas, variacao):
    # Quem recebe salário nunca é classificado como autônomo, mesmo com meses sem salário
    if tem_salario:
        return "fixa" if variacao < LIMITE_RENDA_FIXA or troca else "variavel"
    if fontes_efetivas >= MINIMO_FONTES_AUTONOMO:
        return "autonoma"
    return "fixa" if variacao < LIMITE_RENDA_FIXA else "variavel"


def _troca_de_emprego(salarios, meses):
    """Detecta troca de emprego: salários de empresas diferentes, uma depois da outra.

    Devolve None ou um dicionário com os empregadores e os meses sem salário.
    """
    periodos = salarios.groupby("contraparte")["mes"].agg(["min", "max"]).sort_values("min")
    if len(periodos) < 2:
        return None
    anterior, atual = periodos.iloc[-2], periodos.iloc[-1]
    if anterior["max"] >= atual["min"]:
        return None  # salários ao mesmo tempo: dois empregos, não troca
    return {
        "empresa_anterior": periodos.index[-2],
        "empresa_atual": periodos.index[-1],
        "inicio_atual": atual["min"],
        "meses_sem_salario": [mes for mes in meses if anterior["max"] < mes < atual["min"]],
    }


def _explicar_perfil(perfil):
    if perfil["tipo_renda"] == "nao_informada":
        return (
            "Renda não informada: não há entradas de salário ou trabalho nestes dados (uma fatura de cartão só mostra gastos). "
            "Informe a renda mensal para ver a sobra e as porcentagens."
        )
    if perfil["troca_emprego"]:
        texto = (
            f"Renda fixa, com troca de emprego: o salário passou de {perfil['empresa_anterior']} "
            f"para {perfil['empresa_atual']} em {mes_por_extenso(perfil['inicio_atual'])}"
        )
        if perfil["meses_sem_salario"]:
            meses = ', '.join(mes_por_extenso(mes) for mes in perfil['meses_sem_salario'])
            texto += f", com {meses} sem salário (só outras entradas)"
        texto += f". Para planejar, o sistema usa o salário atual: cerca de {reais(perfil['renda_referencia'])}."
    elif perfil["tipo_renda"] == "fixa":
        texto = (
            f"Renda fixa: cerca de {reais(perfil['media'])} por mês, com variação de {perfil['variacao']:.0%} entre os meses. "
            "Para planejar, o sistema usa a média."
        )
    else:
        nome = "autônoma" if perfil["tipo_renda"] == "autonoma" else "variável"
        texto = (
            f"Renda {nome}: {perfil['fontes']} fontes, média de {reais(perfil['media'])}, "
            f"menor mês {reais(perfil['minima'])} e maior mês {reais(perfil['maxima'])} "
            f"(variação de {perfil['variacao']:.0%}). Para planejar, o sistema usa o menor mês, por segurança."
        )
    if perfil["eventual_total"] > 0:
        texto += f" Entradas eventuais (ex.: ajuda) somam {reais(perfil['eventual_total'])} e não contam como renda."
    if perfil["nao_identificada_total"] > 0:
        texto += f" Há {reais(perfil['nao_identificada_total'])} de origem não identificada, fora da conta da renda."
    return texto


def perfil_de_renda(entradas, meses, usuarios=None):
    """Uma linha por usuário com o perfil da renda efetiva (fixa + variável).

    usuarios: lista de todos os usuários. Quem não tem nenhuma entrada (ex.: só uma fatura de cartão,
    sem renda informada) aparece com renda "não informada".
    """
    usuarios = list(usuarios) if usuarios is not None else list(entradas["id_usuario"].unique())
    efetiva = entradas[entradas["categoria_renda"].isin(CATEGORIAS_RENDA_EFETIVA)]
    por_mes = efetiva.pivot_table(index="id_usuario", columns="mes", values="valor", aggfunc="sum", fill_value=0)
    por_mes = por_mes.reindex(columns=meses, fill_value=0).reindex(usuarios, fill_value=0)

    linhas = []
    for usuario, valores in por_mes.iterrows():
        do_usuario = entradas[entradas["id_usuario"] == usuario]
        salarios = do_usuario[do_usuario["categoria_renda"] == "renda_fixa"]
        tem_salario = len(salarios) > 0
        troca = _troca_de_emprego(salarios, meses) if tem_salario else None
        fontes = do_usuario.loc[do_usuario["categoria_renda"].isin(CATEGORIAS_RENDA_EFETIVA), "contraparte"].nunique()
        media = valores.mean()
        variacao = valores.std() / media if media > 0 else 0.0
        tipo = _tipo_de_renda(tem_salario, troca is not None, fontes, variacao) if media > 0 else "nao_informada"
        if troca:
            referencia = salarios.loc[salarios["contraparte"] == troca["empresa_atual"], "valor"].mean()
        else:
            referencia = media if tipo == "fixa" else valores.min()
        perfil = {
            "id_usuario": usuario,
            "tipo_renda": tipo,
            "media": round(media, 2),
            "minima": round(valores.min(), 2),
            "maxima": round(valores.max(), 2),
            "variacao": round(variacao, 3),
            "fontes": fontes,
            "renda_referencia": round(referencia, 2),
            "troca_emprego": troca is not None,
            "empresa_anterior": troca["empresa_anterior"] if troca else "",
            "empresa_atual": troca["empresa_atual"] if troca else "",
            "inicio_atual": troca["inicio_atual"] if troca else "",
            "meses_sem_salario": troca["meses_sem_salario"] if troca else [],
            "eventual_total": round(do_usuario.loc[do_usuario["categoria_renda"] == "renda_eventual", "valor"].sum(), 2),
            "nao_identificada_total": round(
                do_usuario.loc[do_usuario["categoria_renda"] == "renda_nao_identificada", "valor"].sum(), 2
            ),
        }
        perfil["explicacao"] = _explicar_perfil(perfil)
        linhas.append(perfil)
    return pd.DataFrame(linhas)
