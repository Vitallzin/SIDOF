"""O sistema em uso, sem a verdade.

Diferente dos experimentos, aqui nada lê a verdade dos usuários atendidos:
1. O modelo é treinado numa BASE separada de usuários fictícios (outra semente), que faz o
   papel de clientes antigos que já confirmaram suas categorias.
2. As saídas dos usuários atendidos são classificadas por regras + memória + modelo.
   O que tem confiança baixa fica "a confirmar" até o usuário responder.
3. Cada resposta do usuário entra na memória dele e passa a valer para pagamentos parecidos.
"""

import pandas as pd

from financas import SEMENTE
from financas.anomalias import detectar_estatistico
from financas.categorias import CATEGORIAS
from financas.diagnostico import diagnosticar
from financas.gerador import gerar_dados
from financas.modelo import classificar_hibrido, treinar
from financas.normalizacao import normalizar
from financas.regras import classificar_por_regras

SEMENTE_BASE = SEMENTE + 1000  # base de "clientes antigos", diferente dos usuários atendidos
C_DO_MODELO = 10  # valor escolhido pela validação cruzada em todas as rodadas da Fase 3
COLUNAS_ANOMALIAS = ["id_transacao", "id_usuario", "data", "mes", "descricao", "contraparte", "valor", "parcela", "categoria_final"]


def treinar_modelo_da_base(semente=SEMENTE_BASE):
    """Treina o modelo com as saídas confirmadas de uma base separada de usuários."""
    base = gerar_dados(semente)
    classificado = classificar_por_regras(normalizar(base["extrato"]), base["usuarios"])
    saidas = classificado[classificado["direcao"] == "saida"].merge(
        base["verdade"][["id_transacao", "categoria"]], on="id_transacao"
    )
    return treinar(saidas["descricao"], saidas["categoria"], C_DO_MODELO)


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
        return perguntas[["id_transacao", "id_usuario", "data", "descricao", "valor", "sugestao_modelo", "explicacao_final"]]

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
