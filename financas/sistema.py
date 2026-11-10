"""O sistema em uso, sem a verdade.

Diferente dos experimentos, aqui nada lê a verdade dos usuários atendidos:
1. O modelo é treinado numa BASE separada de usuários fictícios (outra semente), que faz o
   papel de clientes antigos que já confirmaram suas categorias.
2. As saídas dos usuários atendidos são classificadas por regras + memória + modelo.
   O que tem confiança baixa fica "a confirmar" até o usuário responder.
3. Cada resposta do usuário entra na memória dele e passa a valer para pagamentos parecidos.
"""

from functools import lru_cache

import pandas as pd

from financas import SEMENTE
from financas.anomalias import detectar_estatistico
from financas.categorias import CATEGORIAS
from financas.diagnostico import diagnosticar
from financas.faturas_pdf import fatura_para_extrato, ler_faturas_do_conjunto
from financas.gerador import gerar_dados
from financas.modelo import classificar_hibrido, treinar
from financas.normalizacao import normalizar, normalizar_texto
from financas.regras import classificar_por_regras

SEMENTE_BASE = SEMENTE + 1000  # base de "clientes antigos", diferente dos usuários atendidos
C_DO_MODELO = 10  # valor escolhido pela validação cruzada em todas as rodadas da Fase 3
COLUNAS_ANOMALIAS = ["id_transacao", "id_usuario", "data", "mes", "descricao", "contraparte", "valor", "parcela", "categoria_final"]


@lru_cache(maxsize=4)
def treinar_modelo_da_base(semente=SEMENTE_BASE, incluir_faturas=True):
    """Treina o modelo com as saídas confirmadas de uma base separada de usuários.

    Com incluir_faturas, as compras no cartão também entram como aparecem numa fatura em PDF
    (nome cortado, sem prefixo do banco), para o modelo reconhecer faturas importadas.
    O resultado fica guardado: treinar de novo com os mesmos parâmetros devolve o mesmo modelo.
    """
    base = gerar_dados(semente)
    classificado = classificar_por_regras(normalizar(base["extrato"]), base["usuarios"])
    saidas = classificado[classificado["direcao"] == "saida"].merge(
        base["verdade"][["id_transacao", "categoria"]], on="id_transacao"
    )
    textos, categorias = list(saidas["descricao"]), list(saidas["categoria"])
    if incluir_faturas:
        lidas = ler_faturas_do_conjunto(base["extrato"], base["usuarios"]).dropna(subset=["id_origem"])
        rotulos = base["verdade"].set_index("id_transacao")["categoria"]
        textos += [normalizar_texto(texto) for texto in lidas["descricao"]]
        categorias += list(rotulos[lidas["id_origem"]])
    return treinar(textos, categorias, C_DO_MODELO)


class Sistema:
    """Atende um grupo de usuários a partir do extrato e dos nomes (nunca da verdade)."""

    def __init__(self, extrato, usuarios, modelo):
        self.usuarios = usuarios
        self.modelo = modelo
        self.classificado = classificar_por_regras(normalizar(extrato), usuarios)
        self.memoria = {}

    def saidas(self):
        """Saídas classificadas com o que o sistema sabe agora (inclui as respostas já dadas)."""
        saidas = self.classificado[self.classificado["direcao"] == "saida"]
        return classificar_hibrido(saidas, self.modelo, self.memoria)

    def perguntas(self, id_usuario=None):
        """Transações que o sistema precisa que o usuário confirme."""
        saidas = self.saidas()
        perguntas = saidas[saidas["perguntar_usuario"]]
        if id_usuario is not None:
            perguntas = perguntas[perguntas["id_usuario"] == id_usuario]
        colunas = ["id_transacao", "id_usuario", "data", "descricao", "contraparte", "valor", "sugestao_modelo", "explicacao_final"]
        return perguntas[colunas]

    def responder(self, id_transacao, categoria):
        """Guarda a resposta do usuário; ela passa a valer para pagamentos parecidos."""
        if categoria not in CATEGORIAS:
            raise ValueError(f"Categoria desconhecida: {categoria}")
        linha = self.classificado.loc[self.classificado["id_transacao"] == id_transacao].iloc[0]
        self.memoria[(linha["id_usuario"], linha["contraparte"])] = categoria

    def diagnosticar(self):
        """Indicadores e textos da Fase 6 com as categorias atuais ('a confirmar' onde faltar resposta)."""
        return diagnosticar(self.classificado, self.usuarios, saidas=self.saidas())

    def alertas(self):
        """Alertas de anomalia (método estatístico da Fase 8)."""
        return detectar_estatistico(self.saidas()[COLUNAS_ANOMALIAS])


def classificar_fatura(compras, modelo, nome_titular="", memoria=None):
    """Classifica as compras lidas de uma fatura em PDF (de qualquer origem), sem guardar nada."""
    extrato = fatura_para_extrato(compras)
    usuarios = pd.DataFrame({"id_usuario": ["PDF"], "nome": [nome_titular or "TITULAR DA FATURA"]})
    classificado = classificar_por_regras(normalizar(extrato), usuarios)
    return classificar_hibrido(classificado, modelo, memoria)
