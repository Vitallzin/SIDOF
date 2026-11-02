"""Avaliação e relatórios. Só este módulo carrega os arquivos de verdade.

A verdade serve para medir o desempenho e, no experimento da Fase 3, para simular
usuários que já confirmaram suas categorias. Nunca é usada para classificar
as transações de quem está sendo testado.
"""

from pathlib import Path

import pandas as pd

from financas.diagnostico import NOMES_BLOCOS, diagnosticar
from financas.gerador import PASTA_PADRAO, TIPOS_NAO_PREVISTOS


def carregar_verdade(pasta=PASTA_PADRAO):
    return pd.read_csv(Path(pasta) / "verdade.csv", keep_default_na=False)


def carregar_usuarios_verdade(pasta=PASTA_PADRAO):
    return pd.read_csv(Path(pasta) / "usuarios_verdade.csv")


def avaliar_regras(classificado, verdade):
    """Compara a classificação por regras com a verdade.

    Devolve um dicionário com:
    - cobertura: % das transações que alguma regra reconheceu
    - perguntas: % das transações que vão gerar pergunta ao usuário
    - precisao: % de acertos entre as transações reconhecidas por regra
    - por_regra: tabela com quantidade e acertos de cada regra
    - erros: transações reconhecidas por regra com categoria errada
    - nao_identificadas: transações sem regra, com a categoria real
    """
    junto = classificado.merge(verdade[["id_transacao", "categoria", "ambigua"]], on="id_transacao")
    junto["acertou"] = junto["categoria_regra"] == junto["categoria"]
    reconhecidas = junto[junto["regra"] != "sem_regra"]

    por_regra = reconhecidas.groupby("regra").agg(
        quantidade=("acertou", "size"),
        acertos=("acertou", "sum"),
        confianca=("confianca", "first"),
    )
    por_regra["precisao"] = por_regra["acertos"] / por_regra["quantidade"]

    return {
        "total": len(junto),
        "cobertura": len(reconhecidas) / len(junto),
        "perguntas": junto["perguntar_usuario"].mean(),
        "precisao": reconhecidas["acertou"].mean(),
        "por_regra": por_regra.sort_values("quantidade", ascending=False),
        "erros": reconhecidas[~reconhecidas["acertou"]],
        "nao_identificadas": junto[junto["regra"] == "sem_regra"],
    }


def relatorio_regras(resultado):
    """Relatório em texto da Fase 2."""
    nao_identificadas = resultado["nao_identificadas"]
    linhas = [
        "=== Classificação por regras (Fase 2) ===",
        f"Transações: {resultado['total']}",
        f"Reconhecidas por alguma regra: {resultado['cobertura']:.1%}",
        f"Acertos entre as reconhecidas: {resultado['precisao']:.1%}",
        f"Vão gerar pergunta ao usuário: {resultado['perguntas']:.1%}",
        "",
        "Por regra (quantidade, confiança da regra, acertos):",
    ]
    for nome, linha in resultado["por_regra"].iterrows():
        linhas.append(f"  {nome:<22} {int(linha['quantidade']):>5}   conf. {linha['confianca']:.2f}   acertos {linha['precisao']:.0%}")

    linhas += ["", f"Erros das regras ({len(resultado['erros'])}):"]
    for _, linha in resultado["erros"].drop_duplicates("descricao").iterrows():
        linhas.append(f"  {linha['descricao']:<40} regra disse {linha['categoria_regra']}, real é {linha['categoria']}")

    linhas += ["", f"Não identificadas ({len(nao_identificadas)}), agrupadas por motivo:"]
    for explicacao, quantidade in nao_identificadas["explicacao"].value_counts().items():
        linhas.append(f"  {quantidade:>5}  {explicacao}")

    linhas += ["", "Não identificadas, por categoria real:"]
    for categoria, quantidade in nao_identificadas["categoria"].value_counts().items():
        linhas.append(f"  {quantidade:>5}  {categoria}")

    linhas += ["", "Lembrete: dados sintéticos e regras escritas conhecendo o gerador; o desempenho real seria menor."]
    return "\n".join(linhas)


# Perfil real (gerador) -> tipo de renda esperado
TIPO_ESPERADO = {
    "renda_fixa_poucos_compromissos": "fixa",
    "renda_variavel_autonomo": "autonoma",
    "renda_fixa_com_dividas": "fixa",
    "renda_baixa_pouca_margem": "fixa",
}


def avaliar_renda(entradas, perfis, verdade, usuarios_verdade):
    """Compara a classificação das entradas e o perfil de renda com a verdade."""
    junto = entradas.merge(verdade[["id_transacao", "categoria"]], on="id_transacao")
    junto["acertou"] = junto["categoria_renda"] == junto["categoria"]
    junto["acertou_regras"] = junto["categoria_regra"] == junto["categoria"]
    automaticas = ~junto["perguntar_usuario"]

    perfis = perfis.merge(usuarios_verdade, on="id_usuario", suffixes=("", "_real"))
    perfis["tipo_esperado"] = perfis["perfil"].map(TIPO_ESPERADO)
    # Acerta quando o tipo de renda e a troca de emprego batem com a verdade
    perfis["acertou"] = (perfis["tipo_renda"] == perfis["tipo_esperado"]) & (
        perfis["troca_emprego"] == perfis["troca_emprego_real"]
    )

    return {
        "entradas": junto,
        "acerto_regras": junto["acertou_regras"].mean(),
        "acerto": junto["acertou"].mean(),
        "automaticas": automaticas.mean(),
        "precisao_automaticas": junto.loc[automaticas, "acertou"].mean(),
        "confusao": pd.crosstab(junto["categoria"], junto["categoria_renda"]),
        "perfis": perfis,
    }


def relatorio_renda(resultado):
    """Relatório em texto da Fase 4."""
    entradas, perfis = resultado["entradas"], resultado["perfis"]
    linhas = [
        "=== Renda e transferências internas (Fase 4) ===",
        f"Entradas de dinheiro: {len(entradas)}",
        f"Origem correta (1º palpite): só regras da Fase 2 {resultado['acerto_regras']:.1%} -> Fase 4 {resultado['acerto']:.1%}",
        f"Decididas sem perguntar: {resultado['automaticas']:.1%}, com {resultado['precisao_automaticas']:.1%} de acerto",
        "",
        "Categoria real (linhas) x categoria da Fase 4 (colunas):",
        resultado["confusao"].to_string(),
        "",
        f"Perfil de renda identificado corretamente: {perfis['acertou'].sum()} de {len(perfis)}",
    ]
    for _, perfil in perfis.iterrows():
        marca = "OK " if perfil["acertou"] else "ERRO"
        linhas.append(f"  [{marca}] {perfil['id_usuario']} ({perfil['perfil']}): {perfil['explicacao']}")

    dificeis = entradas[~entradas["acertou"] | entradas["perguntar_usuario"]]
    linhas += ["", f"Casos difíceis (erradas ou perguntadas): {len(dificeis)}, agrupados por fonte:"]
    agrupados = dificeis.groupby(["id_usuario", "contraparte", "categoria", "categoria_renda"]).size()
    for (usuario, contraparte, real, previsto), quantidade in agrupados.items():
        marca = "acertou, mas pergunta" if real == previsto else f"errou (disse {previsto})"
        linhas.append(f"  {usuario} {contraparte:<30} {quantidade}x  real: {real:<24} {marca}")
    linhas += ["", "Lembrete: dados sintéticos; os sinais usados (sobrenome, variação) foram pensados junto com o gerador."]
    return "\n".join(linhas)


def contar_parcelamentos(parcelamentos, extrato, verdade):
    """Compara, por usuário, quantos parcelamentos o sistema achou com quantos existem de verdade."""
    junto = extrato.merge(verdade[["id_transacao", "loja"]], on="id_transacao")
    com_parcela = junto[junto["parcela"].fillna("") != ""]
    total_parcelas = com_parcela["parcela"].str.split("/").str[1]
    verdadeiros = com_parcela.assign(total=total_parcelas).groupby(["id_usuario", "loja", "total"]).size()
    contagem = pd.DataFrame({
        "existentes": verdadeiros.groupby("id_usuario").size(),
        "encontrados": parcelamentos.groupby("id_usuario").size(),
    })
    return contagem.reindex(sorted(extrato["id_usuario"].unique())).fillna(0).astype(int)


def relatorio_parcelas(parcelamentos, comprometimento, contagem):
    """Relatório em texto da Fase 5."""
    linhas = [
        "=== Parcelas e compromissos futuros (Fase 5) ===",
        f"Parcelamentos encontrados: {contagem['encontrados'].sum()} de {contagem['existentes'].sum()} existentes "
        f"({(contagem['encontrados'] == contagem['existentes']).sum()} de {len(contagem)} usuários com contagem exata)",
        f"Ainda em aberto: {(parcelamentos['parcelas_restantes'] > 0).sum()}",
        "",
    ]
    for _, usuario in comprometimento.iterrows():
        marca = " [alto comprometimento]" if usuario["alto_comprometimento"] else ""
        linhas.append(f"{usuario['id_usuario']}{marca}: {usuario['explicacao']}")
        do_usuario = parcelamentos[parcelamentos["id_usuario"] == usuario["id_usuario"]]
        for explicacao in do_usuario.sort_values("parcelas_restantes", ascending=False)["explicacao"]:
            linhas.append(f"    - {explicacao}")
    linhas += ["", "Lembrete: dados sintéticos; o limite de 30% para 'alto comprometimento' é uma escolha de projeto."]
    return "\n".join(linhas)


def com_respostas_do_usuario(hibrido):
    """Simula o usuário respondendo todas as perguntas: a resposta é a categoria verdadeira."""
    confirmado = hibrido.copy()
    perguntadas = confirmado["perguntar_usuario"].astype(str) == "True"
    confirmado.loc[perguntadas, "categoria_final"] = confirmado.loc[perguntadas, "categoria"]
    return confirmado


def comparar_diagnosticos(classificado, usuarios, hibrido):
    """Diferença média (R$ por mês) de cada bloco em relação ao diagnóstico feito com a verdade."""
    verdade_completa = hibrido.assign(categoria_final=hibrido["categoria"])
    versoes = {
        "sem respostas": hibrido,
        "com respostas do usuário": com_respostas_do_usuario(hibrido),
    }
    referencia, _ = diagnosticar(classificado, usuarios, saidas=verdade_completa)
    colunas = NOMES_BLOCOS + ["sobra_media"]
    linhas = {}
    for nome, saidas in versoes.items():
        tabela, _ = diagnosticar(classificado, usuarios, saidas=saidas)
        linhas[nome] = (tabela[colunas] - referencia[colunas]).abs().mean()
    return pd.DataFrame(linhas).T.round(2)


def relatorio_diagnostico(textos, comparacao):
    """Relatório da Fase 6: precisão do diagnóstico e o texto de cada usuário."""
    linhas = [
        "=== Indicadores e diagnóstico (Fase 6) ===",
        "Os textos abaixo supõem que o usuário respondeu as perguntas do sistema (respostas simuladas).",
        "",
        "Erro médio de cada bloco (R$ por mês) comparado ao diagnóstico feito com as categorias verdadeiras:",
        comparacao.to_string(),
        "",
    ]
    for texto in textos.values():
        linhas += [texto, ""]
    linhas.append("Lembrete: dados sintéticos; os limites dos pontos de atenção são escolhas de projeto.")
    return "\n".join(linhas)


def instancias_plantadas(extrato, verdade):
    """Cada anomalia plantada = conjunto de transações com o mesmo usuário e tipo."""
    junto = extrato[["id_transacao", "id_usuario", "descricao", "valor", "data"]].merge(
        verdade[["id_transacao", "tipo_anomalia"]], on="id_transacao"
    )
    plantadas = junto[junto["tipo_anomalia"] != ""]
    return {
        (usuario, tipo): grupo
        for (usuario, tipo), grupo in plantadas.groupby(["id_usuario", "tipo_anomalia"])
    }


def avaliar_anomalias(alertas, instancias):
    """Precisão e revocação por tipo de anomalia.

    - Um alerta é correto se envolve alguma transação de uma anomalia plantada.
    - Uma anomalia plantada foi detectada se algum alerta envolve alguma das suas transações.
    - Precisão por tipo (só no método estatístico, que diz o tipo): alertas daquele detector
      que acertaram uma anomalia do mesmo tipo; "acerta_alguma" conta qualquer anomalia,
      inclusive as não previstas.
    """
    dono = {id_: chave for chave, grupo in instancias.items() for id_ in grupo["id_transacao"]}
    acertos = [{dono[id_] for id_ in ids if id_ in dono} for ids in alertas["ids"]]
    alertas = alertas.assign(
        correto=[len(acerto) > 0 for acerto in acertos],
        tipos_acertados=[sorted({tipo for _, tipo in acerto}) for acerto in acertos],
    )
    detectadas = set().union(*acertos) if acertos else set()

    linhas = []
    for tipo in sorted({tipo for _, tipo in instancias}):
        do_tipo = [chave for chave in instancias if chave[1] == tipo]
        do_detector = alertas[alertas["detector"] == tipo]
        linhas.append({
            "tipo": tipo,
            "previsto": "não" if tipo in TIPOS_NAO_PREVISTOS else "sim",
            "plantadas": len(do_tipo),
            "detectadas": sum(chave in detectadas for chave in do_tipo),
            "revocacao": sum(chave in detectadas for chave in do_tipo) / len(do_tipo),
            "alertas_do_detector": len(do_detector),
            # Acerta o mesmo tipo do detector / acerta qualquer anomalia (inclusive as não previstas)
            "precisao_do_detector": (
                do_detector["tipos_acertados"].map(lambda tipos: tipo in tipos).mean() if len(do_detector) else float("nan")
            ),
            "acerta_alguma": do_detector["correto"].mean() if len(do_detector) else float("nan"),
        })
    return {
        "por_tipo": pd.DataFrame(linhas).set_index("tipo"),
        "alertas": alertas,
        "precisao_geral": alertas["correto"].mean() if len(alertas) else float("nan"),
        "detectadas": detectadas,
    }


def _descrever_instancia(grupo):
    primeira = grupo.sort_values("data").iloc[0]
    extra = f" (+{len(grupo) - 1} transações)" if len(grupo) > 1 else ""
    return f'{primeira["data"]} "{primeira["descricao"]}" {-primeira["valor"]:.2f}{extra}'


def relatorio_anomalias(resultados, instancias, semente=0):
    """Relatório da Fase 8: estatístico x IsolationForest, com exemplos."""
    estatistico, floresta = resultados["estatístico"], resultados["IsolationForest"]
    linhas = [
        "=== Anomalias (Fase 8) ===",
        f"Anomalias plantadas: {len(instancias)} (só usadas para avaliar; nenhum método as vê).",
        "Tipos 'não previstos' não têm detector próprio: medem se os métodos acham o que ninguém antecipou.",
        "",
    ]
    for nome, resultado in resultados.items():
        tabela = resultado["por_tipo"].copy()
        if nome == "IsolationForest":
            tabela = tabela[["previsto", "plantadas", "detectadas", "revocacao"]]
        por_grupo = resultado["por_tipo"].groupby("previsto")[["plantadas", "detectadas"]].sum()
        linhas += [
            f"--- {nome}: {len(resultado['alertas'])} alertas, {resultado['precisao_geral']:.0%} deles acertam alguma anomalia plantada",
            tabela.to_string(float_format=lambda valor: f"{valor:.0%}"),
            "Revocação: tipos previstos "
            f"{por_grupo.loc['sim', 'detectadas'] / por_grupo.loc['sim', 'plantadas']:.0%} | tipos NÃO previstos "
            f"{por_grupo.loc['não', 'detectadas'] / por_grupo.loc['não', 'plantadas']:.0%}",
            "",
        ]
    so_estatistico = estatistico["detectadas"] - floresta["detectadas"]
    so_floresta = floresta["detectadas"] - estatistico["detectadas"]
    linhas += [
        f"Detectadas só pelo estatístico: {len(so_estatistico)} | só pelo IsolationForest: {len(so_floresta)} | "
        f"pelos dois: {len(estatistico['detectadas'] & floresta['detectadas'])}",
        "",
        "10 anomalias detectadas (método estatístico), com a explicação mostrada ao usuário:",
    ]
    corretos = estatistico["alertas"][estatistico["alertas"]["correto"]]
    exemplos = corretos.groupby("detector").head(3).head(10)
    for alerta in exemplos.itertuples():
        linhas.append(f"  [{alerta.detector}] {alerta.id_usuario}: {alerta.explicacao}")

    linhas += ["", "10 anomalias NÃO detectadas (por algum dos métodos):"]
    perdidas = [
        (chave, [nome for nome, resultado in resultados.items() if chave not in resultado["detectadas"]])
        for chave in sorted(instancias)
    ]
    perdidas = [(chave, nomes) for chave, nomes in perdidas if nomes]
    for (usuario, tipo), nomes in perdidas[:10]:
        linhas.append(f"  [{tipo}] {usuario}: {_descrever_instancia(instancias[(usuario, tipo)])} -> perdida pelo {' e pelo '.join(nomes)}")

    falsos = estatistico["alertas"][~estatistico["alertas"]["correto"]]
    linhas += ["", f"Exemplos de alarmes falsos do estatístico ({len(falsos)} no total):"]
    for alerta in falsos.groupby("detector").head(2).itertuples():
        linhas.append(f"  [{alerta.detector}] {alerta.id_usuario}: {alerta.explicacao}")
    linhas += ["", "Lembrete: dados sintéticos; os limites foram fixados antes de olhar os resultados."]
    return "\n".join(linhas)
