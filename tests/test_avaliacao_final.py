"""Testes da avaliação final (Fase 10)."""

import pandas as pd

from financas.avaliacao_final import indicadores_por_usuario, relatorio_final, resumo_por_perfil


def _entradas():
    indicadores = pd.DataFrame({
        "id_usuario": ["U01", "U02"],
        "taxa_de_sobra": [0.20, -0.05],
        "poupanca_por_mes": [500.0, 0.0],
        "percentual_comprometido": [0.05, 0.35],
        "renda_referencia": [5000.0, 2000.0],
        "variacao_gastos": [0.10, 0.30],
    })
    meses = ["2026-07", "2026-08", "2026-09", "2026-10", "2026-11", "2026-12"]
    compromissos = pd.DataFrame([[250.0] * 6, [700.0] * 3 + [100.0] * 3], index=["U01", "U02"], columns=meses)
    aportes = pd.DataFrame([[400.0] * 6, [0.0] * 6], index=["U01", "U02"], columns=[f"2026-0{m}" for m in range(1, 7)])
    usuarios_verdade = pd.DataFrame({"id_usuario": ["U01", "U02"], "perfil": ["fixa", "dividas"]})
    return indicadores, compromissos, aportes, usuarios_verdade


def test_indicadores_por_usuario():
    tabela = indicadores_por_usuario(*_entradas()).set_index("id_usuario")
    assert tabela.loc["U01", "meta_situacao"] == "no ritmo"  # R$ 400 por mês é o ritmo da meta exemplo
    assert tabela.loc["U02", "meta_situacao"] == "atrasada"
    assert tabela.loc["U02", "comprometido_em_6_meses"] == 100.0 / 2000.0
    assert tabela.loc["U01", "meta_percentual"] == 2400.0 / 4000.0


def test_resumo_por_perfil():
    resumo = resumo_por_perfil(indicadores_por_usuario(*_entradas()))
    assert set(resumo.index) == {"fixa", "dividas"}


def test_relatorio_final_e_honesto_sobre_o_que_nao_mede():
    por_usuario = indicadores_por_usuario(*_entradas())
    saidas = pd.DataFrame({"id_transacao": ["A"], "categoria_final": ["energia"], "perguntar_usuario": [False]})
    verdade = pd.DataFrame({"id_transacao": ["A"], "categoria": ["energia"]})
    anomalias = {
        "por_tipo": pd.DataFrame({"previsto": ["sim", "não"], "plantadas": [4, 2], "detectadas": [4, 1]}),
        "precisao_geral": 0.8,
    }
    texto = relatorio_final(saidas, verdade, por_usuario, anomalias)
    assert "100.0% de acerto" in texto
    assert "tipos previstos 4/4" in texto and "tipos não previstos 1/2" in texto
    assert "NÃO dá para medir" in texto
