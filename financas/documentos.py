"""Junta os documentos enviados por uma pessoa (faturas e extratos) num extrato só, sem contar nada duas vezes.

Regras contra duplicação (decisões do maestro):
1. Renda: se o extrato já mostra renda (salário ou trabalho) num mês, vale a do extrato. A renda digitada
   entra só nos meses em que o extrato não mostra renda.
2. Fatura + extrato: o pagamento da fatura que aparece no extrato não é gasto (as compras já estão
   detalhadas na fatura). Isso já vale pela regra "pagamento de fatura", que fica fora dos gastos.
3. O mesmo extrato (ou fatura) enviado em dois formatos, por exemplo PDF e CSV, conta uma vez só.
"""

import pandas as pd

from financas.faturas_pdf import DESCRICAO_RENDA_INFORMADA, DIA_RENDA_INFORMADA, ID_FATURA, mes_da_fatura
from financas.extratos import EXTRATO, FATURA
from financas.formatacao import reais
from financas.normalizacao import normalizar
from financas.regras import classificar_por_regras
from financas.renda import CATEGORIAS_RENDA_EFETIVA, classificar_entradas

PALAVRAS_DE_APLICACAO = ("APLICACAO", "RESGATE")


def _sem_repetidas(tabelas, chave):
    """Junta as tabelas; uma linha que aparece em mais de um arquivo conta uma vez só.

    Se o mesmo arquivo tiver a linha repetida (ex.: duas compras iguais no mesmo dia), as repetições
    ficam: pode ser uma cobrança duplicada que a pessoa precisa ver.
    """
    if not tabelas:
        return pd.DataFrame()
    marcadas = [tabela.assign(_vez=tabela.groupby(chave).cumcount()) for tabela in tabelas if len(tabela)]
    if not marcadas:
        return pd.DataFrame()
    return pd.concat(marcadas, ignore_index=True).drop_duplicates(chave + ["_vez"]).drop(columns="_vez")


def _no_mes_da_fatura(compras):
    """Cada fatura conta como um mês: compras de outro mês passam para o dia 1 do mês da fatura."""
    mes = mes_da_fatura(compras)
    fora = compras["data"].str[:7] != mes
    return compras.assign(data=compras["data"].where(~fora, f"{mes}-01"))


def _meio(descricao, tipo, valor):
    texto = f"{descricao} {tipo}".upper()
    if "PIX" in texto:
        return "pix"
    if "BOLETO" in texto:
        return "boleto"
    if "TED" in texto or "TRANSF" in texto or valor > 0:
        return "ted"
    return "cartao_debito"


def _linhas_de_fatura(faturas):
    compras = _sem_repetidas([_no_mes_da_fatura(f) for f in faturas], ["data", "descricao", "parcela", "valor"])
    if compras.empty:
        return []
    compras = compras.sort_values("data", kind="stable")
    return [
        {"data": c.data, "descricao": c.descricao, "valor": -c.valor, "meio": "cartao_credito", "conta": "cartao",
         "parcela": c.parcela, "categoria_banco": ""}
        for c in compras.itertuples()
    ]


def _linhas_de_extrato(extratos):
    movimentos = _sem_repetidas(extratos, ["data", "descricao", "valor"])
    if movimentos.empty:
        return []
    linhas = []
    for m in movimentos.sort_values("data", kind="stable").itertuples():
        linha = {"data": m.data, "descricao": m.descricao, "valor": m.valor, "meio": _meio(m.descricao, m.tipo_banco, m.valor),
                 "conta": "corrente", "parcela": m.parcela, "categoria_banco": m.categoria_banco}
        linhas.append(linha)
        if any(palavra in m.descricao for palavra in PALAVRAS_DE_APLICACAO):
            # Aplicação/resgate: o dinheiro foi para (ou voltou de) um investimento da própria pessoa.
            # A linha espelhada na "poupança" deixa o sistema contar isso como dinheiro guardado,
            # do mesmo jeito que nas transferências entre contas dos dados fictícios.
            linhas.append({**linha, "valor": -m.valor, "conta": "poupanca", "categoria_banco": ""})
    return linhas


def _meses_com_renda(extrato, usuarios):
    """Meses em que o extrato já mostra renda efetiva (salário ou pagamento por trabalho)."""
    if not (extrato["valor"] > 0).any():
        return set()
    entradas = classificar_entradas(classificar_por_regras(normalizar(extrato), usuarios), usuarios)
    efetiva = entradas[entradas["categoria_renda"].isin(CATEGORIAS_RENDA_EFETIVA)]
    return set(efetiva["mes"])


def extrato_de_documentos(documentos, nome, renda_mensal=0.0):
    """Junta faturas e extratos de uma pessoa. Devolve (extrato, usuarios, avisos).

    avisos: frases curtas para a tela explicar o que foi feito com a renda e com o pagamento da fatura.
    """
    faturas = [d.movimentos for d in documentos if d.tipo == FATURA and not d.vazio]
    extratos = [d.movimentos for d in documentos if d.tipo == EXTRATO and not d.vazio]
    linhas = _linhas_de_fatura(faturas) + _linhas_de_extrato(extratos)
    if not linhas:
        raise ValueError("Nenhuma movimentação encontrada nos arquivos.")
    extrato = pd.DataFrame(linhas)
    prefixos = extrato["conta"].map({"cartao": "F", "corrente": "E", "poupanca": "P"})
    extrato.insert(0, "id_transacao", [f"{p}{i:05d}" for i, p in enumerate(prefixos, start=1)])
    extrato.insert(1, "id_usuario", ID_FATURA)
    usuarios = pd.DataFrame({"id_usuario": [ID_FATURA], "nome": [nome.strip() or "TITULAR"]})
    avisos = []

    meses = sorted(extrato["data"].str[:7].unique())
    com_renda = _meses_com_renda(extrato, usuarios) if extratos else set()
    if renda_mensal > 0:
        sem_renda = [mes for mes in meses if mes not in com_renda]
        if com_renda:
            avisos.append(
                f"O extrato já mostra renda em {len(com_renda)} mês(es): usei a renda do extrato, sem somar a digitada "
                f"({reais(renda_mensal)}) de novo."
                + (f" A renda digitada entrou só em {len(sem_renda)} mês(es) sem renda no extrato." if sem_renda else "")
            )
        renda = pd.DataFrame({
            "id_transacao": [f"R{i:03d}" for i in range(1, len(sem_renda) + 1)],
            "id_usuario": ID_FATURA,
            "data": [f"{mes}-{DIA_RENDA_INFORMADA:02d}" for mes in sem_renda],
            "descricao": DESCRICAO_RENDA_INFORMADA,
            "valor": float(renda_mensal),
            "meio": "ted",
            "conta": "corrente",
            "parcela": "",
            "categoria_banco": "",
        })
        extrato = pd.concat([extrato, renda], ignore_index=True)

    if extratos:
        regras = classificar_por_regras(normalizar(extrato), usuarios)
        pagamentos = -regras.loc[regras["categoria_regra"] == "pagamento_fatura", "valor"].sum()
        if pagamentos > 0 and not faturas:
            avisos.append(
                f"O extrato tem {reais(pagamentos)} em pagamentos de fatura de cartão. Eles não contam como gasto "
                "porque o extrato não mostra o que foi comprado: envie também as faturas para ver o detalhe."
            )
        elif pagamentos > 0:
            avisos.append(
                f"Os pagamentos de fatura do extrato ({reais(pagamentos)}) não foram somados: as compras já estão nas faturas."
            )
    extrato = extrato.sort_values("data", kind="stable", ignore_index=True)
    return extrato, usuarios, avisos
