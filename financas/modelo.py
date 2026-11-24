"""Modelo de classificação (Fase 3) e classificação híbrida.

Ordem de decisão para cada saída de dinheiro:
1. Regras (Fase 2): se alguma regra reconhecer, ela decide.
2. Memória do usuário: se o usuário já disse o que é um pagamento para esta contraparte.
3. Modelo: lê a descrição e devolve uma categoria com uma probabilidade (a confiança).
Abaixo de 0,70 de confiança o sistema pergunta ao usuário em vez de decidir.

Entradas de dinheiro ficam com o resultado das regras; renda é tratada na Fase 4.
"""

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.pipeline import make_pipeline

from financas import SEMENTE
from financas.normalizacao import chave_de_loja
from financas.regras import CONFIANCA_MINIMA, parece_pessoa

CONFIANCA_MEMORIA = 0.90
CONFIANCA_COLETIVO = 0.85  # confirmado por outras pessoas: confiável, mas abaixo da própria resposta
# Semelhança mínima para reaproveitar a resposta dada para uma loja escrita de outro jeito
# (decidida antes de medir; é o mesmo limite usado para "loja já vista" nas anomalias)
SEMELHANCA_MEMORIA = 0.5
# Trava de segurança: num PIX para uma pessoa, só o usuário sabe a finalidade.
# O palpite do modelo nunca passa desta confiança, então vira pergunta.
CONFIANCA_MAXIMA_PIX_PESSOA = 0.50


def criar_modelo(c=1.0):
    """TF-IDF de pedaços de 2 a 4 letras + regressão logística.

    Pedaços de letras (n-gramas de caracteres) funcionam mesmo com nomes abreviados
    ou colados: "SUPERMERCADOBOMPRECO" ainda contém "MERC", "BOM", "PREC".
    O parâmetro c controla o quanto o modelo pode se ajustar aos exemplos de treino.
    """
    return make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True),
        LogisticRegression(C=c, max_iter=3000, random_state=SEMENTE),
    )


def treinar(textos, categorias, c=1.0):
    modelo = criar_modelo(c)
    modelo.fit(list(textos), list(categorias))
    return modelo


def prever(modelo, textos):
    """Devolve, para cada texto, a categoria mais provável e sua probabilidade."""
    probabilidades = modelo.predict_proba(list(textos))
    indices = probabilidades.argmax(axis=1)
    return modelo.classes_[indices], probabilidades.max(axis=1)


def buscar_na_memoria(memoria, usuario, contraparte):
    """Procura a resposta do usuário para esta contraparte. Devolve (categoria, nome lembrado) ou None.

    - Nome exatamente igual: sempre vale.
    - Lojas com nome escrito diferente ("LV*SUSHIKAZU" e "SUSHI KAZU 1234"): vale se forem
      parecidas o bastante (pedaços de letras em comum).
    - Pessoas: só nome exato. "MARIA SILVA" e "MARIA SOUZA" são pessoas diferentes.
    """
    if (usuario, contraparte) in memoria:
        return memoria[(usuario, contraparte)], contraparte
    if parece_pessoa(contraparte):
        return None
    # Nomes curtos de loja ("SUSHI KAZU") podem parecer de pessoa: entram como candidatos mesmo assim
    candidatos = [nome for (dono, nome) in memoria if dono == usuario]
    if not candidatos:
        return None
    parecido = _nome_mais_parecido(chave_de_loja(contraparte), [chave_de_loja(nome) for nome in candidatos])
    if parecido is None:
        return None
    return memoria[(usuario, candidatos[parecido])], candidatos[parecido]


def _nome_mais_parecido(chave, chaves_candidatas):
    """Posição da chave de loja mais parecida (pedaços de 3 letras), ou None se nenhuma for parecida o bastante."""
    if not chave or not chaves_candidatas:
        return None
    vetores = TfidfVectorizer(analyzer="char", ngram_range=(3, 3)).fit_transform([chave] + list(chaves_candidatas))
    semelhancas = cosine_similarity(vetores[0], vetores[1:])[0]
    melhor = int(semelhancas.argmax())
    return melhor if semelhancas[melhor] >= SEMELHANCA_MEMORIA else None


def buscar_no_coletivo(conhecimento, contraparte, pix_para_pessoa=False):
    """Procura a loja no que os usuários já ensinaram. Devolve (categoria, votos, nome) ou None.

    PIX para pessoas nunca entra (PIX para "CARLOS LOPES" é assunto de cada um).
    """
    if not conhecimento or pix_para_pessoa:
        return None
    chave = chave_de_loja(contraparte)
    if chave in conhecimento:
        return conhecimento[chave]
    chaves = list(conhecimento)
    parecido = _nome_mais_parecido(chave, chaves)
    return conhecimento[chaves[parecido]] if parecido is not None else None


def _nome_categoria(categoria):
    return categoria.replace("_", " ")


def classificar_hibrido(classificado, modelo, memoria=None, conhecimento=None):
    """Combina regras, memória do usuário, conhecimento coletivo e modelo.

    classificado: saída de classificar_por_regras.
    memoria: dicionário {(id_usuario, contraparte): categoria} com respostas do usuário.
    conhecimento: lojas aprendidas com outros usuários {chave: (categoria, votos, nome)}.
    """
    memoria = memoria or {}
    tabela = classificado.copy().reset_index(drop=True)
    tabela["perguntar_regra"] = tabela["confianca"] < CONFIANCA_MINIMA  # decisão só das regras
    tabela["categoria_final"] = tabela["categoria_regra"]
    tabela["confianca_final"] = tabela["confianca"]
    tabela["origem"] = "regra"
    tabela["explicacao_final"] = tabela["explicacao"]
    tabela["sugestao_modelo"] = ""
    tabela["confianca_modelo"] = float("nan")

    sem_regra = (tabela["regra"] == "sem_regra") & (tabela["direcao"] == "saida")

    # Memória: respostas que o próprio usuário já deu (iguais ou, para lojas, parecidas)
    lembrado = pd.Series(False, index=tabela.index)
    for i in tabela.index[sem_regra]:
        achado = buscar_na_memoria(memoria, tabela.loc[i, "id_usuario"], tabela.loc[i, "contraparte"])
        if achado is None:
            continue
        categoria, lembrada = achado
        lembrado[i] = True
        tabela.loc[i, ["categoria_final", "confianca_final", "origem"]] = [categoria, CONFIANCA_MEMORIA, "memoria"]
        texto = f'Você já informou que pagamentos para "{lembrada}" são {_nome_categoria(categoria)}.'
        if lembrada != tabela.loc[i, "contraparte"]:
            texto += f' "{tabela.loc[i, "contraparte"]}" parece ser o mesmo lugar.'
        tabela.loc[i, "explicacao_final"] = texto

    # Conhecimento coletivo: lojas que outros usuários já confirmaram
    for i in tabela.index[sem_regra & ~lembrado]:
        pix_para_pessoa = tabela.loc[i, "operacao"] == "pix_enviado" and parece_pessoa(tabela.loc[i, "contraparte"])
        achado = buscar_no_coletivo(conhecimento, tabela.loc[i, "contraparte"], pix_para_pessoa)
        if achado is None:
            continue
        categoria, votos, nome = achado
        lembrado[i] = True
        tabela.loc[i, ["categoria_final", "confianca_final", "origem"]] = [categoria, CONFIANCA_COLETIVO, "coletivo"]
        tabela.loc[i, "explicacao_final"] = (
            f'Aprendido com confirmações de outros usuários: "{nome}" é {_nome_categoria(categoria)} ({votos} votos).'
        )

    # Modelo: só para o que as regras, a memória e o conhecimento coletivo não resolveram
    para_modelo = sem_regra & ~lembrado
    if para_modelo.any():
        categorias, confiancas = prever(modelo, tabela.loc[para_modelo, "descricao"])
        tabela.loc[para_modelo, "sugestao_modelo"] = categorias
        tabela.loc[para_modelo, "confianca_modelo"] = confiancas
        tabela.loc[para_modelo, "categoria_final"] = categorias
        tabela.loc[para_modelo, "confianca_final"] = confiancas
        tabela.loc[para_modelo, "origem"] = "modelo"
        pix_pessoa = (tabela["operacao"] == "pix_enviado") & tabela["contraparte"].map(parece_pessoa)
        travado = para_modelo & pix_pessoa
        tabela.loc[travado, "confianca_final"] = tabela.loc[travado, "confianca_final"].clip(upper=CONFIANCA_MAXIMA_PIX_PESSOA)
        for i in tabela.index[para_modelo]:
            categoria, confianca = tabela.loc[i, "sugestao_modelo"], tabela.loc[i, "confianca_modelo"]
            if travado[i]:
                texto = (
                    f"PIX para uma pessoa: o modelo arrisca {_nome_categoria(categoria)}, "
                    "mas só o usuário sabe a finalidade. Perguntar ao usuário."
                )
            elif confianca >= CONFIANCA_MINIMA:
                texto = f"O modelo achou a descrição parecida com outras de {_nome_categoria(categoria)} (confiança {confianca:.0%})."
            else:
                texto = f"Confiança baixa ({confianca:.0%}); talvez seja {_nome_categoria(categoria)}. Perguntar ao usuário."
            tabela.loc[i, "explicacao_final"] = texto

    # Confiança baixa: não inventar, perguntar
    tabela["perguntar_usuario"] = tabela["confianca_final"] < CONFIANCA_MINIMA
    perguntar = tabela["perguntar_usuario"]
    tabela.loc[perguntar, "origem"] = "pergunta"
    saida_sem_resposta = perguntar & (tabela["direcao"] == "saida")
    tabela.loc[saida_sem_resposta, "categoria_final"] = "nao_identificado"
    return tabela
