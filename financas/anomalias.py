"""Detecção de anomalias (Fase 8).

Dois métodos, ambos NÃO supervisionados (nenhum deles vê os rótulos das anomalias plantadas):

1. Estatístico: quatro verificações simples, cada uma comparando o usuário com o próprio
   histórico (só meses anteriores). Fáceis de explicar em uma frase.
2. IsolationForest (scikit-learn): olha várias características ao mesmo tempo e separa as
   transações "fáceis de isolar". A explicação vem da característica mais fora do normal.

Cada alerta tem: usuário, detector, as transações envolvidas e uma explicação curta.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from financas import SEMENTE
from financas.formatacao import mes_por_extenso, reais
from financas.regras import parece_pessoa

# Transações que não entram na detecção: movimentam dinheiro entre contas ou são parcelas esperadas
FORA_DA_DETECCAO = ("transferencia_interna", "pagamento_fatura")

# Limites (escolhas de projeto, decididas antes de olhar os resultados)
# Pico: 3 desvios e 3 meses de histórico, decididos por princípio (docs/03_decisoes_anomalias.md):
# com ~600 verificações, 2 desvios dariam ~30 alarmes falsos esperados; 3 desvios, ~2
DESVIOS_PICO = 3.0  # pico: acima de média + 3 desvios padrão dos meses anteriores
AUMENTO_MINIMO_PICO = 1.5  # ...e pelo menos 50% acima da média
DIFERENCA_MINIMA_PICO = 50.0  # ...e pelo menos R$ 50 acima da média
MESES_MINIMOS_HISTORICO = 3
SIMILARIDADE_LOJA_CONHECIDA = 0.5  # abaixo disso, a descrição não parece nenhuma já vista
VEZES_A_MEDIANA = 3.0  # valor alto: mais de 3x a mediana das compras do usuário
MINIMO_COMPRAS_FREQUENCIA = 5  # frequência incomum: 5+ compras da mesma categoria em 2 dias
DESVIOS_FREQUENCIA = 3.0
DIAS_DUPLICADA = 1  # cobrança igual no mesmo dia ou no dia seguinte
CONTAMINACAO_ISOLATION_FOREST = 0.05  # fração esperada de transações estranhas (fixada a priori)


def preparar(saidas):
    """Só as saídas que fazem sentido analisar, com colunas auxiliares."""
    tabela = saidas[~saidas["categoria_final"].isin(FORA_DA_DETECCAO) & (saidas["parcela"].fillna("") == "")].copy()
    tabela["data"] = pd.to_datetime(tabela["data"])
    tabela["gasto"] = -tabela["valor"]
    return tabela.sort_values(["id_usuario", "data", "id_transacao"]).reset_index(drop=True)


def _nome(categoria):
    return categoria.replace("_", " ")


def _alerta(usuario, detector, ids, explicacao):
    return {"id_usuario": usuario, "detector": detector, "ids": list(ids), "explicacao": explicacao}


# ---------- Método estatístico ----------

def detectar_picos(tabela):
    """Mês em que o gasto de uma categoria ficou bem acima da média dos meses anteriores."""
    meses = sorted(tabela["mes"].unique())
    alertas = []
    # Sem categoria ainda ("a confirmar") não dá para dizer que um tipo de gasto aumentou
    com_categoria = tabela[tabela["categoria_final"] != "nao_identificado"]
    por_mes = com_categoria.groupby(["id_usuario", "categoria_final", "mes"])["gasto"].sum()
    for (usuario, categoria), serie in por_mes.groupby(level=[0, 1]):
        totais = serie.droplevel([0, 1]).reindex(meses, fill_value=0)
        for posicao in range(MESES_MINIMOS_HISTORICO, len(meses)):
            anteriores, atual = totais.iloc[:posicao], totais.iloc[posicao]
            media, desvio = anteriores.mean(), anteriores.std()
            if (
                media > 0
                and atual > media + DESVIOS_PICO * desvio
                and atual >= AUMENTO_MINIMO_PICO * media
                and atual - media >= DIFERENCA_MINIMA_PICO
            ):
                mes = meses[posicao]
                ids = tabela.loc[
                    (tabela["id_usuario"] == usuario) & (tabela["categoria_final"] == categoria) & (tabela["mes"] == mes),
                    "id_transacao",
                ]
                alertas.append(_alerta(usuario, "pico_categoria", ids, (
                    f"Seu gasto com {_nome(categoria)} em {mes_por_extenso(mes)} foi {reais(atual)}, "
                    f"bem acima da sua média dos meses anteriores ({reais(media)})."
                )))
    return alertas


def detectar_duplicadas(tabela):
    """Mesma descrição e mesmo valor no mesmo dia ou no dia seguinte."""
    alertas = []
    for (usuario, descricao, valor), grupo in tabela.groupby(["id_usuario", "descricao", "valor"]):
        if len(grupo) < 2:
            continue
        datas = grupo["data"].tolist()
        ids = grupo["id_transacao"].tolist()
        for anterior in range(len(grupo) - 1):
            if (datas[anterior + 1] - datas[anterior]).days <= DIAS_DUPLICADA:
                alertas.append(_alerta(usuario, "cobranca_duplicada", [ids[anterior + 1]], (
                    f'Cobrança igual a outra de {datas[anterior]:%d/%m} ("{descricao}", {reais(-valor)}): '
                    "pode ter sido cobrada duas vezes."
                )))
    return alertas


def novidade(tabela):
    """Para cada transação, 1 - maior semelhança com descrições ANTERIORES do mesmo usuário.

    1 = nada parecido no histórico; 0 = descrição já vista. A semelhança usa pedaços de
    letras, então "LV*SUPERMERCADOBOMPRECO" ainda parece "SUPERMERCADO BOM PRECO".
    """
    resultado = pd.Series(1.0, index=tabela.index)
    for _, grupo in tabela.groupby("id_usuario"):
        vetores = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4)).fit_transform(grupo["contraparte"])
        semelhanca = cosine_similarity(vetores)
        datas = grupo["data"].to_numpy()
        for posicao, indice in enumerate(grupo.index):
            anteriores = datas < datas[posicao]
            if anteriores.any():
                resultado[indice] = 1 - semelhanca[posicao, anteriores].max()
    return resultado


def detectar_lojas_novas_caras(tabela, novidades):
    """Descrição que não parece nenhuma já vista e valor muito acima do habitual."""
    alertas = []
    primeiro_mes = tabela["mes"].min()
    for usuario, grupo in tabela.groupby("id_usuario"):
        for indice, linha in grupo[grupo["mes"] > primeiro_mes].iterrows():
            historico = grupo.loc[grupo["data"] < linha["data"], "gasto"]
            if historico.empty or novidades[indice] < 1 - SIMILARIDADE_LOJA_CONHECIDA:
                continue
            limite = max(VEZES_A_MEDIANA * historico.median(), historico.quantile(0.95))
            if linha["gasto"] > limite:
                eh_pix_para_pessoa = linha["descricao"].startswith("PIX ENVIADO") and parece_pessoa(linha["contraparte"])
                inicio = "Primeiro PIX para" if eh_pix_para_pessoa else "Primeira compra em"
                alertas.append(_alerta(usuario, "estabelecimento_novo_alto", [linha["id_transacao"]], (
                    f'{inicio} "{linha["contraparte"]}" e no valor de {reais(linha["gasto"])}, '
                    f"acima do seu habitual (até {reais(limite)})."
                )))
    return alertas


def detectar_frequencia(tabela):
    """Muitas compras da mesma categoria em 2 dias, bem mais que o normal do usuário."""
    alertas = []
    meses = sorted(tabela["mes"].unique())
    dias = pd.date_range(tabela["data"].min(), tabela["data"].max(), freq="D")
    for (usuario, categoria), grupo in tabela.groupby(["id_usuario", "categoria_final"]):
        contagem = grupo.groupby("data").size().reindex(dias, fill_value=0)
        dois_dias = contagem.rolling(2, min_periods=1).sum()
        dia_alerta = None
        for dia, quantidade in dois_dias.items():
            mes = dia.strftime("%Y-%m")
            if mes == meses[0]:
                continue
            historico = dois_dias[dois_dias.index < pd.Timestamp(mes + "-01")]
            limite = max(MINIMO_COMPRAS_FREQUENCIA, historico.mean() + DESVIOS_FREQUENCIA * historico.std())
            if quantidade >= limite and (dia_alerta is None or (dia - dia_alerta).days > 2):
                dia_alerta = dia
                janela = grupo[(grupo["data"] >= dia - pd.Timedelta(days=1)) & (grupo["data"] <= dia + pd.Timedelta(days=1))]
                alertas.append(_alerta(usuario, "frequencia_incomum", janela["id_transacao"], (
                    f"{len(janela)} compras de {_nome(categoria)} entre {janela['data'].min():%d/%m} e "
                    f"{janela['data'].max():%d/%m}; o normal para você é até {int(limite) - 1} em 2 dias."
                )))
    return alertas


def detectar_estatistico(saidas):
    """Roda as quatro verificações e devolve a tabela de alertas.

    O pico por categoria é calculado por último, sem as transações já explicadas pelos
    outros detectores: uma compra cara numa loja nova não deve gerar também um alerta
    de "mês acima da média" pelo mesmo motivo.
    """
    tabela = preparar(saidas)
    alertas = detectar_duplicadas(tabela) + detectar_lojas_novas_caras(tabela, novidade(tabela)) + detectar_frequencia(tabela)
    ja_explicadas = {id_ for alerta in alertas for id_ in alerta["ids"]}
    alertas += detectar_picos(tabela[~tabela["id_transacao"].isin(ja_explicadas)])
    return pd.DataFrame(alertas, columns=["id_usuario", "detector", "ids", "explicacao"])


# ---------- IsolationForest ----------

EXPLICACOES_IF = {
    "valor_vs_categoria": "valor muito diferente do que você costuma gastar nessa categoria",
    "valor_vs_usuario": "valor alto comparado às suas compras em geral",
    "repeticoes": "cobrança repetida com mesmo valor em poucos dias",
    "compras_em_2_dias": "muitas compras da mesma categoria em poucos dias",
    "novidade": "estabelecimento diferente de todos do seu histórico",
    "mes_da_categoria": "mês com gasto acima do normal nessa categoria",
}


def caracteristicas(tabela, novidades):
    """Características de cada transação, sempre relativas ao próprio usuário."""
    grupo_categoria = tabela.groupby(["id_usuario", "categoria_final"])["gasto"]
    media_cat, desvio_cat = grupo_categoria.transform("mean"), grupo_categoria.transform("std").fillna(0)
    mediana_usuario = tabela.groupby("id_usuario")["gasto"].transform("median")
    total_mes = tabela.groupby(["id_usuario", "categoria_final", "mes"])["gasto"].transform("sum")
    meses_por_usuario = tabela.groupby("id_usuario")["mes"].transform("nunique")
    media_mes = tabela.groupby(["id_usuario", "categoria_final"])["gasto"].transform("sum") / meses_por_usuario

    repeticoes, vizinhas = [], []
    for linha in tabela.itertuples():
        mesmo_usuario = tabela[tabela["id_usuario"] == linha.id_usuario]
        perto = (mesmo_usuario["data"] - linha.data).abs() <= pd.Timedelta(days=1)
        repeticoes.append(int((perto & (mesmo_usuario["descricao"] == linha.descricao) & (mesmo_usuario["valor"] == linha.valor)).sum()) - 1)
        vizinhas.append(int((perto & (mesmo_usuario["categoria_final"] == linha.categoria_final)).sum()) - 1)

    return pd.DataFrame({
        "valor_vs_categoria": (tabela["gasto"] - media_cat) / desvio_cat.replace(0, np.nan),
        "valor_vs_usuario": np.log(tabela["gasto"] / mediana_usuario),
        "repeticoes": repeticoes,
        "compras_em_2_dias": vizinhas,
        "novidade": novidades,
        "mes_da_categoria": total_mes / media_mes,
    }, index=tabela.index).fillna(0)


def detectar_isolation_forest(saidas):
    """Marca as transações mais "isoláveis" e explica pela característica mais fora do normal."""
    tabela = preparar(saidas)
    dados = caracteristicas(tabela, novidade(tabela))
    padronizado = (dados - dados.mean()) / dados.std().replace(0, 1)
    modelo = IsolationForest(n_estimators=200, contamination=CONTAMINACAO_ISOLATION_FOREST, random_state=SEMENTE)
    marcadas = modelo.fit_predict(padronizado) == -1
    alertas = []
    for indice in tabela.index[marcadas]:
        linha = tabela.loc[indice]
        principal = padronizado.loc[indice].idxmax()
        alertas.append(_alerta(linha["id_usuario"], "isolation_forest", [linha["id_transacao"]], (
            f'"{linha["descricao"]}" ({reais(linha["gasto"])}, {linha["data"]:%d/%m}) foge do seu padrão: '
            f"{EXPLICACOES_IF[principal]}."
        )))
    return pd.DataFrame(alertas, columns=["id_usuario", "detector", "ids", "explicacao"])
