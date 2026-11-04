"""Interface do protótipo (Fase 9). Rodar com: .venv\\Scripts\\streamlit run app.py

Mostra, para cada usuário fictício, o diagnóstico, as perguntas do sistema, as notificações
do mês, as parcelas e uma meta. Um seletor simula os meses chegando um a um.
Usa só o sistema em uso (financas/sistema.py): nada aqui lê a verdade dos usuários.
"""

import altair as alt
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

st.set_page_config(page_title="Diagnóstico financeiro (protótipo)", layout="wide")

# ---------- Visual ----------

# Uma cor por bloco do diagnóstico (mesma ordem de BLOCOS)
CORES_BLOCOS = {
    "essenciais": "#0F766E",
    "prioritarios": "#3B82F6",
    "discricionarios": "#F59E0B",
    "parcelas": "#8B5CF6",
    "a_confirmar": "#9CA3AF",
}
VERDE, AMARELO, VERMELHO = "#15803D", "#B45309", "#B91C1C"

# Cor da borda de cada tipo de notificação
CORES_NOTIFICACAO = {
    "Queda de renda": VERMELHO,
    "Nova parcela": "#8B5CF6",
    "Possível cobrança duplicada": AMARELO,
    "Compra alta em lugar novo": AMARELO,
    "Muitas compras em pouco tempo": AMARELO,
    "Aumento de gasto": AMARELO,
}

# Duas paletas: a interface troca entre elas pela chave "Tema escuro" na barra lateral
PALETAS = {
    "claro": {
        "fundo": "#F6F8F7", "lateral": "#E8F1EF", "cartao": "#FFFFFF", "borda": "#E5ECEA", "linha": "#EEF2F1",
        "texto": "#111827", "suave": "#6B7280", "forte": "#374151",
        "alerta_fundo": "#FEF3C7", "alerta_texto": "#92400E", "alerta_borda": "#FDE68A",
        "ok_fundo": "#DCFCE7", "ok_texto": "#166534", "ok_borda": "#BBF7D0",
        "verde": "#15803D", "amarelo": "#B45309", "vermelho": "#B91C1C",
    },
    "escuro": {
        "fundo": "#0E1514", "lateral": "#15201E", "cartao": "#1A2624", "borda": "#2A3A37", "linha": "#24332F",
        "texto": "#E5E7EB", "suave": "#9CA3AF", "forte": "#D1D5DB",
        "alerta_fundo": "#3A2E12", "alerta_texto": "#FCD34D", "alerta_borda": "#5B4718",
        "ok_fundo": "#12301F", "ok_texto": "#86EFAC", "ok_borda": "#1F4D33",
        "verde": "#4ADE80", "amarelo": "#FBBF24", "vermelho": "#F87171",
    },
}


def aplicar_tema(cores):
    """Injeta as cores da paleta como variáveis CSS e estiliza a página e os componentes."""
    variaveis = "".join(f"--{nome.replace('_', '-')}: {valor};" for nome, valor in cores.items())
    st.markdown(
        f"""
    <style>
    :root {{{variaveis}}}
    .stApp, [data-testid="stHeader"] {{background-color: var(--fundo); color: var(--texto);}}
    [data-testid="stSidebar"] {{background-color: var(--lateral);}}
    .stApp h1, .stApp h2, .stApp h3, .stApp p, .stApp li, .stApp label,
    [data-testid="stMarkdownContainer"], [data-testid="stText"] {{color: var(--texto);}}
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{color: var(--suave);}}
    [data-baseweb="select"] > div, [data-baseweb="input"] > div, .stApp input, .stApp textarea,
    [data-baseweb="popover"] ul, [data-baseweb="popover"] li, [role="listbox"], [role="option"],
    [data-testid="stSelectbox"] div:has(input), [data-testid="stNumberInput"] div:has(> input),
    [data-testid="stTextInput"] div:has(> input) {{background-color: var(--cartao) !important; color: var(--texto) !important;}}
    [data-testid="stExpander"] details, [data-testid="stVerticalBlockBorderWrapper"] {{border-color: var(--borda) !important;}}
    [data-testid="stExpander"] details {{background-color: var(--cartao);}}
    button[data-baseweb="tab"] p {{color: var(--suave);}}
    button[data-baseweb="tab"][aria-selected="true"] p {{color: #0F766E; font-weight: 600;}}
    .block-container {{padding-top: 2rem; max-width: 1200px;}}
    .cartao {{background: var(--cartao); border-radius: 14px; padding: 1rem 1.2rem;
             box-shadow: 0 1px 3px rgba(15, 23, 42, .08); border: 1px solid var(--borda); height: 100%;}}
    .cartao .rotulo {{font-size: .75rem; color: var(--suave); text-transform: uppercase; letter-spacing: .04em; min-height: 2.2em;}}
    .cartao .valor {{font-size: clamp(1.05rem, 2.1vw, 1.7rem); font-weight: 700; color: var(--texto); line-height: 1.3; white-space: nowrap;}}
    .cartao .detalhe {{font-size: .85rem; color: var(--suave);}}
    .bloco {{display: flex; align-items: center; gap: .7rem; padding: .55rem .2rem; border-bottom: 1px solid var(--linha);}}
    .bloco:last-child {{border-bottom: none;}}
    .bolinha {{width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0;}}
    .bloco .corpo {{flex: 1; min-width: 0;}}
    .bloco .topo, .bloco .base {{display: flex; justify-content: space-between; gap: .6rem;}}
    .bloco .nome {{color: var(--texto); font-weight: 500;}}
    .bloco .quanto {{font-weight: 600; color: var(--texto); white-space: nowrap;}}
    .bloco .base {{font-size: .78rem; color: var(--suave);}}
    .bloco .base span:last-child {{white-space: nowrap;}}
    .faixa {{border-radius: 14px; padding: 1rem 1.3rem; color: #FFFFFF; margin: .3rem 0 1rem 0;}}
    .faixa .grande {{font-size: 1.5rem; font-weight: 700;}}
    .etiqueta {{display: inline-block; padding: .35rem .75rem; border-radius: 999px; margin: 0 .4rem .5rem 0; font-size: .88rem;
               background: var(--alerta-fundo); color: var(--alerta-texto); border: 1px solid var(--alerta-borda);}}
    .etiqueta.ok {{background: var(--ok-fundo); color: var(--ok-texto); border-color: var(--ok-borda);}}
    .aviso {{background: var(--cartao); border-radius: 12px; padding: .8rem 1rem; margin-bottom: .6rem;
            border: 1px solid var(--borda); border-left-width: 6px;}}
    .aviso .titulo {{font-weight: 600; margin-bottom: .15rem;}}
    .secao {{font-size: 1.05rem; font-weight: 600; margin: .2rem 0 .4rem 0; color: var(--texto);}}
    </style>
    """,
        unsafe_allow_html=True,
    )


def estilo_grafico(grafico):
    """Fundo transparente e textos na cor do tema atual."""
    return grafico.configure(background="transparent").configure_view(strokeWidth=0).configure_axis(
        labelColor=CORES["suave"], titleColor=CORES["suave"], gridColor=CORES["linha"], domainColor=CORES["borda"]
    ).configure_legend(labelColor=CORES["texto"])


def md(texto):
    """Protege o "$" em markdown: no Streamlit, texto entre dois cifrões vira fórmula matemática."""
    return texto.replace("$", r"\$")


def html(texto):
    """Protege o "$" dentro de HTML (usa o código do caractere)."""
    return texto.replace("$", "&#36;")


def reais_curto(valor):
    """R$ sem centavos, para caber nos cartões: 'R$ 6.388'."""
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ " + f"{abs(valor):,.0f}".replace(",", ".")


def cartao(rotulo, valor, detalhe="", cor_valor="var(--texto)"):
    return html(
        f'<div class="cartao"><div class="rotulo">{rotulo}</div>'
        f'<div class="valor" style="color:{cor_valor}">{valor}</div>'
        f'<div class="detalhe">{detalhe}</div></div>'
    )


def cor_da_sobra(taxa, para_texto=True):
    """Verde, amarelo ou vermelho. Para texto usa o tom do tema; para fundo (com letra branca), o tom escuro."""
    nome = "vermelho" if taxa < 0 else "amarelo" if taxa < 0.10 else "verde"
    if para_texto:
        return f"var(--{nome})"
    return {"verde": VERDE, "amarelo": AMARELO, "vermelho": VERMELHO}[nome]


def seta(variacao):
    """Variação do 1º para o 2º trimestre. Neutra: mostra direção, sem julgar."""
    if abs(variacao) < 0.05:
        return '<span style="color:var(--suave)">→ estável</span>'
    simbolo = "↑" if variacao > 0 else "↓"
    return f'<span style="color:var(--forte)">{simbolo} {abs(variacao):.0%}</span>'


# ---------- Dados ----------

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
    st.title("Diagnóstico financeiro")
    usuario = st.selectbox("Usuário", list(nomes.index), format_func=lambda u: f"{u} · {nomes[u].title()}")
    mes = st.select_slider(
        "Mês atual (simulação)", options=meses[2:], value=meses[-1], format_func=mes_por_extenso,
        help="Simula os meses chegando: o sistema só enxerga o extrato até este mês.",
    )
    escuro = st.toggle("Tema escuro", key="tema_escuro")
    st.divider()
    st.caption("Protótipo de estudo. **Todos os dados são fictícios.** O sistema não recomenda investimentos.")

CORES = PALETAS["escuro" if escuro else "claro"]
aplicar_tema(CORES)

resultado = calcular(mes, tuple(sorted(st.session_state.respostas.items())))
indicador = resultado["indicadores"].set_index("id_usuario").loc[usuario]
secoes = indicador["secoes"]
perguntas_usuario = resultado["perguntas"][resultado["perguntas"]["id_usuario"] == usuario]
notificacoes_usuario = resultado["notificacoes"][resultado["notificacoes"]["id_usuario"] == usuario]

# ---------- Cabeçalho ----------
st.header(f"Olá, {nomes[usuario].title().split()[0]}", anchor=False)
st.markdown(f"**Seu diagnóstico até {mes_por_extenso(mes)}**")
st.caption(md(secoes["renda"]))

taxa = indicador["taxa_de_sobra"]
colunas = st.columns(4)
colunas[0].markdown(cartao("Renda efetiva média", reais_curto(indicador["renda_media"]), "por mês"), unsafe_allow_html=True)
colunas[1].markdown(cartao("Gastos médios", reais_curto(indicador["gastos_total"]), "por mês"), unsafe_allow_html=True)
colunas[2].markdown(
    cartao("Sobra média", reais_curto(indicador["sobra_media"]), f"{taxa:.0%} da renda", cor_da_sobra(taxa)),
    unsafe_allow_html=True,
)
colunas[3].markdown(
    cartao("Parcelas no próximo mês", reais_curto(indicador["comprometido_proximo_mes"]),
           f"{indicador['percentual_comprometido']:.0%} da renda",
           "var(--vermelho)" if indicador["alto_comprometimento"] else "var(--texto)"),
    unsafe_allow_html=True,
)
st.write("")

abas = st.tabs([
    "Diagnóstico",
    f"Notificações ({len(notificacoes_usuario)})",
    f"Perguntas ({len(perguntas_usuario)})",
    "Parcelas",
    "Metas",
])

# ---------- Diagnóstico ----------
with abas[0]:
    blocos = pd.DataFrame({
        "bloco": [rotulo.split(" (")[0] for _, rotulo in BLOCOS],
        "nome": [nome for nome, _ in BLOCOS],
        "valor": [indicador[nome] for nome, _ in BLOCOS],
        "ordem": range(len(BLOCOS)),
    })
    esquerda, direita = st.columns([2, 3], gap="large")
    with esquerda:
        st.markdown('<div class="secao">Para onde foi o dinheiro</div>', unsafe_allow_html=True)
        rosca = alt.Chart(blocos[blocos["valor"] > 0]).mark_arc(innerRadius=70, cornerRadius=4).encode(
            theta=alt.Theta("valor:Q", stack=True),
            color=alt.Color(
                "bloco:N", legend=None,
                scale=alt.Scale(domain=list(blocos["bloco"]), range=[CORES_BLOCOS[nome] for nome, _ in BLOCOS]),
            ),
            order="ordem:Q",
            tooltip=[alt.Tooltip("bloco:N", title="Bloco"), alt.Tooltip("valor:Q", title="R$ por mês", format=",.2f")],
        )
        centro = alt.Chart(pd.DataFrame({"texto": [reais_curto(indicador["gastos_total"])]})).mark_text(
            fontSize=20, fontWeight="bold", color=CORES["texto"]
        ).encode(text="texto:N")
        st.altair_chart(estilo_grafico((rosca + centro).properties(height=260)), use_container_width=True)
        st.caption("Gasto médio por mês no centro. Passe o mouse para ver cada bloco.")
    with direita:
        base = indicador["renda_media"] if indicador["renda_media"] > 0 else 1
        linhas = []
        for nome, rotulo in BLOCOS:
            variacao = seta(indicador[f"variacao_{nome}"]) if nome != "a_confirmar" else ""
            titulo, _, detalhe = rotulo.partition(" (")
            detalhe = detalhe.rstrip(")")
            # Duas linhas: nome e valor em cima; detalhe, % da renda e variação embaixo
            linhas.append(
                f'<div class="bloco"><span class="bolinha" style="background:{CORES_BLOCOS[nome]}"></span>'
                f'<div class="corpo"><div class="topo"><span class="nome">{titulo}</span>'
                f'<span class="quanto">{reais(indicador[nome])}</span></div>'
                f'<div class="base"><span>{detalhe}</span><span>{indicador[nome] / base:.0%} da renda {variacao}</span></div>'
                f'</div></div>'
            )
        st.markdown(html(f'<div class="cartao">{"".join(linhas)}</div>'), unsafe_allow_html=True)
        st.caption("% da renda efetiva · setas comparam o último trimestre com o anterior")
        st.markdown(
            html(
                f'<div class="faixa" style="background:{cor_da_sobra(taxa, para_texto=False)}">Sobra média por mês'
                f'<div class="grande">{reais(indicador["sobra_media"])} · {taxa:.0%} da renda</div></div>'
            ),
            unsafe_allow_html=True,
        )
        if secoes["outras_entradas"]:
            st.caption(md(secoes["outras_entradas"]))

    st.markdown('<div class="secao">Pontos de atenção</div>', unsafe_allow_html=True)
    if secoes["pontos"]:
        st.markdown("".join(html(f'<span class="etiqueta">{ponto}</span>') for ponto in secoes["pontos"]), unsafe_allow_html=True)
    else:
        st.markdown('<span class="etiqueta ok">Nenhum ponto de atenção no período</span>', unsafe_allow_html=True)

    st.write("")
    for coluna, (titulo, texto) in zip(st.columns(3), [
        ("Evolução", secoes["evolucao"]),
        ("Compromissos futuros", secoes["compromissos"]),
        ("Reserva", secoes["reserva"]),
    ]):
        coluna.markdown(html(f'<div class="cartao"><div class="secao">{titulo}</div>{texto}</div>'), unsafe_allow_html=True)

    st.write("")
    with st.expander("Como calculamos?"):
        st.write(md(secoes["origem"]))
    with st.expander("Ver o relatório completo em texto"):
        st.text(resultado["textos"][usuario])

# ---------- Notificações ----------
with abas[1]:
    st.markdown(f'<div class="secao">O que mudou em {mes_por_extenso(mes)}</div>', unsafe_allow_html=True)
    if notificacoes_usuario.empty:
        st.markdown('<span class="etiqueta ok">Nenhuma notificação neste mês</span>', unsafe_allow_html=True)
    for linha in notificacoes_usuario.itertuples():
        cor = CORES_NOTIFICACAO.get(linha.tipo, AMARELO)
        st.markdown(
            html(f'<div class="aviso" style="border-left-color:{cor}"><div class="titulo" style="color:{cor}">{linha.tipo}</div>{linha.mensagem}</div>'),
            unsafe_allow_html=True,
        )
    st.caption("Mude o mês na barra lateral para simular a chegada de um novo mês.")

# ---------- Perguntas ----------
with abas[2]:
    respondidas = sum(1 for (dono, _) in st.session_state.respostas if dono == usuario)
    st.markdown(f'<div class="secao">O sistema precisa da sua ajuda em {len(perguntas_usuario)} transações</div>', unsafe_allow_html=True)
    st.caption(
        f"Respostas suas até agora: {respondidas}. Quando a confiança é baixa, o sistema pergunta em vez de "
        "adivinhar, e cada resposta vale também para pagamentos parecidos."
    )
    if perguntas_usuario.empty:
        st.markdown('<span class="etiqueta ok">Tudo classificado</span>', unsafe_allow_html=True)
    opcoes = sorted(CATEGORIAS)
    for linha in perguntas_usuario.head(10).itertuples():
        with st.container(border=True):
            texto, escolha, botao = st.columns([3, 2, 1], vertical_alignment="center")
            texto.markdown(md(f"**{linha.descricao}**  \n{reais(-linha.valor)} · {linha.data:%d/%m/%Y}"))
            texto.caption(md(linha.explicacao_final))
            sugestao = linha.sugestao_modelo if linha.sugestao_modelo in opcoes else "nao_identificado"
            categoria = escolha.selectbox(
                "Categoria", opcoes, index=opcoes.index(sugestao), key=f"cat_{linha.id_transacao}",
                format_func=lambda c: c.replace("_", " ").capitalize(), label_visibility="collapsed",
            )
            if botao.button("Confirmar", key=f"ok_{linha.id_transacao}", type="primary", use_container_width=True):
                st.session_state.respostas[(usuario, linha.contraparte)] = categoria
                st.rerun()
    if len(perguntas_usuario) > 10:
        st.caption(f"Mostrando 10 de {len(perguntas_usuario)}.")

# ---------- Parcelas ----------
with abas[3]:
    comprometimento = resultado["comprometimento"].set_index("id_usuario").loc[usuario]
    parcelas = resultado["parcelamentos"]
    parcelas = parcelas[parcelas["id_usuario"] == usuario].sort_values("parcelas_restantes", ascending=False)
    ativas = parcelas[parcelas["parcelas_restantes"] > 0]

    colunas = st.columns(3)
    colunas[0].markdown(cartao("Parcelamentos em aberto", str(len(ativas))), unsafe_allow_html=True)
    colunas[1].markdown(cartao("Total que falta pagar", reais_curto(comprometimento["total_restante"])), unsafe_allow_html=True)
    ultimo_mes = comprometimento["ultimo_mes_com_parcela"]
    ultimo = f"{ultimo_mes[5:]}/{ultimo_mes[:4]}" if len(ativas) else "—"  # formato curto para caber no cartão
    colunas[2].markdown(cartao("Última parcela", ultimo), unsafe_allow_html=True)
    st.write("")
    st.info(md(comprometimento["explicacao"]))

    if len(ativas):
        st.markdown('<div class="secao">Até quando cada parcela vai</div>', unsafe_allow_html=True)
        linha_do_tempo = ativas.assign(
            inicio=pd.to_datetime(mes + "-01"),
            fim=pd.to_datetime(ativas["mes_final"] + "-28"),
            faltam=ativas["parcelas_restantes"].astype(str) + "x de " + ativas["valor_parcela"].map(reais),
        )
        grafico = alt.Chart(linha_do_tempo).mark_bar(cornerRadius=4, color="#8B5CF6").encode(
            x=alt.X("inicio:T", title=None, axis=alt.Axis(format="%m/%Y")),
            x2="fim:T",
            y=alt.Y("contraparte:N", title=None, sort="-x"),
            tooltip=[alt.Tooltip("contraparte:N", title="Onde"), alt.Tooltip("faltam:N", title="Faltam")],
        ).properties(height=max(120, 45 * len(ativas)))
        st.altair_chart(estilo_grafico(grafico), use_container_width=True)
    for explicacao in parcelas["explicacao"]:
        st.markdown(md(f"- {explicacao}"))

# ---------- Metas ----------
with abas[4]:
    st.markdown('<div class="secao">Simular uma meta</div>', unsafe_allow_html=True)
    coluna_nome, coluna_valor, coluna_prazo = st.columns([2, 1, 1])
    nome_meta = coluna_nome.text_input("Objetivo", "Computador novo")
    valor_meta = coluna_valor.number_input("Valor (R$)", min_value=100.0, value=4000.0, step=100.0)
    prazo = coluna_prazo.number_input("Prazo (meses)", min_value=1, value=10, step=1)
    meta = Meta(nome_meta, valor_meta, int(prazo), meses[0])
    acompanhamento = acompanhar(meta, list(resultado["aportes"].loc[usuario]))
    resumo = previsao(meta, acompanhamento)

    cores_situacao = {"concluída": "var(--verde)", "adiantada": "var(--verde)", "no ritmo": "var(--verde)", "atrasada": "var(--amarelo)"}
    colunas = st.columns(3)
    colunas[0].markdown(cartao("Reservar por mês", reais_curto(meta.valor_mensal), f"até {mes_por_extenso(meta.mes_final)}"), unsafe_allow_html=True)
    colunas[1].markdown(cartao("Guardado até agora", reais_curto(resumo["acumulado"]), f"de {reais_curto(meta.valor_alvo)}"), unsafe_allow_html=True)
    colunas[2].markdown(
        cartao("Situação", resumo["situacao"].capitalize(), "comparado ao ritmo necessário", cores_situacao.get(resumo["situacao"], "var(--amarelo)")),
        unsafe_allow_html=True,
    )
    st.write("")
    progresso = min(resumo["acumulado"] / meta.valor_alvo, 1.0) if meta.valor_alvo else 0.0
    st.progress(max(progresso, 0.0), text=f"{progresso:.0%} da meta")
    st.write(md(plano_da_meta(meta, indicador["sobra_media"], indicador["alto_comprometimento"], indicador["tipo_renda"])))
    st.write(md(resumo["explicacao"]))

    grafico = acompanhamento.melt(id_vars="mes", value_vars=["acumulado", "esperado"], var_name="serie", value_name="valor")
    grafico["serie"] = grafico["serie"].map({"acumulado": "Guardado (poupança)", "esperado": "Necessário para o prazo"})
    linhas = alt.Chart(grafico).mark_line(point=True, strokeWidth=3).encode(
        x=alt.X("mes:N", title=None),
        y=alt.Y("valor:Q", title="R$"),
        color=alt.Color("serie:N", title=None, scale=alt.Scale(range=["#0F766E", "#9CA3AF"]), legend=alt.Legend(orient="top")),
        strokeDash=alt.StrokeDash("serie:N", legend=None, scale=alt.Scale(range=[[1, 0], [6, 4]])),
    ).properties(height=280)
    st.altair_chart(estilo_grafico(linhas), use_container_width=True)
    st.caption("O acompanhamento usa o que foi transferido para a poupança desde janeiro.")
