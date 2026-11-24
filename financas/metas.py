"""Metas financeiras (Fase 7).

O usuário informa quanto quer juntar e em quantos meses. O sistema calcula quanto
reservar por mês, compara com a sobra que ele costuma ter e acompanha o progresso
mês a mês. Se o ritmo real for menor que o necessário, avisa quanto tempo a meta
deve levar mantendo o ritmo atual. Nunca recomenda onde aplicar o dinheiro.
"""

import math
from dataclasses import dataclass

import pandas as pd

from financas.diagnostico import movimentos_da_poupanca
from financas.formatacao import mes_por_extenso, reais

# Margem para dizer que a meta está "no ritmo": até 5% abaixo ou acima do esperado
TOLERANCIA_RITMO = 0.05
# Referência educativa de reserva de emergência (escolha de projeto, ajustável):
# meses de gastos essenciais para renda fixa e para renda variável/autônoma
MESES_RESERVA_FIXA = 3
MESES_RESERVA_VARIAVEL = 6


def _duracao(meses):
    """14 -> '14 meses'; 462 -> '462 meses (cerca de 38 anos)'."""
    texto = f"{meses} meses"
    return texto + f" (cerca de {meses // 12} anos)" if meses >= 24 else texto


def _rever_meta(meses_previstos, prazo):
    """Sugestão neutra quando a previsão passa do dobro do prazo."""
    return " Pode valer rever o valor ou o prazo da meta." if meses_previstos > 2 * prazo else ""


@dataclass(frozen=True)
class Meta:
    nome: str
    valor_alvo: float
    prazo_meses: int
    mes_inicio: str  # ex.: "2026-01"
    ja_guardado: float = 0.0

    @property
    def valor_mensal(self):
        """Quanto reservar por mês para chegar no prazo."""
        return max(self.valor_alvo - self.ja_guardado, 0) / self.prazo_meses

    @property
    def mes_final(self):
        return str(pd.Period(self.mes_inicio, freq="M") + self.prazo_meses - 1)


def plano_da_meta(meta, sobra_media, alto_comprometimento=False, tipo_renda="fixa"):
    """Texto com o valor mensal e a comparação com a sobra média do usuário (None = renda não informada)."""
    texto = (
        f'Meta "{meta.nome}": juntar {reais(meta.valor_alvo)} até {mes_por_extenso(meta.mes_final)} '
        f"({meta.prazo_meses} meses). É preciso reservar cerca de {reais(meta.valor_mensal)} por mês."
    )
    if sobra_media is None:  # renda não informada (ex.: só a fatura do cartão)
        return texto + " Informe a renda mensal para comparar com a sua sobra média."
    if sobra_media <= 0:
        texto += (
            " Hoje, em média, não sobra dinheiro no fim do mês; para a meta caber, seria preciso "
            "aumentar a renda ou reduzir algum gasto."
        )
    elif meta.valor_mensal > sobra_media:
        meses = math.ceil(max(meta.valor_alvo - meta.ja_guardado, 0) / sobra_media)
        texto += (
            f" Isso é mais que a sobra média ({reais(sobra_media)}). Usando toda a sobra média, "
            f"a meta levaria cerca de {_duracao(meses)}."
        ) + _rever_meta(meses, meta.prazo_meses)
    else:
        texto += f" Cabe na sobra média ({reais(sobra_media)}), usando {meta.valor_mensal / sobra_media:.0%} dela."
    if alto_comprometimento or tipo_renda != "fixa":
        texto += (
            " Como a renda tem alta variação ou muitas parcelas, uma ordem comum é: primeiro as "
            "obrigações e uma reserva para meses difíceis, depois os outros objetivos."
        )
    return texto


def acompanhar(meta, aportes):
    """Acompanha a meta mês a mês.

    aportes: valores guardados em cada mês, a partir do mês de início (lista ou Series).
    Devolve uma tabela com acumulado, esperado e situação de cada mês.
    """
    linhas, acumulado = [], meta.ja_guardado
    for indice, aporte in enumerate(aportes, start=1):
        acumulado += aporte
        esperado = meta.ja_guardado + meta.valor_mensal * min(indice, meta.prazo_meses)
        linhas.append({
            "mes": str(pd.Period(meta.mes_inicio, freq="M") + indice - 1),
            "aporte": round(aporte, 2),
            "acumulado": round(acumulado, 2),
            "esperado": round(esperado, 2),
            "situacao": _situacao(acumulado, esperado, meta.valor_alvo),
        })
    return pd.DataFrame(linhas)


def _situacao(acumulado, esperado, alvo):
    if acumulado >= alvo:
        return "concluída"
    if acumulado < esperado * (1 - TOLERANCIA_RITMO):
        return "atrasada"
    if acumulado > esperado * (1 + TOLERANCIA_RITMO):
        return "adiantada"
    return "no ritmo"


def previsao(meta, acompanhamento):
    """Resumo do progresso e previsão de conclusão mantendo o ritmo atual."""
    meses_passados = len(acompanhamento)
    acumulado = acompanhamento["acumulado"].iloc[-1] if meses_passados else meta.ja_guardado
    ritmo = (acumulado - meta.ja_guardado) / meses_passados if meses_passados else 0.0
    falta = max(meta.valor_alvo - acumulado, 0)
    meses_restantes_no_prazo = max(meta.prazo_meses - meses_passados, 0)
    situacao = acompanhamento["situacao"].iloc[-1] if meses_passados else "no ritmo"

    resultado = {
        "acumulado": round(acumulado, 2),
        "ritmo_mensal": round(ritmo, 2),
        "falta": round(falta, 2),
        "situacao": situacao,
        "meses_previstos": None,
        "mensal_para_cumprir_prazo": None,
    }
    texto = (
        f"Depois de {meses_passados} meses: {reais(acumulado)} guardados "
        f"({acumulado / meta.valor_alvo:.0%} da meta), ritmo médio de {reais(ritmo)} por mês. Situação: {situacao}."
    )
    if falta == 0:
        texto += " A meta foi atingida."
    elif ritmo <= 0:
        texto += " Até agora não houve valor guardado, então não dá para estimar quando a meta será atingida."
    else:
        total = meses_passados + math.ceil(falta / ritmo)
        resultado["meses_previstos"] = total
        if total > meta.prazo_meses:
            texto += (
                f" Mantendo o ritmo atual, a meta deve levar cerca de {_duracao(total)}, "
                f"{total - meta.prazo_meses} meses a mais que o planejado."
            ) + _rever_meta(total, meta.prazo_meses)
        else:
            texto += f" Mantendo o ritmo atual, a meta deve ser atingida em cerca de {total} meses, dentro do prazo."
    if falta > 0 and situacao == "atrasada" and meses_restantes_no_prazo > 0:
        necessario = falta / meses_restantes_no_prazo
        resultado["mensal_para_cumprir_prazo"] = round(necessario, 2)
        texto += (
            f" Para terminar no prazo, seria preciso guardar {reais(necessario)} por mês "
            f"nos {meses_restantes_no_prazo} meses restantes."
        )
    resultado["explicacao"] = texto
    return resultado


def reserva_de_referencia(gastos_essenciais_mensais, tipo_renda):
    """Valor educativo de reserva: meses de gastos essenciais (mais meses se a renda varia)."""
    meses = MESES_RESERVA_FIXA if tipo_renda == "fixa" else MESES_RESERVA_VARIAVEL
    return round(gastos_essenciais_mensais * meses, 2), meses


def aportes_por_mes(classificado, meses):
    """Quanto cada usuário guardou em cada mês: saldo líquido das transferências para a poupança."""
    movimentos = movimentos_da_poupanca(classificado)
    tabela = movimentos.pivot_table(index="id_usuario", columns="mes", values="valor", aggfunc="sum", fill_value=0)
    return tabela.reindex(index=sorted(classificado["id_usuario"].unique()), columns=meses, fill_value=0)


def meta_exemplo(mes_inicio):
    """A meta da proposta: R$ 4.000 para um computador em 10 meses."""
    return Meta("Computador novo", 4000.0, 10, mes_inicio)


def relatorio_metas(indicadores, aportes):
    """Aplica a meta exemplo a cada usuário, acompanhando com o que ele realmente guardou."""
    meses = list(aportes.columns)
    meta = meta_exemplo(meses[0])
    linhas = [
        "=== Metas financeiras (Fase 7) ===",
        f"Meta exemplo para todos: {reais(meta.valor_alvo)} em {meta.prazo_meses} meses, a partir de "
        f"{mes_por_extenso(meta.mes_inicio)}. O acompanhamento usa o que cada um transferiu para a poupança.",
        "",
    ]
    for linha in indicadores.to_dict("records"):
        usuario = linha["id_usuario"]
        acompanhamento = acompanhar(meta, list(aportes.loc[usuario]))
        resumo = previsao(meta, acompanhamento)
        reserva, meses_reserva = reserva_de_referencia(linha["essenciais"], linha["tipo_renda"])
        linhas += [
            f"--- {usuario} ---",
            plano_da_meta(meta, linha["sobra_media"], linha["alto_comprometimento"], linha["tipo_renda"]),
            resumo["explicacao"],
            "  " + " | ".join(f"{a['mes'][5:]}: {reais(a['acumulado'])} ({a['situacao']})" for a in acompanhamento.to_dict("records")),
            f"Referência de reserva para meses difíceis: {reais(reserva)} ({meses_reserva} meses de gastos essenciais).",
            "",
        ]
    linhas.append("Lembrete: meta e referência de reserva são exemplos; o sistema não indica onde aplicar o dinheiro.")
    return "\n".join(linhas)
