"""Ponto de entrada do projeto: `python -m financas`."""

import pandas as pd

from financas.avaliacao import (
    avaliar_anomalias,
    avaliar_faturas,
    avaliar_regras,
    instancias_plantadas,
    avaliar_renda,
    com_respostas_do_usuario,
    comparar_diagnosticos,
    contar_parcelamentos,
    carregar_usuarios_verdade,
    carregar_verdade,
    relatorio_anomalias,
    relatorio_diagnostico,
    relatorio_faturas,
    relatorio_parcelas,
    relatorio_regras,
    relatorio_sistema,
    relatorio_renda,
)
from financas.avaliacao_final import indicadores_por_usuario, relatorio_final
from financas.anomalias import detectar_estatistico, detectar_isolation_forest
from financas.diagnostico import diagnosticar
from financas.faturas_pdf import compras_no_cartao, gerar_fatura_pdf, ler_faturas_do_conjunto
from financas.experimento import executar_experimento, relatorio_modelo, relatorio_teste_duro
from financas.metas import aportes_por_mes, relatorio_metas
from financas.gerador import PASTA_PADRAO, gerar_dados, resumo, salvar_dados
from financas.normalizacao import carregar_dados, normalizar
from financas.parcelas import comprometimento_da_renda, compromissos_futuros, identificar_parcelamentos
from financas.regras import classificar_por_regras
from financas.sistema import Sistema, treinar_modelo_da_base
from financas.renda import classificar_entradas, perfil_de_renda


def executar():
    """Roda as fases já implementadas, na ordem."""
    # Fase 1: dados sintéticos
    dados = gerar_dados()
    pasta = salvar_dados(dados)
    print(f"Dados sintéticos gerados em: {pasta}")
    print(resumo(dados))
    print()

    # Fase 2: normalização e regras (o sistema só lê o extrato e os nomes)
    extrato, usuarios = carregar_dados(pasta)
    classificado = classificar_por_regras(normalizar(extrato), usuarios)
    classificado.to_csv(PASTA_PADRAO / "classificacao_regras.csv", index=False)

    # Avaliação: só aqui a verdade é lida
    verdade = carregar_verdade(pasta)
    texto = relatorio_regras(avaliar_regras(classificado, verdade))
    (PASTA_PADRAO / "relatorio_regras.txt").write_text(texto, encoding="utf-8")
    print(texto)
    print()

    # Fase 3: modelo, comparado com as regras (divisão por usuário)
    resultado = executar_experimento(classificado, verdade, carregar_usuarios_verdade(pasta))
    resultado["hibrido"].to_csv(PASTA_PADRAO / "classificacao_hibrida_teste.csv", index=False)
    texto = relatorio_modelo(resultado)
    (PASTA_PADRAO / "relatorio_modelo.txt").write_text(texto, encoding="utf-8")
    print(texto)
    print()

    # Fase 3, teste duro: também separa lojas, para medir o modelo em lojas nunca vistas
    resultado_duro = executar_experimento(classificado, verdade, carregar_usuarios_verdade(pasta), separar_lojas=True)
    resultado_duro["hibrido"].to_csv(PASTA_PADRAO / "classificacao_teste_duro.csv", index=False)
    texto = relatorio_teste_duro(resultado_duro)
    (PASTA_PADRAO / "relatorio_teste_duro.txt").write_text(texto, encoding="utf-8")
    print(texto)
    print()

    # Fase 4: origem das entradas e perfil de renda (o sistema só usa o extrato e os nomes)
    entradas = classificar_entradas(classificado, usuarios)
    perfis = perfil_de_renda(entradas, sorted(classificado["mes"].unique()))
    entradas.to_csv(PASTA_PADRAO / "entradas_classificadas.csv", index=False)
    perfis.to_csv(PASTA_PADRAO / "perfis_de_renda.csv", index=False)
    texto = relatorio_renda(avaliar_renda(entradas, perfis, verdade, carregar_usuarios_verdade(pasta)))
    (PASTA_PADRAO / "relatorio_renda.txt").write_text(texto, encoding="utf-8")
    print(texto)
    print()

    # Fase 5: parcelas e compromissos futuros
    mes_atual = classificado["mes"].max()
    parcelamentos = identificar_parcelamentos(classificado)
    compromissos = compromissos_futuros(parcelamentos, usuarios["id_usuario"], mes_atual)
    comprometimento = comprometimento_da_renda(parcelamentos, compromissos, perfis)
    parcelamentos.to_csv(PASTA_PADRAO / "parcelamentos.csv", index=False)
    compromissos.to_csv(PASTA_PADRAO / "compromissos_futuros.csv")
    comprometimento.to_csv(PASTA_PADRAO / "comprometimento_da_renda.csv", index=False)
    texto = relatorio_parcelas(parcelamentos, comprometimento, contar_parcelamentos(parcelamentos, extrato, verdade))
    (PASTA_PADRAO / "relatorio_parcelas.txt").write_text(texto, encoding="utf-8")
    print(texto)
    print()

    # Fase 6: indicadores e diagnóstico (gastos categorizados por regras + modelo + respostas do usuário)
    confirmado = com_respostas_do_usuario(resultado["hibrido"])
    indicadores, textos = diagnosticar(classificado, usuarios, saidas=confirmado)
    indicadores.to_csv(PASTA_PADRAO / "indicadores.csv", index=False)
    texto = relatorio_diagnostico(textos, comparar_diagnosticos(classificado, usuarios, resultado["hibrido"]))
    (PASTA_PADRAO / "relatorio_diagnostico.txt").write_text(texto, encoding="utf-8")
    print(texto)
    print()

    # Fase 7: metas (meta exemplo da proposta, acompanhada com o que cada um guardou)
    texto = relatorio_metas(indicadores, aportes_por_mes(classificado, sorted(classificado["mes"].unique())))
    (PASTA_PADRAO / "relatorio_metas.txt").write_text(texto, encoding="utf-8")
    print(texto)
    print()

    # Fase 8: anomalias (os métodos só veem as saídas, sem os rótulos das anomalias)
    colunas = ["id_transacao", "id_usuario", "data", "mes", "descricao", "contraparte", "valor", "parcela", "categoria_final"]
    alertas = {
        "estatístico": detectar_estatistico(confirmado[colunas]),
        "IsolationForest": detectar_isolation_forest(confirmado[colunas]),
    }
    pd.concat(alertas.values()).to_csv(PASTA_PADRAO / "alertas.csv", index=False)
    instancias = instancias_plantadas(extrato, verdade)
    resultados = {nome: avaliar_anomalias(tabela, instancias) for nome, tabela in alertas.items()}
    texto = relatorio_anomalias(resultados, instancias)
    (PASTA_PADRAO / "relatorio_anomalias.txt").write_text(texto, encoding="utf-8")
    print(texto)
    print()

    # Sistema em uso: modelo treinado numa base separada; nada lê a verdade dos atendidos
    atendido = Sistema(extrato, usuarios, treinar_modelo_da_base())
    texto = relatorio_sistema(atendido.saidas(), verdade)
    (PASTA_PADRAO / "relatorio_sistema.txt").write_text(texto, encoding="utf-8")
    print(texto)
    print()

    # Faturas em PDF: gera a fatura de cada usuário em cada mês, lê de volta e classifica
    exemplo = gerar_fatura_pdf(compras_no_cartao(extrato, "U08", "2026-03"), "JULIANA (FICTICIA)", "2026-03")
    (PASTA_PADRAO / "fatura_exemplo.pdf").write_bytes(exemplo)
    modelos = {
        "modelo treinado com faturas": treinar_modelo_da_base(),
        "modelo treinado sem faturas": treinar_modelo_da_base(incluir_faturas=False),
    }
    texto = relatorio_faturas(avaliar_faturas(ler_faturas_do_conjunto(extrato, usuarios), extrato, verdade, modelos))
    (PASTA_PADRAO / "relatorio_faturas.txt").write_text(texto, encoding="utf-8")
    print(texto)
    print()

    # Fase 10: indicadores da seção 19 da proposta
    por_usuario = indicadores_por_usuario(
        indicadores, compromissos, aportes_por_mes(classificado, sorted(classificado["mes"].unique())),
        carregar_usuarios_verdade(pasta),
    )
    por_usuario.to_csv(PASTA_PADRAO / "indicadores_finais.csv", index=False)
    texto = relatorio_final(atendido.saidas(), verdade, por_usuario, resultados["estatístico"])
    (PASTA_PADRAO / "relatorio_final.txt").write_text(texto, encoding="utf-8")
    print(texto)


if __name__ == "__main__":
    executar()
