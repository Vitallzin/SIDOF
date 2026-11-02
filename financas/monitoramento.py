"""Monitoramento simulado (Fase 9).

Simula os meses chegando um a um: o sistema só enxerga o extrato até o "mês atual" e,
a cada novo mês, gera notificações sobre o que mudou:
- gastos fora do padrão (alertas da Fase 8 com transações daquele mês)
- novas compras parceladas (parcela 1 naquele mês)
- queda da renda efetiva em relação aos meses anteriores
"""

import pandas as pd

from financas.diagnostico import renda_por_mes
from financas.formatacao import mes_por_extenso, reais
from financas.parcelas import identificar_parcelamentos
from financas.renda import classificar_entradas
from financas.sistema import Sistema

QUEDA_DE_RENDA = 0.20  # avisa se a renda do mês ficou 20% ou mais abaixo da média anterior
MESES_MINIMOS_RENDA = 2

NOMES_ALERTAS = {
    "pico_categoria": "Aumento de gasto",
    "cobranca_duplicada": "Possível cobrança duplicada",
    "estabelecimento_novo_alto": "Compra alta em lugar novo",
    "frequencia_incomum": "Muitas compras em pouco tempo",
}


def extrato_ate(extrato, mes):
    """Só as transações até o fim do mês informado (ex.: '2026-04')."""
    return extrato[extrato["data"].astype(str).str[:7] <= mes]


def _notificacao(usuario, tipo, mensagem):
    return {"id_usuario": usuario, "tipo": tipo, "mensagem": mensagem}


def _alertas_do_mes(sistema, mes):
    meses = sistema.classificado.set_index("id_transacao")["mes"]
    notificacoes = []
    for alerta in sistema.alertas().itertuples():
        if any(meses.get(id_) == mes for id_ in alerta.ids):
            notificacoes.append(_notificacao(alerta.id_usuario, NOMES_ALERTAS[alerta.detector], alerta.explicacao))
    return notificacoes


def _parcelas_novas(sistema, mes):
    parcelamentos = identificar_parcelamentos(sistema.classificado)
    novas = parcelamentos[(parcelamentos["primeira_vista"] == 1) & (parcelamentos["mes_ultima"] == mes)]
    return [
        _notificacao(linha.id_usuario, "Nova parcela", (
            f"Nova compra parcelada em {linha.contraparte}: {linha.total_parcelas}x de {reais(linha.valor_parcela)}. "
            f"Isso compromete {reais(linha.valor_parcela)} por mês até {mes_por_extenso(linha.mes_final)}."
        ))
        for linha in novas.itertuples()
    ]


def _queda_de_renda(sistema, mes):
    meses = sorted(sistema.classificado["mes"].unique())
    anteriores = [m for m in meses if m < mes]
    if len(anteriores) < MESES_MINIMOS_RENDA:
        return []
    renda = renda_por_mes(classificar_entradas(sistema.classificado, sistema.usuarios), meses)
    notificacoes = []
    for usuario, valores in renda.iterrows():
        media = valores[anteriores].mean()
        if media > 0 and valores[mes] < (1 - QUEDA_DE_RENDA) * media:
            notificacoes.append(_notificacao(usuario, "Queda de renda", (
                f"Sua renda efetiva em {mes_por_extenso(mes)} foi {reais(valores[mes])}, "
                f"abaixo da média dos meses anteriores ({reais(media)})."
            )))
    return notificacoes


def notificacoes_do_mes(extrato, usuarios, modelo, mes, memoria=None):
    """Notificações geradas quando o mês 'mes' chega, olhando só o extrato até ele."""
    sistema = Sistema(extrato_ate(extrato, mes), usuarios, modelo)
    sistema.memoria = dict(memoria or {})
    linhas = _queda_de_renda(sistema, mes) + _parcelas_novas(sistema, mes) + _alertas_do_mes(sistema, mes)
    return pd.DataFrame(linhas, columns=["id_usuario", "tipo", "mensagem"])
