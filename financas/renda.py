"""Renda e transferências internas (Fase 4).

O SIDOF orienta sobre os gastos; dos ganhos ele só precisa saber se a renda é fixa ou variável.
Por isso nunca pergunta sobre entradas (decisão do maestro, 25/11/2026). Todo dinheiro que entra conta
como renda, menos as exceções que o sistema reconhece sozinho:
- transferencia_interna: dinheiro do próprio usuário mudando de conta
- guardar_investir: aplicação ou resgate de investimento
- renda_eventual: rendimento, reembolso/estorno, empréstimo recebido e ajuda da família
  (mesmo sobrenome ou palavras como "familiar"): entram, mas não são renda do trabalho
- renda_fixa: salário (com ou sem a palavra "salário")
- renda_variavel: todo o resto (clientes, PIX de várias pessoas, maquininha, bicos)

Depois calcula o perfil de renda: fixa ou variável, média, menor mês, e mudanças no salário
(troca de emprego, salário que começou ou que parou, meses sem salário).
"""

import pandas as pd

from financas.formatacao import mes_por_extenso, reais
from financas.normalizacao import normalizar_texto
from financas.regras import CONFIANCA_MINIMA, MARCAS_DE_EMPRESA, REGRAS_INTERNAS, parece_pessoa, sem_detalhes

# Palavras comuns em nomes de empresas (além de LTDA, ME, SA...)
PALAVRAS_DE_EMPRESA = set(MARCAS_DE_EMPRESA) | {
    "COMERCIO", "CONSTRUTORA", "ESCRITORIO", "AGENCIA", "STUDIO", "EVENTOS",
    "CONSULTORIA", "INDUSTRIA", "DISTRIBUIDORA", "ASSOCIACAO", "INSTITUTO",
}
LIMITE_RENDA_FIXA = 0.10  # variação mensal até 10% = renda fixa
MINIMO_FONTES_AUTONOMO = 3  # sem salário e com 3+ fontes pagadoras = perfil de autônomo
# Salário sem a palavra "salário": empresa que paga 1 vez por mês, em 2+ meses,
# sempre perto do mesmo dia e com valor estável
MESES_SALARIO = 2
VARIACAO_SALARIO = 0.10
VARIACAO_DIA_SALARIO = 3  # dias

CATEGORIAS_RENDA_EFETIVA = ["renda_fixa", "renda_variavel"]
# Entradas que não são renda do trabalho, reconhecidas pelo texto (sem perguntar)
PALAVRAS_DE_EMPRESTIMO = ("EMPRESTIMO", "FINANCIAMENTO", "CREDITO PESSOAL", "CONSIGNADO")
PALAVRAS_DE_FAMILIA = ("FAMILIAR", "FAMILIA", "MESADA", "AJUDA")
# Nenhuma entrada vira pergunta: a confiança das decisões sobre renda fica sempre acima do limite
CONFIANCA_RENDA_SEM_PERGUNTA = 0.80


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


def _tem_palavra(texto, palavras):
    return any(palavra in texto.split() or f" {palavra} " in f" {texto} " for palavra in palavras)


def _decidir(linha, sobrenome_usuario, fonte, eh_par):
    """Devolve (categoria, confiança, explicação) para uma entrada. Nunca pergunta."""
    contraparte = linha["contraparte"]
    descricao = linha["descricao"]

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
    if _tem_palavra(descricao, PALAVRAS_DE_EMPRESTIMO):
        return "renda_eventual", 0.90, "Empréstimo recebido: o dinheiro entra, mas é dívida, não renda."
    if linha["regra"] == "salario":
        return "renda_fixa", 0.95, f"Crédito de salário ({contraparte})."
    if _parece_salario(contraparte, fonte):
        return "renda_fixa", 0.85, (
            f'"{contraparte}" paga uma vez por mês, perto do dia {linha["data"].day} e com valor estável: tratado como salário.'
        )
    pessoa = linha.get("eh_pessoa", parece_pessoa(contraparte))
    mesmo_sobrenome = sobrenome_usuario and pessoa and sem_detalhes(contraparte).split()[-1:] == [sobrenome_usuario]
    if _tem_palavra(descricao, PALAVRAS_DE_FAMILIA) or mesmo_sobrenome:
        return "renda_eventual", CONFIANCA_RENDA_SEM_PERGUNTA, (
            f'"{contraparte}" parece ajuda da família: entra, mas não conta como renda do trabalho.'
        )
    if parece_empresa(contraparte):
        return "renda_variavel", 0.85, f'Pagamento de uma empresa ("{contraparte}") sem indicação de salário: renda de trabalho ou serviço.'
    return "renda_variavel", CONFIANCA_RENDA_SEM_PERGUNTA, (
        f'Entrada de "{contraparte}": conta como renda do trabalho (clientes, vendas, bicos). '
        "O sistema não pergunta sobre ganhos; ele só observa se a renda é fixa ou variável."
    )


def classificar_entradas(classificado, usuarios):
    """Classifica a origem de cada entrada de dinheiro. Recebe a saída de classificar_por_regras."""
    sobrenomes = usuarios.set_index("id_usuario")["nome"].map(lambda nome: normalizar_texto(nome).split()[-1])
    pares = transferencias_por_par(classificado)
    entradas = classificado[classificado["direcao"] == "entrada"].copy()

    internas = entradas["regra"].isin(REGRAS_INTERNAS) | entradas["id_transacao"].isin(pares)
    fontes = _resumo_das_fontes(entradas[~internas])
    # Quem tem salário (com ou sem a palavra) não é tratado como autônomo

    resultados = []
    for linha in entradas.to_dict("records"):
        usuario = linha["id_usuario"]
        chave = (usuario, linha["contraparte"])
        vazia = {"meses": 0, "vezes": 0, "variacao": float("nan"), "variacao_dia": float("nan")}
        fonte = fontes.loc[chave] if chave in fontes.index else vazia
        categoria, confianca, explicacao = _decidir(linha, sobrenomes.get(usuario, ""), fonte, linha["id_transacao"] in pares)
        resultados.append({"categoria_renda": categoria, "confianca_renda": confianca, "explicacao_renda": explicacao})

    colunas = ["categoria_renda", "confianca_renda", "explicacao_renda"]
    entradas = pd.concat([entradas.reset_index(drop=True), pd.DataFrame(resultados, columns=colunas)], axis=1)
    entradas["perguntar_usuario"] = entradas["confianca_renda"] < CONFIANCA_MINIMA
    return entradas


def _tipo_sem_salario(fontes_efetivas, variacao):
    if fontes_efetivas >= MINIMO_FONTES_AUTONOMO:
        return "autonoma"
    return "fixa" if variacao < LIMITE_RENDA_FIXA else "variavel"


def _mudancas_no_salario(salarios, meses):
    """O que aconteceu com o salário no período. Devolve None se ele veio todos os meses.

    situacao: "troca" (trocou de empresa), "comecou" (não havia salário no início), "parou" (o salário
    sumiu antes do fim: parece um período sem emprego fixo) ou "intervalo" (meses sem salário no meio).
    """
    meses_com_salario = sorted(salarios["mes"].unique())
    sem_salario = [mes for mes in meses if mes not in meses_com_salario]
    if not sem_salario:
        return None
    troca = _troca_de_emprego(salarios, meses)
    ultimo = meses_com_salario[-1]
    if ultimo < meses[-1]:
        situacao = "parou"
    elif troca:
        situacao = "troca"
    elif meses_com_salario[0] > meses[0] and all(mes < meses_com_salario[0] for mes in sem_salario):
        situacao = "comecou"
    else:
        situacao = "intervalo"
    empresa_atual = salarios.loc[salarios["mes"] == ultimo, "contraparte"].iloc[0]
    inicio_atual = salarios.loc[salarios["contraparte"] == empresa_atual, "mes"].min()
    return {
        "situacao": situacao,
        "meses_sem_salario": sem_salario,
        "empresa_anterior": troca["empresa_anterior"] if troca else "",
        "empresa_atual": empresa_atual,
        "inicio_atual": inicio_atual,
        "ultimo_salario": ultimo,
    }


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


def _lista_de_meses(meses):
    return ", ".join(mes_por_extenso(mes) for mes in meses)


def _explicar_salario(perfil):
    situacao, sem_salario = perfil["situacao_salario"], perfil["meses_sem_salario"]
    if situacao == "parou":
        depois = [mes for mes in sem_salario if mes > perfil["ultimo_salario"]]
        return (
            f"O último salário de {perfil['empresa_atual']} foi em {mes_por_extenso(perfil['ultimo_salario'])}. "
            f"Desde então ({_lista_de_meses(depois)}) a renda veio de outras entradas, o que parece um período sem emprego "
            f"fixo. Para planejar, o sistema usa o menor desses meses, por segurança: cerca de {reais(perfil['renda_referencia'])}."
        )
    if situacao == "troca":
        texto = (
            f"Renda fixa, com troca de emprego: o salário passou de {perfil['empresa_anterior']} "
            f"para {perfil['empresa_atual']} em {mes_por_extenso(perfil['inicio_atual'])}"
        )
    elif situacao == "comecou":
        texto = (
            f"Renda fixa desde {mes_por_extenso(perfil['inicio_atual'])}, com salário de {perfil['empresa_atual']}. "
            "Antes disso não havia salário (parece um período sem emprego fixo)"
        )
    else:
        texto = f"Renda fixa de {perfil['empresa_atual']}"
    texto += f", com {_lista_de_meses(sem_salario)} sem salário (só outras entradas)"
    return texto + f". Para planejar, o sistema usa o salário atual: cerca de {reais(perfil['renda_referencia'])}."


def _explicar_perfil(perfil):
    if perfil["tipo_renda"] == "nao_informada":
        return (
            "Renda não informada: não há entradas de salário ou trabalho nestes dados (uma fatura de cartão só mostra gastos). "
            "Informe a renda mensal para ver a sobra e as porcentagens."
        )
    if perfil["situacao_salario"]:
        texto = _explicar_salario(perfil)
    elif perfil["tipo_renda"] == "fixa":
        texto = (
            f"Renda fixa: cerca de {reais(perfil['renda_referencia'])} por mês de salário, com variação de "
            f"{perfil['variacao']:.0%} entre os meses. Para planejar, o sistema usa o salário."
        )
        if perfil["extra_por_mes"] > 0:
            texto += (
                f" Além dele, entram em média {reais(perfil['extra_por_mes'])} por mês de outras fontes; como variam, "
                "ficam fora do planejamento."
            )
    else:
        texto = (
            f"Renda variável: {perfil['fontes']} fontes, média de {reais(perfil['media'])}, "
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
        fontes = do_usuario.loc[do_usuario["categoria_renda"].isin(CATEGORIAS_RENDA_EFETIVA), "contraparte"].nunique()
        media = valores.mean()
        # Com um mês só não há variação para medir (o desvio padrão de um único valor não existe)
        variacao = valores.std() / media if media > 0 and len(valores) > 1 else 0.0
        mudanca = _mudancas_no_salario(salarios, meses) if len(salarios) else None
        extra_por_mes = 0.0
        if media <= 0:
            tipo, referencia = "nao_informada", 0.0
        elif not len(salarios):
            tipo = _tipo_sem_salario(fontes, variacao)
            referencia = media if tipo == "fixa" else valores.min()
        elif mudanca and mudanca["situacao"] == "parou":
            # Sem salário no fim do período: a renda de agora é variável
            depois = valores[[mes for mes in meses if mes > mudanca["ultimo_salario"]]]
            tipo, referencia = "variavel", depois.min()
        elif mudanca:
            tipo = "fixa"
            referencia = salarios.loc[salarios["contraparte"] == mudanca["empresa_atual"]].groupby("mes")["valor"].sum().mean()
        else:
            # Salário todo mês: a variação é a do salário; outras entradas são extras fora do planejamento
            salario_por_mes = salarios.groupby("mes")["valor"].sum().reindex(meses, fill_value=0)
            referencia = salario_por_mes.mean()
            variacao = salario_por_mes.std() / referencia if referencia > 0 and len(salario_por_mes) > 1 else 0.0
            tipo = "fixa" if variacao < LIMITE_RENDA_FIXA else "variavel"
            extra_por_mes = max(media - referencia, 0.0)
        troca = mudanca if mudanca and mudanca["situacao"] == "troca" else None
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
            "situacao_salario": mudanca["situacao"] if mudanca else "",
            "empresa_anterior": mudanca["empresa_anterior"] if mudanca else "",
            "empresa_atual": mudanca["empresa_atual"] if mudanca else "",
            "inicio_atual": mudanca["inicio_atual"] if mudanca else "",
            "ultimo_salario": mudanca["ultimo_salario"] if mudanca else "",
            "meses_sem_salario": mudanca["meses_sem_salario"] if mudanca else [],
            "extra_por_mes": round(extra_por_mes, 2),
            "eventual_total": round(do_usuario.loc[do_usuario["categoria_renda"] == "renda_eventual", "valor"].sum(), 2),
            "nao_identificada_total": round(
                do_usuario.loc[do_usuario["categoria_renda"] == "renda_nao_identificada", "valor"].sum(), 2
            ),
        }
        perfil["explicacao"] = _explicar_perfil(perfil)
        linhas.append(perfil)
    return pd.DataFrame(linhas)
