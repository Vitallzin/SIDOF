"""Interface do protótipo (Fase 9). Rodar com: .venv\\Scripts\\streamlit run app.py

Mostra, para cada usuário fictício, o diagnóstico, as perguntas do sistema, as notificações
do mês, as parcelas e uma meta. Um seletor simula os meses chegando um a um.
Usa só o sistema em uso (financas/sistema.py): nada aqui lê a verdade dos usuários.
"""

import pandas as pd
import streamlit as st

from financas.categorias import CATEGORIAS
from financas.diagnostico import BLOCOS
from financas.formatacao import mes_por_extenso, reais
from financas.gerador import gerar_dados
from financas.metas import Meta, acompanhar, aportes_por_mes, plano_da_meta, previsao
from financas.monitoramento import extrato_ate, notificacoes_do_mes
from financas.parcelas import comprometimento_da_renda, compromissos_futuros, identificar_parcelamentos
from financas.renda import classificar_entradas, perfil_de_renda
from financas.sistema import Sistema, treinar_modelo_da_base

st.set_page_config(page_title="Diagnóstico financeiro (protótipo)", page_icon="💰", layout="wide")


def md(texto):
    """Protege o "$": no Streamlit, texto entre dois cifrões vira fórmula matemática."""
    return texto.replace("$", r"\$")


def reais_curto(valor):
    """R$ sem centavos, para caber nos cartões: 'R$ 6.388'."""
    return "R$ " + f"{valor:,.0f}".replace(",", ".")


@st.cache_resource(show_spinner="Gerando dados fictícios e treinando o modelo...")
def carregar():
    """Dados fictícios dos usuários atendidos e modelo treinado na base separada."""
    return gerar_dados(), treinar_modelo_da_base()


dados, modelo = carregar()
extrato, usuarios = dados["extrato"], dados["usuarios"]
meses = sorted(extrato["data"].str[:7].unique())


@st.cache_data(show_spinner="Calculando...")
def calcular(mes, respostas):
    """Tudo o que a tela mostra, olhando só o extrato até o mês escolhido."""
    sistema = Sistema(extrato_ate(extrato, mes), usuarios, modelo)
    sistema.memoria = dict(respostas)
    meses_vistos = sorted(sistema.classificado["mes"].unique())
    indicadores, textos = sistema.diagnosticar()
    entradas = classificar_entradas(sistema.classificado, usuarios)
    perfis = perfil_de_renda(entradas, meses_vistos)
    parcelamentos = identificar_parcelamentos(sistema.classificado)
    compromissos = compromissos_futuros(parcelamentos, sorted(usuarios["id_usuario"]), mes)
    return {
        "indicadores": indicadores,
        "textos": textos,
        "perguntas": sistema.perguntas(),
        "parcelamentos": parcelamentos,
        "comprometimento": comprometimento_da_renda(parcelamentos, compromissos, perfis),
        "aportes": aportes_por_mes(sistema.classificado, meses_vistos),
        "notificacoes": notificacoes_do_mes(extrato, usuarios, modelo, mes, dict(respostas)),
    }


if "respostas" not in st.session_state:
    st.session_state.respostas = {}

# ---------- Barra lateral ----------
nomes = usuarios.set_index("id_usuario")["nome"]
with st.sidebar:
    st.title("💰 Diagnóstico financeiro")
    usuario = st.selectbox("Usuário", list(nomes.index), format_func=lambda u: f"{u} · {nomes[u].title()}")
    mes = st.select_slider(
        "Mês atual (simulação)", options=meses[2:], value=meses[-1], format_func=mes_por_extenso,
        help="Simula os meses chegando: o sistema só enxerga o extrato até este mês.",
    )
    st.caption("Protótipo de estudo. **Todos os dados são fictícios.** O sistema não recomenda investimentos.")

resultado = calcular(mes, tuple(sorted(st.session_state.respostas.items())))
indicador = resultado["indicadores"].set_index("id_usuario").loc[usuario]

st.header(f"{nomes[usuario].title()} · até {mes_por_extenso(mes)}")
coluna1, coluna2, coluna3, coluna4 = st.columns(4)
coluna1.metric("Renda efetiva média", reais_curto(indicador["renda_media"]))
coluna2.metric("Gastos médios", reais_curto(indicador["gastos_total"]))
coluna3.metric("Sobra média", reais_curto(indicador["sobra_media"]), f"{indicador['taxa_de_sobra']:.0%} da renda")
coluna4.metric(
    "Parcelas no próximo mês", reais_curto(indicador["comprometido_proximo_mes"]),
    f"{indicador['percentual_comprometido']:.0%} da renda", delta_color="off",
)

aba_diag, aba_notif, aba_perg, aba_parc, aba_meta = st.tabs(
    ["Diagnóstico", "Notificações do mês", "Perguntas", "Parcelas", "Metas"]
)

# ---------- Diagnóstico ----------
with aba_diag:
    blocos = pd.DataFrame(
        {"Média por mês (R$)": [indicador[nome] for nome, _ in BLOCOS]},
        # Numerados para o gráfico seguir a ordem do diagnóstico (ele ordena pelo nome)
        index=[f"{numero}. {rotulo.split(' (')[0]}" for numero, (_, rotulo) in enumerate(BLOCOS, start=1)],
    )
    st.subheader("Para onde foi o dinheiro")
    st.bar_chart(blocos, horizontal=True)
    st.text(resultado["textos"][usuario])

# ---------- Notificações ----------
with aba_notif:
    st.subheader(f"O que mudou em {mes_por_extenso(mes)}")
    notificacoes = resultado["notificacoes"]
    do_usuario = notificacoes[notificacoes["id_usuario"] == usuario]
    if do_usuario.empty:
        st.success("Nenhuma notificação neste mês.")
    for linha in do_usuario.itertuples():
        st.warning(md(f"**{linha.tipo}** — {linha.mensagem}"))
    st.caption("Mude o mês na barra lateral para simular a chegada de um novo mês.")

# ---------- Perguntas ----------
with aba_perg:
    perguntas = resultado["perguntas"]
    perguntas = perguntas[perguntas["id_usuario"] == usuario]
    st.subheader(f"O sistema precisa da sua ajuda em {len(perguntas)} transações")
    st.caption(
        "Quando a confiança é baixa, o sistema pergunta em vez de adivinhar. "
        "Sua resposta vale também para pagamentos parecidos."
    )
    opcoes = sorted(CATEGORIAS)
    for linha in perguntas.head(10).itertuples():
        with st.container(border=True):
            texto, escolha, botao = st.columns([3, 2, 1])
            texto.markdown(md(f"**{linha.descricao}** · {reais(-linha.valor)} · {linha.data:%d/%m}"))
            texto.caption(md(linha.explicacao_final))
            sugestao = linha.sugestao_modelo if linha.sugestao_modelo in opcoes else "nao_identificado"
            categoria = escolha.selectbox(
                "Categoria", opcoes, index=opcoes.index(sugestao), key=f"cat_{linha.id_transacao}",
                format_func=lambda c: c.replace("_", " "), label_visibility="collapsed",
            )
            if botao.button("Confirmar", key=f"ok_{linha.id_transacao}"):
                st.session_state.respostas[(usuario, linha.contraparte)] = categoria
                st.rerun()
    if len(perguntas) > 10:
        st.caption(f"Mostrando 10 de {len(perguntas)}.")

# ---------- Parcelas ----------
with aba_parc:
    comprometimento = resultado["comprometimento"].set_index("id_usuario").loc[usuario]
    st.subheader("Compromissos futuros")
    st.info(md(comprometimento["explicacao"]))
    parcelas = resultado["parcelamentos"]
    parcelas = parcelas[(parcelas["id_usuario"] == usuario)].sort_values("parcelas_restantes", ascending=False)
    for explicacao in parcelas["explicacao"]:
        st.markdown(md(f"- {explicacao}"))

# ---------- Metas ----------
with aba_meta:
    st.subheader("Simular uma meta")
    coluna_nome, coluna_valor, coluna_prazo = st.columns(3)
    nome_meta = coluna_nome.text_input("Objetivo", "Computador novo")
    valor_meta = coluna_valor.number_input("Valor (R$)", min_value=100.0, value=4000.0, step=100.0)
    prazo = coluna_prazo.number_input("Prazo (meses)", min_value=1, value=10, step=1)
    meta = Meta(nome_meta, valor_meta, int(prazo), meses[0])
    st.write(md(plano_da_meta(meta, indicador["sobra_media"], indicador["alto_comprometimento"], indicador["tipo_renda"])))
    acompanhamento = acompanhar(meta, list(resultado["aportes"].loc[usuario]))
    st.write(md(previsao(meta, acompanhamento)["explicacao"]))
    grafico = acompanhamento.set_index("mes")[["acumulado", "esperado"]].rename(
        columns={"acumulado": "Guardado (poupança)", "esperado": "Necessário para o prazo"}
    )
    st.line_chart(grafico)
    st.caption("O acompanhamento usa o que foi transferido para a poupança desde janeiro.")
