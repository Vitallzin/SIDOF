"""Pessoa ou loja? A decisão que separa um PIX para alguém (ambíguo, sempre pergunta) de um PIX para uma loja.

Num banco de verdade, o CPF ou CNPJ de quem recebeu viria em cada transação (Open Finance). Nos arquivos
do protótipo ele às vezes vem na descrição; quando não vem, o sistema usa pistas, da mais forte para a mais fraca:
1. CNPJ = loja; CPF = pessoa (lido da descrição e depois apagado: o número nunca é guardado nem mostrado)
2. A mesma loja já apareceu numa compra de cartão ou débito do usuário (cartão é sempre loja)
3. A forma do nome: 2 ou 3 palavras só com letras, sem LTDA/ME/S.A. (o que está entre parênteses não conta)
4. O primeiro nome: "ACAI DA PRAIA" não começa com nome de gente; "MARIA DA SILVA" começa
"""

import re

from financas.normalizacao import chave_de_loja

# Indícios de que a contraparte é uma empresa e não uma pessoa
MARCAS_DE_EMPRESA = ("LTDA", "ME", "SA", "EIRELI", "CIA", "SERVICOS")

# Primeiros nomes mais comuns no Brasil (sem acento, como aparecem no extrato). Lista ampla de propósito:
# na dúvida, o nome é tratado como de pessoa, que é o lado seguro (vira pergunta e não vai para o Firebase).
NOMES_COMUNS = set("""
MARIA JOSE ANA JOAO ANTONIO FRANCISCO CARLOS PAULO PEDRO LUCAS LUIZ LUIS MARCOS GABRIEL RAFAEL DANIEL MARCELO BRUNO
EDUARDO FELIPE RAIMUNDO RODRIGO MANOEL MANUEL MATEUS MATHEUS ANDRE FERNANDO FABIO LEONARDO GUSTAVO GUILHERME LEANDRO
TIAGO THIAGO ANDERSON RICARDO JORGE ALEXANDRE ROBERTO EDSON DIEGO VITOR VICTOR SERGIO CLAUDIO CESAR MARIO SEBASTIAO
GERALDO ADRIANO MARCIO JULIO RENATO JOAQUIM DAVI DAVID ARTUR ARTHUR ENZO HEITOR BERNARDO SAMUEL MIGUEL NICOLAS
VINICIUS IGOR CAIO OTAVIO HENRIQUE RUAN WESLEY WELLINGTON WILLIAM ALEX JEFFERSON EVERTON EMERSON ROGERIO RONALDO
RAFAELA FRANCISCA ANTONIA ADRIANA JULIANA MARCIA FERNANDA PATRICIA ALINE SANDRA CAMILA AMANDA BRUNA JESSICA LETICIA
JULIA LUCIANA VANESSA MARIANA GABRIELA VERA VITORIA LARISSA CLAUDIA BEATRIZ LUANA RITA SONIA RENATA ELIANE JOSEFA
SIMONE NATALIA CRISTIANE CARLA DEBORA ROSANGELA JAQUELINE ROSA DANIELA ALINE TATIANE TATIANA LUCIA REGINA CAROLINA
ISABELA ISABEL LARA LAURA SOFIA ALICE HELENA VALENTINA MANUELA GIOVANNA YASMIN CLARA LIVIA LORENA CECILIA ELISA
MICHELE MICHELLE KELLY PRISCILA PRISCILLA THAIS TAIS RAQUEL ROSANA ELAINE ANDREA ANDREIA DENISE SILVIA LUIZA LUISA
TERESA TEREZA IVONE APARECIDA CONCEICAO FATIMA GRACA MARLENE MIRIAM NEIDE ODETE SUELI SOLANGE VALERIA VIVIANE
ALESSANDRA BIANCA CAROLINE DAYANE DAIANE EDUARDA EMANUELLE GISELE GRAZIELE INGRID IRIS JANAINA KARINA KATIA LILIAN
MARCELA MELISSA MONICA NADIA PAOLA PAULA REBECA SABRINA SAMANTHA STEFANY STEPHANIE TAMIRES TALITA VIVIAN
HUGO OSVALDO OSWALDO WAGNER WALTER WILSON NILTON NELSON MILTON GILBERTO GILSON GERSON ELIAS ISAAC ISRAEL JONAS
JONATHAN JOSUE MOISES NATAN RENAN ROBSON SAULO SILVIO TOMAS VALTER ALAN ALLAN ALISSON ANTHONY BENJAMIN CAUA
DOUGLAS ERICK ERIC FABIANO FABRICIO FLAVIO GIOVANI HELIO HUMBERTO IVAN JOEL KAIQUE KAUA LAURO LORENZO LUAN
MAURICIO MAURO MURILO NOAH OTAVIANO PABLO RAUL REINALDO RUBENS SANDRO THEO VALDIR VANDERLEI YURI ZECA
""".split())

_CNPJ = re.compile(r"(?:\bCNPJ:?\s*)?\b\d{2}\.?\d{3}\.?\d{3}/\d{4}-?\d{2}\b")
_CPF = re.compile(r"(?:\bCPF:?\s*)?[\d*]{3}\.[\d*]{3}\.[\d*]{3}-[\d*]{2}|\bCPF:?\s*\d{11}\b")
_PARENTESES = re.compile(r"\s*\([^)]*\)")


def extrair_documento(descricao):
    """'PIX ENVIADO PICHAU - CNPJ 09.376.495/0001-22' -> ('PIX ENVIADO PICHAU', 'cnpj').

    O número é apagado da descrição: serve só para decidir pessoa ou loja e nunca é guardado nem mostrado.
    """
    for padrao, tipo in ((_CNPJ, "cnpj"), (_CPF, "cpf")):
        achado = padrao.search(descricao)
        if achado:
            limpa = (descricao[: achado.start()] + " " + descricao[achado.end():]).strip()
            limpa = re.sub(r"\s*-\s*$", "", re.sub(r"\s+", " ", limpa)).strip(" -")
            return limpa, tipo
    return descricao, ""


def sem_detalhes(contraparte):
    """'JOSE RICARDO (SALARIO GARCOM)' -> 'JOSE RICARDO'. O que está entre parênteses é anotação, não nome."""
    return _PARENTESES.sub("", contraparte).strip()


def parece_pessoa(contraparte):
    """Forma de nome de pessoa: duas ou três palavras só com letras e sem indício de empresa, ex.: 'MARIA SOUZA'.

    Nomes de pessoa não têm '*' (prefixo de maquininha) nem números (código do terminal).
    """
    palavras = sem_detalhes(contraparte).split()
    return (
        2 <= len(palavras) <= 3
        and all(palavra.isalpha() for palavra in palavras)
        and not any(palavra in MARCAS_DE_EMPRESA for palavra in palavras)
    )


def comeca_com_nome_de_gente(contraparte):
    palavras = sem_detalhes(contraparte).split()
    return bool(palavras) and palavras[0] in NOMES_COMUNS


def eh_pessoa(contraparte, tipo_documento="", lojas_conhecidas=frozenset()):
    """Decide se a contraparte de um PIX é uma pessoa, usando as pistas da mais forte para a mais fraca."""
    if tipo_documento == "cnpj":
        return False
    if tipo_documento == "cpf":
        return True
    if chave_de_loja(sem_detalhes(contraparte)) in lojas_conhecidas:
        return False
    return parece_pessoa(contraparte) and comeca_com_nome_de_gente(contraparte)


def marcar_pessoas(tabela):
    """Coluna eh_pessoa: True nos PIX (enviados ou recebidos) para pessoas. Recebe o extrato normalizado."""
    eh_pix = tabela["operacao"].isin(["pix_enviado", "pix_recebido"])
    # Lojas em que o usuário comprou no cartão ou no débito (não PIX): o mesmo nome num PIX também é loja
    compras = tabela[~eh_pix & (tabela["valor"] < 0)]
    lojas = {
        usuario: frozenset(chave_de_loja(sem_detalhes(nome)) for nome in grupo["contraparte"]) - {""}
        for usuario, grupo in compras.groupby("id_usuario")
    }
    documentos = tabela["tipo_documento"] if "tipo_documento" in tabela else [""] * len(tabela)
    return [
        bool(pix) and eh_pessoa(contraparte, documento, lojas.get(usuario, frozenset()))
        for pix, contraparte, documento, usuario in zip(eh_pix, tabela["contraparte"], documentos, tabela["id_usuario"])
    ]
