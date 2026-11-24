"""Avaliação final (Fase 10): os indicadores da seção 19 da proposta.

A proposta sugere medir a eficácia por: transações corretamente classificadas, capacidade de
poupança, acompanhamento de metas, evolução da reserva, comprometimento futuro da renda e
gastos inesperados. Com dados sintéticos de 6 meses, dá para medir o que o sistema MOSTRA ao
usuário e se acerta; não dá para medir se o comportamento das pessoas melhora com o uso.
"""

import pandas as pd

from financas.experimento import metricas
from financas.metas import acompanhar, meta_exemplo, previsao


def indicadores_por_usuario(indicadores, compromissos, aportes, usuarios_verdade):
    """Uma linha por usuário com os indicadores da seção 19 que dependem só do sistema."""
    meta = meta_exemplo(aportes.columns[0])
    linhas = []
    for linha in indicadores.to_dict("records"):
        usuario = linha["id_usuario"]
        resumo = previsao(meta, acompanhar(meta, list(aportes.loc[usuario])))
        proximos = compromissos.loc[usuario]
        linhas.append({
            "id_usuario": usuario,
            "taxa_de_sobra": linha["taxa_de_sobra"],
            "poupanca_por_mes": linha["poupanca_por_mes"],
            "comprometido_agora": linha["percentual_comprometido"],
            "comprometido_em_6_meses": proximos.iloc[5] / linha["renda_referencia"] if linha["renda_referencia"] else 0.0,
            "variacao_gastos": linha["variacao_gastos"],
            "meta_situacao": resumo["situacao"],
            "meta_percentual": resumo["acumulado"] / meta.valor_alvo,
        })
    return pd.DataFrame(linhas).merge(usuarios_verdade[["id_usuario", "perfil"]], on="id_usuario")


def resumo_por_perfil(por_usuario):
    """Médias por perfil (o que mais importa: perfis diferentes recebem diagnósticos diferentes)."""
    numeros = ["taxa_de_sobra", "poupanca_por_mes", "comprometido_agora", "comprometido_em_6_meses", "variacao_gastos", "meta_percentual"]
    return por_usuario.groupby("perfil")[numeros].mean()


def relatorio_final(saidas_sistema, verdade, por_usuario, anomalias):
    """Texto da avaliação final com os indicadores da seção 19."""
    classificacao = metricas(saidas_sistema.merge(verdade[["id_transacao", "categoria"]], on="id_transacao"))
    previstos = anomalias["por_tipo"][anomalias["por_tipo"]["previsto"] == "sim"]
    nao_previstos = anomalias["por_tipo"][anomalias["por_tipo"]["previsto"] == "não"]
    perfil = resumo_por_perfil(por_usuario)
    formatado = perfil.copy()
    for coluna in formatado.columns:
        formatado[coluna] = formatado[coluna].map(
            (lambda valor: f"R$ {valor:,.0f}".replace(",", ".")) if coluna == "poupanca_por_mes" else (lambda valor: f"{valor:.0%}")
        )
    situacoes = por_usuario["meta_situacao"].value_counts()
    linhas = [
        "=== Avaliação final (Fase 10): indicadores da seção 19 da proposta ===",
        "",
        "1. Transações corretamente classificadas (sistema em uso, sem respostas do usuário):",
        f"   {classificacao['automaticas']:.1%} decididas sozinho, {classificacao['precisao']:.1%} de acerto, "
        f"{classificacao['erros_silenciosos']:.1%} de erros silenciosos, {classificacao['perguntas']:.1%} viram pergunta.",
        "",
        "2. Gastos inesperados (anomalias plantadas que o método estatístico encontrou):",
        f"   tipos previstos {previstos['detectadas'].sum()}/{previstos['plantadas'].sum()}, "
        f"tipos não previstos {nao_previstos['detectadas'].sum()}/{nao_previstos['plantadas'].sum()}, "
        f"{anomalias['precisao_geral']:.0%} dos alertas acertam alguma anomalia.",
        "",
        "3 a 6. Capacidade de poupança, reserva, comprometimento futuro e metas, por perfil (médias):",
        formatado.rename(columns={
            "taxa_de_sobra": "sobra", "poupanca_por_mes": "poupança/mês", "comprometido_agora": "parcelas agora",
            "comprometido_em_6_meses": "parcelas em 6 meses", "variacao_gastos": "gastos 2º x 1º tri", "meta_percentual": "meta R$4.000",
        }).to_string(),
        "",
        "   Meta exemplo (R$ 4.000 em 10 meses) após 6 meses: "
        + ", ".join(f"{quantidade} {situacao}" for situacao, quantidade in situacoes.items()),
        "",
        "O que NÃO dá para medir aqui: se as pessoas passam a poupar mais, gastar menos de forma",
        "inesperada ou reduzir dívidas POR CAUSA do sistema. Isso exige usuários reais acompanhados",
        "ao longo do tempo (de preferência comparando com quem não usa). Os números acima mostram",
        "que o sistema mede esses indicadores e diferencia os perfis, não que muda comportamento.",
    ]
    return "\n".join(linhas)
