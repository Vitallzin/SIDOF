"""Aprendizado contínuo: o que os usuários confirmam sobre lojas vira conhecimento de todos.

Quando alguém confirma "SUSHI KAZU é restaurante" (na aba Perguntas ou ao importar uma fatura),
o voto é guardado. Depois de confirmações de sessões diferentes, a loja passa a ser reconhecida
para qualquer pessoa, e também entra no re-treino do modelo.

O que é guardado: só o nome da loja, a categoria votada, a origem do voto e um código aleatório
da sessão (que não identifica ninguém). Nunca: valores, datas, o arquivo da fatura, nomes de
pessoas (PIX para "CARLOS LOPES") ou entradas de dinheiro.

Duas formas de guardar, com as mesmas funções:
- ArmazenamentoMemoria: na memória do programa (testes e uso local, sem internet)
- ArmazenamentoFirestore: no Firebase (app publicado), chave nos Secrets do Streamlit
"""

from collections import Counter
from datetime import datetime, timezone

from financas.categorias import CATEGORIAS_ANTIGAS, CATEGORIAS
from financas.normalizacao import chave_de_loja, normalizar_texto
from financas.regras import parece_pessoa

MINIMO_DE_CONFIRMACOES = 2  # sessões diferentes que precisam concordar antes de valer para todos
ORIGENS = ("fatura", "ficticio")  # fatura real enviada / usuário fictício da aba Perguntas
GRUPOS_APRENDIVEIS = ("essencial", "prioritario", "discricionario")  # só gastos em lojas
# Dinheiro para a família é sempre para pessoas: nunca vai para o aprendizado coletivo
CATEGORIAS_NAO_APRENDIVEIS = ("transferencia_familiar",)


def eh_pix_para_pessoa(descricao, contraparte):
    """Só um PIX pode ir para uma pessoa; compra no cartão ou no débito é sempre numa loja.

    Por isso "SUSHI KAZU" numa compra de cartão é loja, mesmo parecendo nome de gente.
    """
    return normalizar_texto(descricao).startswith("PIX") and parece_pessoa(normalizar_texto(contraparte))


def pode_aprender(contraparte, categoria, descricao="", tipo_documento=""):
    """Só lojas e só categorias de gasto. PIX para pessoas, renda e transferências ficam de fora.

    tipo_documento: "cnpj" garante que é empresa; "cpf" garante que é pessoa. Sem documento, vale a regra
    cuidadosa: qualquer PIX com forma de nome de pessoa fica fora (privacidade em primeiro lugar).
    """
    nome = normalizar_texto(contraparte)
    pix_pessoa = tipo_documento == "cpf" or (tipo_documento != "cnpj" and eh_pix_para_pessoa(descricao, nome))
    return (
        bool(chave_de_loja(nome))
        and not pix_pessoa
        and CATEGORIAS.get(categoria) in GRUPOS_APRENDIVEIS
        and categoria not in CATEGORIAS_NAO_APRENDIVEIS
    )


def _agora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ArmazenamentoMemoria:
    """Guarda na memória do programa. Some quando o programa fecha."""

    nome = "memória local"

    def __init__(self):
        self.lojas = {}
        self.usos = []

    def salvar_voto(self, chave, nome, sessao, categoria, origem):
        loja = self.lojas.setdefault(chave, {"nome": nome, "votos": {}})
        loja["votos"][sessao] = {"categoria": categoria, "origem": origem}
        loja["atualizado_em"] = _agora()

    def ler_lojas(self):
        return {chave: dict(loja, votos=dict(loja["votos"])) for chave, loja in self.lojas.items()}

    def salvar_uso(self, registro):
        self.usos.append(dict(registro))

    def ler_usos(self):
        return list(self.usos)


class ArmazenamentoFirestore:
    """Guarda no Firestore (Firebase). Coleções: lojas_aprendidas e uso_faturas."""

    nome = "Firebase"

    def __init__(self, credenciais):
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(dict(credenciais)))
        self.banco = firestore.client()

    def salvar_voto(self, chave, nome, sessao, categoria, origem):
        # merge=True junta o voto novo aos que já existem no documento da loja
        self.banco.collection("lojas_aprendidas").document(chave).set(
            {"nome": nome, "votos": {sessao: {"categoria": categoria, "origem": origem}}, "atualizado_em": _agora()},
            merge=True,
        )

    def ler_lojas(self):
        return {documento.id: documento.to_dict() for documento in self.banco.collection("lojas_aprendidas").stream()}

    def salvar_uso(self, registro):
        self.banco.collection("uso_faturas").add(dict(registro))

    def ler_usos(self):
        return [documento.to_dict() for documento in self.banco.collection("uso_faturas").stream()]


def criar_armazenamento(credenciais=None):
    """Firestore quando há credenciais; senão, memória local (o app funciona do mesmo jeito)."""
    if credenciais:
        return ArmazenamentoFirestore(credenciais)
    return ArmazenamentoMemoria()


def registrar_confirmacao(armazenamento, contraparte, categoria, sessao, origem, descricao="", tipo_documento=""):
    """Guarda a confirmação do usuário, se for sobre uma loja. Devolve True se guardou.

    descricao: o texto completo da transação (ex.: "PIX ENVIADO CARLOS LOPES"), para saber se foi PIX.
    """
    if origem not in ORIGENS:
        raise ValueError(f"Origem desconhecida: {origem}")
    if not pode_aprender(contraparte, categoria, descricao, tipo_documento):
        return False
    nome = normalizar_texto(contraparte)
    armazenamento.salvar_voto(chave_de_loja(nome), nome, sessao, categoria, origem)
    return True


def _apuracao(loja, origens):
    """Contagem de votos por categoria, considerando só as origens pedidas."""
    return Counter(
        CATEGORIAS_ANTIGAS.get(voto["categoria"], voto["categoria"])  # voto antigo em categoria que mudou de nome
        for voto in loja.get("votos", {}).values() if voto.get("origem") in origens
    )


def conhecimento_coletivo(armazenamento, minimo=MINIMO_DE_CONFIRMACOES, origens=ORIGENS):
    """Lojas já aprendidas: {chave: (categoria, votos da categoria, nome)}.

    Vale a categoria mais votada, desde que tenha votos de pelo menos `minimo` sessões.
    """
    conhecimento = {}
    for chave, loja in armazenamento.ler_lojas().items():
        apuracao = _apuracao(loja, origens)
        if not apuracao:
            continue
        categoria, votos = apuracao.most_common(1)[0]
        if votos >= minimo:
            conhecimento[chave] = (categoria, votos, loja.get("nome", chave))
    return conhecimento


def exemplos_de_treino(conhecimento):
    """Pares (texto, categoria) para re-treinar o modelo com o que foi aprendido."""
    return tuple(sorted((nome, categoria) for categoria, _, nome in conhecimento.values()))


def registrar_uso_fatura(armazenamento, compras, perguntas, resolvidas_pelo_coletivo, compras_lojas=None, perguntas_lojas=None):
    """Guarda só números sobre um documento analisado (nada do conteúdo dele).

    compras_lojas / perguntas_lojas: as mesmas contagens sem os PIX para pessoas. Esses PIX sempre viram
    pergunta (só a pessoa sabe a finalidade) e nunca são aprendidos, então escondem o aprendizado das lojas.
    """
    uso = {
        "data_hora": _agora(),
        "compras": int(compras),
        "perguntas": int(perguntas),
        "resolvidas_pelo_coletivo": int(resolvidas_pelo_coletivo),
    }
    if compras_lojas is not None:
        uso["compras_lojas"] = int(compras_lojas)
        uso["perguntas_lojas"] = int(perguntas_lojas)
    armazenamento.salvar_uso(uso)


def contagem_do_documento(saidas):
    """Números para registrar_uso_fatura a partir das saídas classificadas de um documento."""
    if "eh_pessoa" in saidas:
        pix_pessoa = list((saidas["operacao"] == "pix_enviado") & saidas["eh_pessoa"].astype(bool))
    else:
        pix_pessoa = [eh_pix_para_pessoa(d, c) for d, c in zip(saidas["descricao"], saidas["contraparte"])]
    lojas = saidas[[not eh for eh in pix_pessoa]]
    return {
        "compras": len(saidas),
        "perguntas": int(saidas["perguntar_usuario"].sum()),
        "resolvidas_pelo_coletivo": int((saidas["origem"] == "coletivo").sum()),
        "compras_lojas": len(lojas),
        "perguntas_lojas": int(lojas["perguntar_usuario"].sum()),
    }


def resumo(armazenamento, minimo=MINIMO_DE_CONFIRMACOES):
    """Números para a aba Aprendizado."""
    lojas = armazenamento.ler_lojas()
    votos = [voto for loja in lojas.values() for voto in loja.get("votos", {}).values()]
    aprendidas = conhecimento_coletivo(armazenamento, minimo)
    por_origem = {origem: len(conhecimento_coletivo(armazenamento, minimo, (origem,))) for origem in ORIGENS}
    return {
        "lojas_com_votos": len(lojas),
        "lojas_aprendidas": len(aprendidas),
        "aprendidas_por_origem": por_origem,
        "confirmacoes": len(votos),
        "sessoes": len({sessao for loja in lojas.values() for sessao in loja.get("votos", {})}),
        "usos": sorted(armazenamento.ler_usos(), key=lambda uso: uso.get("data_hora", "")),
        "ultimas": sorted(
            ((loja.get("atualizado_em", ""), chave) for chave, loja in lojas.items() if chave in aprendidas), reverse=True
        ),
        "conhecimento": aprendidas,
    }
