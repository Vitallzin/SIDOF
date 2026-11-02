"""Experimento da Fase 3: o modelo melhora em relação às regras?

Como o teste é feito (avaliação honesta):
- Divisão por USUÁRIO: em cada rodada, 1 usuário de cada perfil fica de fora do treino
  e só é usado para teste. São 3 rodadas, então cada usuário é testado uma vez
  por um modelo que nunca viu as transações dele.
- Treino: transações dos outros usuários com a categoria verdadeira, simulando
  pessoas que já confirmaram suas classificações no passado.
- O parâmetro C do modelo é escolhido só com os usuários de treino.
- Baseline (comparação simples): só as regras da Fase 2. Também mostramos a
  "categoria mais comum" para ter uma referência ingênua.
- Ciclo de correção: mês a mês, o usuário de teste responde as perguntas (a resposta
  vem da verdade, simulando o usuário) e o sistema aprende com elas.
"""

import pandas as pd
from sklearn.model_selection import GridSearchCV, GroupKFold

from financas.modelo import classificar_hibrido, criar_modelo, treinar
from financas.regras import CONFIANCA_MINIMA

VALORES_DE_C = [0.3, 1, 3, 10, 30]
RODADAS = 3
# No teste duro, só categorias com pelo menos este número de lojas têm lojas separadas
# (separar a única empresa de energia deixaria a categoria sem nenhum exemplo de treino)
MINIMO_DE_LOJAS = 3
COLUNAS_VERDADE = ["id_transacao", "categoria", "ambigua", "loja"]


def dividir_por_usuario(usuarios_verdade):
    """Lista de conjuntos de usuários de teste: em cada rodada, 1 usuário de cada perfil."""
    rodadas = []
    for indice in range(RODADAS):
        teste = usuarios_verdade.groupby("perfil")["id_usuario"].nth(indice)
        rodadas.append(set(teste))
    return rodadas


def lojas_de_teste(verdade, rodada):
    """Teste duro: em cada rodada, 1/3 das lojas de cada categoria fica fora do treino.

    Em 3 rodadas, cada loja é "nova" para o modelo exatamente uma vez.
    """
    lojas = verdade.loc[verdade["loja"] != "", ["loja", "categoria"]].drop_duplicates()
    fora = set()
    for _, grupo in lojas.groupby("categoria"):
        nomes = sorted(grupo["loja"])
        if len(nomes) >= MINIMO_DE_LOJAS:
            fora.update(nomes[rodada::RODADAS])
    return fora


def escolher_c(treino):
    """Escolhe C por validação cruzada, separando também os usuários de treino entre si."""
    busca = GridSearchCV(
        criar_modelo(),
        {"logisticregression__C": VALORES_DE_C},
        cv=GroupKFold(n_splits=4),
        scoring="accuracy",
    )
    busca.fit(list(treino["descricao"]), list(treino["categoria"]), groups=list(treino["id_usuario"]))
    return busca.best_params_["logisticregression__C"]


def metricas(tabela, coluna_categoria="categoria_final", coluna_pergunta="perguntar_usuario"):
    """Resultado do ponto de vista do usuário.

    automaticas: o sistema decidiu sozinho
    precisao: acertos entre as decididas sozinho
    erros_silenciosos: % do total decidido sozinho e errado (o pior caso: ninguém confere)
    perguntas: % do total que virou pergunta
    """
    automatica = ~tabela[coluna_pergunta]
    acerto = automatica & (tabela[coluna_categoria] == tabela["categoria"])
    return {
        "automaticas": automatica.mean(),
        "precisao": acerto.sum() / max(automatica.sum(), 1),
        "erros_silenciosos": (automatica & ~acerto).mean(),
        "perguntas": 1 - automatica.mean(),
    }


def simular_correcoes(treino, teste, colunas_sistema, c):
    """Mês a mês: classifica, o usuário responde as perguntas e o sistema aprende."""
    memoria, textos_extra, categorias_extra, meses = {}, [], [], []
    for mes in sorted(teste["mes"].unique()):
        modelo = treinar(
            list(treino["descricao"]) + textos_extra,
            list(treino["categoria"]) + categorias_extra,
            c,
        )
        lote = teste[teste["mes"] == mes]
        resultado = classificar_hibrido(lote[colunas_sistema], modelo, memoria)
        resultado = resultado.merge(lote[COLUNAS_VERDADE], on="id_transacao")
        meses.append(resultado)

        # O usuário responde cada pergunta; a resposta vira memória e exemplo de treino
        perguntas = resultado[resultado["perguntar_usuario"]]
        for linha in perguntas.itertuples():
            memoria[(linha.id_usuario, linha.contraparte)] = linha.categoria
            textos_extra.append(linha.descricao)
            categorias_extra.append(linha.categoria)
    return pd.concat(meses, ignore_index=True)


def executar_experimento(classificado, verdade, usuarios_verdade, separar_lojas=False):
    """Roda as 3 rodadas e devolve as tabelas de resultado (todas só com usuários de teste).

    separar_lojas=True faz o teste duro: além dos usuários, 1/3 das lojas também fica
    fora do treino, e a coluna loja_nova marca as transações dessas lojas.
    """
    colunas_sistema = list(classificado.columns)
    saidas = classificado[classificado["direcao"] == "saida"].merge(
        verdade[COLUNAS_VERDADE], on="id_transacao"
    )
    estaticos, simulados, valores_c = [], [], []
    for rodada, usuarios_teste in enumerate(dividir_por_usuario(usuarios_verdade)):
        fora = lojas_de_teste(verdade, rodada) if separar_lojas else set()
        treino = saidas[~saidas["id_usuario"].isin(usuarios_teste) & ~saidas["loja"].isin(fora)]
        teste = saidas[saidas["id_usuario"].isin(usuarios_teste)].assign(loja_nova=lambda t: t["loja"].isin(fora))
        c = escolher_c(treino)
        valores_c.append(c)

        modelo = treinar(treino["descricao"], treino["categoria"], c)
        resultado = classificar_hibrido(teste[colunas_sistema], modelo)
        resultado = resultado.merge(teste[COLUNAS_VERDADE + ["loja_nova"]], on="id_transacao")
        resultado["mais_comum"] = treino["categoria"].mode()[0]
        estaticos.append(resultado)
        simulado = simular_correcoes(treino, teste, colunas_sistema, c)
        simulados.append(simulado.merge(teste[["id_transacao", "loja_nova"]], on="id_transacao"))

    return {
        "hibrido": pd.concat(estaticos, ignore_index=True),
        "simulacao": pd.concat(simulados, ignore_index=True),
        "valores_c": valores_c,
    }


def comparar_estrategias(resultado):
    """Tabela com regras sozinhas x regras + modelo x regras + modelo + correções."""
    hibrido = resultado["hibrido"]
    linhas = {
        "Só regras (baseline)": metricas(hibrido, "categoria_regra", "perguntar_regra"),
        "Regras + modelo": metricas(hibrido),
        "Regras + modelo + correções (6 meses)": metricas(resultado["simulacao"]),
    }
    return pd.DataFrame(linhas).T


def por_categoria(hibrido):
    """Para cada categoria real: quantas, quantas o sistema acertou sozinho, errou ou perguntou."""
    tabela = hibrido.assign(
        acerto=~hibrido["perguntar_usuario"] & (hibrido["categoria_final"] == hibrido["categoria"]),
        erro=~hibrido["perguntar_usuario"] & (hibrido["categoria_final"] != hibrido["categoria"]),
    )
    resumo = tabela.groupby("categoria").agg(
        quantidade=("acerto", "size"),
        acertou_sozinho=("acerto", "mean"),
        errou_sozinho=("erro", "mean"),
        perguntou=("perguntar_usuario", "mean"),
    )
    return resumo.sort_values("quantidade", ascending=False)


def por_mes(simulacao):
    """Evolução do ciclo de correção: perguntas e erros caem conforme o usuário responde?"""
    return pd.DataFrame({mes: metricas(grupo) for mes, grupo in simulacao.groupby("mes")}).T


def _porcentagem(valor):
    return f"{valor:.1%}"


def relatorio_modelo(resultado):
    """Relatório em texto da Fase 3."""
    hibrido = resultado["hibrido"]
    sem_regra = hibrido[hibrido["regra"] == "sem_regra"]
    acerto_modelo = (sem_regra["sugestao_modelo"] == sem_regra["categoria"]).mean()
    acerto_mais_comum = (sem_regra["mais_comum"] == sem_regra["categoria"]).mean()
    ambiguos = hibrido[(hibrido["ambigua"] == "sim") & (hibrido["origem"] == "modelo")]

    comparacao = comparar_estrategias(resultado).map(_porcentagem)
    categorias = por_categoria(hibrido)
    categorias[["acertou_sozinho", "errou_sozinho", "perguntou"]] = categorias[
        ["acertou_sozinho", "errou_sozinho", "perguntou"]
    ].map(_porcentagem)
    meses = por_mes(resultado["simulacao"]).map(_porcentagem)

    linhas = [
        "=== Modelo de classificação (Fase 3) ===",
        "Só saídas de dinheiro, só usuários de teste (divisão por usuário, 3 rodadas).",
        f"Valor de C escolhido em cada rodada: {resultado['valores_c']}",
        "",
        "Comparação das estratégias:",
        comparacao.to_string(),
        "",
        f"Nas {len(sem_regra)} saídas que as regras não reconheceram:",
        f"  modelo (1º palpite, sem limite de confiança): {acerto_modelo:.1%} de acerto",
        f"  'categoria mais comum' (referência ingênua):  {acerto_mais_comum:.1%} de acerto",
        f"PIX ambíguos que o modelo decidiu sozinho: {len(ambiguos)}"
        + (f" (acertou {(ambiguos['categoria_final'] == ambiguos['categoria']).mean():.0%})" if len(ambiguos) else ""),
        "",
        "Regras + modelo, por categoria real:",
        categorias.to_string(),
        "",
        "Ciclo de correção, mês a mês:",
        meses.to_string(),
        "",
        "Lembrete: dados sintéticos; o treino usa categorias verdadeiras de outros usuários.",
    ]
    return "\n".join(linhas)


def exemplos(hibrido, quantidade=8, semente=0):
    """Acertos, erros e perguntas do modelo, para mostrar ao maestro."""
    do_modelo = hibrido[hibrido["origem"] == "modelo"]
    acertos = do_modelo[do_modelo["categoria_final"] == do_modelo["categoria"]]
    erros = do_modelo[do_modelo["categoria_final"] != do_modelo["categoria"]]
    perguntas = hibrido[(hibrido["origem"] == "pergunta") & (hibrido["sugestao_modelo"] != "")]
    colunas = ["descricao", "categoria_final", "confianca_final", "sugestao_modelo", "categoria"]

    def amostra(tabela):
        return tabela[colunas].sample(min(quantidade, len(tabela)), random_state=semente)

    return {"acertos": amostra(acertos), "erros": amostra(erros), "perguntas": amostra(perguntas)}


def _grupo_de_loja(tabela):
    """Classifica cada transação de teste como loja nova, loja já vista ou sem loja."""
    return tabela["loja_nova"].map({True: "loja nova"}).fillna(
        tabela["loja"].map(lambda loja: "loja já vista" if loja else "sem loja (ex.: PIX p/ pessoa)")
    )


def comparar_por_grupo_de_loja(resultado):
    """Para cada grupo (loja nova / já vista / sem loja), as três estratégias lado a lado."""
    hibrido, simulacao = resultado["hibrido"], resultado["simulacao"]
    grupos_hibrido, grupos_simulacao = _grupo_de_loja(hibrido), _grupo_de_loja(simulacao)
    linhas = []
    for grupo in ["loja nova", "loja já vista", "sem loja (ex.: PIX p/ pessoa)"]:
        parte, parte_simulada = hibrido[grupos_hibrido == grupo], simulacao[grupos_simulacao == grupo]
        estrategias = {
            "só regras": metricas(parte, "categoria_regra", "perguntar_regra"),
            "regras + modelo": metricas(parte),
            "+ correções": metricas(parte_simulada),
        }
        for nome, valores in estrategias.items():
            linhas.append({"grupo": grupo, "transacoes": len(parte), "estrategia": nome, **valores})
    return pd.DataFrame(linhas).set_index(["grupo", "transacoes", "estrategia"])


def relatorio_teste_duro(resultado):
    """Relatório do teste duro: o modelo em lojas que nunca viu."""
    hibrido = resultado["hibrido"]
    sem_regra = hibrido[hibrido["regra"] == "sem_regra"]
    palpite_novas = sem_regra[sem_regra["loja_nova"]]
    palpite_vistas = sem_regra[~sem_regra["loja_nova"] & (sem_regra["loja"] != "")]
    acerto = lambda tabela: (tabela["sugestao_modelo"] == tabela["categoria"]).mean()

    linhas = [
        "=== Teste duro (Fase 3): lojas que o modelo nunca viu ===",
        "Em cada rodada saem do treino os usuários de teste E 1/3 das lojas de cada categoria",
        f"(só categorias com {MINIMO_DE_LOJAS}+ lojas). Valor de C por rodada: {resultado['valores_c']}",
        "",
        comparar_por_grupo_de_loja(resultado).map(_porcentagem).to_string(),
        "",
        "1º palpite do modelo nas saídas que as regras não reconheceram:",
        f"  lojas já vistas: {acerto(palpite_vistas):.1%} de acerto ({len(palpite_vistas)} transações)",
        f"  lojas novas:     {acerto(palpite_novas):.1%} de acerto ({len(palpite_novas)} transações)",
        "",
        "Lembrete: dados sintéticos; mesmo lojas 'novas' foram escritas por quem fez o gerador.",
    ]
    return "\n".join(linhas)
