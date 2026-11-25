"""Interface do protótipo (Fase 9). Rodar com: .venv\\Scripts\\streamlit run app.py

Mostra o diagnóstico, as perguntas do sistema, as notificações do mês, as parcelas e uma meta.
A barra lateral escolhe de quem é o diagnóstico:
- Usuário de simulação: um dos usuários fictícios, com um seletor que simula os meses chegando.
- Minha fatura: faturas de cartão e extratos de conta (PDF ou CSV) enviados pela pessoa (lidos só em
  memória), com a renda mensal opcional. Todas as abas passam a mostrar os dados desses documentos.
Usa só o sistema em uso (financas/sistema.py): nada aqui lê a verdade dos usuários.
"""

import hashlib
import io
import time
import uuid
import zipfile

import altair as alt
import pandas as pd
import streamlit as st

from financas.aprendizado import (
    MINIMO_DE_CONFIRMACOES,
    conhecimento_coletivo,
    criar_armazenamento,
    exemplos_de_treino,
    registrar_confirmacao,
    contagem_do_documento,
    registrar_uso_fatura,
)
from financas.aprendizado import resumo as resumo_do_aprendizado
from financas.categorias import CATEGORIAS, CATEGORIAS_FORA_DOS_GASTOS, nome_exibicao
from financas.diagnostico import BLOCOS
from financas.formatacao import mes_por_extenso, reais
from financas.faturas_pdf import (
    ID_FATURA,
    compras_no_cartao,
    gerar_fatura_pdf,
)
from financas.gerador import gerar_dados
from financas.metas import Meta, acompanhar, aportes_por_mes, plano_da_meta, previsao
from financas.monitoramento import extrato_ate, notificacoes_do_mes
from financas.parcelas import comprometimento_da_renda, compromissos_futuros, identificar_parcelamentos
from financas.renda import classificar_entradas, perfil_de_renda
from financas.normalizacao import normalizar_texto
from financas.sistema import Sistema, treinar_modelo_da_base
from financas.comparacao_banco import comparar_com_banco
from financas.documentos import extrato_de_documentos
from financas.extratos import EXTRATO, FATURA, ler_documento

st.set_page_config(page_title="SIDOF · Diagnóstico financeiro", layout="wide")

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
    .etiqueta.pendente {{background: transparent; color: var(--suave); border-color: var(--borda);}}
    .aviso {{background: var(--cartao); border-radius: 12px; padding: .8rem 1rem; margin-bottom: .6rem;
            border: 1px solid var(--borda); border-left-width: 6px;}}
    .aviso .titulo {{font-weight: 600; margin-bottom: .15rem;}}
    .parcelamento {{margin-bottom: .8rem;}}
    .parcelamento .topo {{display: flex; justify-content: space-between; gap: .8rem; align-items: flex-start;}}
    .parcelamento .nome {{font-weight: 600; color: var(--texto);}}
    .parcelamento .tipo {{font-size: .72rem; color: var(--suave); text-transform: uppercase; letter-spacing: .04em;}}
    .parcelamento .mensal {{font-weight: 700; font-size: 1.15rem; color: var(--texto); text-align: right; white-space: nowrap;}}
    .parcelamento .mensal small {{display: block; font-weight: 400; font-size: .72rem; color: var(--suave);}}
    .parcelamento .barra {{height: 8px; border-radius: 999px; background: var(--linha); margin: .7rem 0 .45rem 0; overflow: hidden;}}
    .parcelamento .barra div {{height: 100%; background: #8B5CF6; border-radius: 999px;}}
    .parcelamento .base {{display: flex; justify-content: space-between; gap: .6rem; flex-wrap: wrap; font-size: .8rem; color: var(--suave);}}
    .stApp button[kind="secondary"], .stApp [data-testid="stDownloadButton"] button {{
        background-color: var(--cartao) !important; color: var(--texto) !important; border: 1px solid var(--borda) !important;}}
    .stApp button[kind="secondary"]:hover, .stApp [data-testid="stDownloadButton"] button:hover {{
        border-color: #0F766E !important; color: #0F766E !important;}}
    .stApp button[kind="secondary"] p, .stApp [data-testid="stDownloadButton"] button p {{color: inherit !important;}}
    [data-testid="stFileUploaderDropzone"] {{background-color: var(--lateral) !important; border: 1px dashed var(--borda) !important;}}
    [data-testid="stFileUploaderDropzone"] span, [data-testid="stFileUploaderDropzone"] small {{color: var(--suave) !important;}}
    .secao {{font-size: 1.05rem; font-weight: 600; margin: .2rem 0 .4rem 0; color: var(--texto);}}
    [data-testid="stToast"] {{background-color: var(--cartao) !important; color: var(--texto) !important;
        border: 1px solid var(--borda) !important; box-shadow: 0 4px 14px rgba(0, 0, 0, .25) !important;}}
    [data-testid="stToast"] p, [data-testid="stToast"] div, [data-testid="stToast"] span {{color: var(--texto) !important;}}
    [data-testid="stToast"] button svg {{fill: var(--suave) !important; color: var(--suave) !important;}}
    [data-testid="stSpinner"], [data-testid="stSpinner"] p {{color: var(--texto) !important;}}
    [data-testid="stText"], [data-testid="stText"] * {{color: var(--texto) !important;}}
    [data-testid="stExpander"] summary, [data-testid="stExpander"] summary:hover,
    [data-testid="stExpander"] details[open] > summary {{background-color: var(--linha) !important; color: var(--texto) !important;}}
    [data-testid="stExpander"] summary p, [data-testid="stExpander"] summary span {{color: var(--texto) !important;}}
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

@st.cache_resource(show_spinner="Gerando dados fictícios...")
def carregar():
    """Dados fictícios dos usuários atendidos."""
    return gerar_dados()


def credenciais_firebase():
    """Chave do Firebase guardada nos Secrets do Streamlit (nunca no código). Sem ela, usa memória local."""
    try:
        return dict(st.secrets["firebase"])
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def abrir_armazenamento():
    return criar_armazenamento(credenciais_firebase())


@st.cache_data(show_spinner=False)
def ler_conhecimento(_armazenamento, janela):
    """Lojas aprendidas por todos. A mesma leitura vale para todas as sessões dentro da janela de 15 s."""
    return conhecimento_coletivo(_armazenamento)


@st.cache_resource(ttl=3600, show_spinner="Treinando o modelo com o que os usuários ensinaram...")
def modelo_atual():
    """Re-treina a cada 1 hora (ou pelo botão da aba Aprendizado) com as lojas aprendidas."""
    exemplos = exemplos_de_treino(conhecimento_coletivo(abrir_armazenamento()))
    return treinar_modelo_da_base(exemplos_extra=exemplos), len(exemplos)


dados = carregar()
extrato_simulado, usuarios_simulados = dados["extrato"], dados["usuarios"]
meses_simulados = sorted(extrato_simulado["data"].str[:7].unique())
armazenamento = abrir_armazenamento()
modelo, lojas_no_modelo = modelo_atual()

if "sessao" not in st.session_state:
    st.session_state.sessao = uuid.uuid4().hex[:12]  # código aleatório: separa votos sem identificar ninguém
JANELA_DE_LEITURA = 15  # segundos: o que outras pessoas ensinam aparece aqui em até 15 s
conhecimento = ler_conhecimento(armazenamento, int(time.time() // JANELA_DE_LEITURA))


def aprender(contraparte, categoria, origem, descricao):
    """Manda a resposta para o aprendizado coletivo (só lojas; PIX para pessoas e renda ficam de fora)."""
    try:
        guardou = registrar_confirmacao(armazenamento, contraparte, categoria, st.session_state.sessao, origem, descricao)
    except Exception:
        st.session_state.aviso = "Não foi possível salvar no aprendizado coletivo agora; sua resposta vale nesta sessão."
        return
    if guardou:
        ler_conhecimento.clear()  # a própria resposta aparece na hora para todos
        # Mostrado depois do recarregamento da página (um aviso feito antes do st.rerun some na hora)
        st.session_state.aviso = f"Obrigado! \"{contraparte}\" entrou no aprendizado coletivo."


if "aviso" in st.session_state:
    st.toast(st.session_state.pop("aviso"))


@st.cache_data(show_spinner="Atualizando o diagnóstico...", max_entries=40)
def calcular(chave_fonte, mes, respostas, conhecimento_itens, lojas_no_modelo, _modelo, _extrato, _usuarios):
    """Tudo o que a tela mostra, olhando só o extrato até o mês escolhido.

    chave_fonte identifica os dados (simulação ou o conjunto de faturas enviado): o resultado
    guardado só é reaproveitado para os mesmos dados.
    """
    modelo, extrato, usuarios = _modelo, _extrato, _usuarios
    sistema = Sistema(extrato_ate(extrato, mes), usuarios, modelo, dict(conhecimento_itens))
    sistema.memoria = dict(respostas)
    meses_vistos = sorted(sistema.classificado["mes"].unique())
    indicadores, textos = sistema.diagnosticar()
    entradas = classificar_entradas(sistema.classificado, usuarios)
    perfis = perfil_de_renda(entradas, meses_vistos, sorted(usuarios["id_usuario"]))
    parcelamentos = identificar_parcelamentos(sistema.classificado)
    compromissos = compromissos_futuros(parcelamentos, sorted(usuarios["id_usuario"]), mes)
    return {
        "indicadores": indicadores,
        "textos": textos,
        "saidas": sistema.saidas(),
        "perguntas": sistema.perguntas(),
        "parcelamentos": parcelamentos,
        "comprometimento": comprometimento_da_renda(parcelamentos, compromissos, perfis),
        "compromissos": compromissos,
        "aportes": aportes_por_mes(sistema.classificado, meses_vistos),
        "notificacoes": notificacoes_do_mes(extrato, usuarios, modelo, mes, dict(respostas)),
    }


@st.cache_data(max_entries=20, show_spinner="Lendo o arquivo...")
def ler_arquivo(conteudo, nome_arquivo):
    """Lê a fatura ou o extrato só em memória; nada é gravado em disco.

    Os exemplos do SIDOF trazem "fictícia/fictício" no título ou no nome: o voto deles não conta como dado real.
    """
    return ler_documento(conteudo, nome_arquivo)


def _extrato_csv_de_exemplo(dono, meses_exemplo):
    """Extrato fictício da conta corrente em CSV (as compras no cartão ficam nas faturas)."""
    conta = extrato_simulado[
        (extrato_simulado["id_usuario"] == dono) & (extrato_simulado["conta"] == "corrente")
        & extrato_simulado["data"].str[:7].isin(meses_exemplo)
    ].sort_values("data", kind="stable")
    linhas = ["Data;Descrição;Valor"] + [
        f"{pd.Timestamp(m.data):%d/%m/%Y};{m.descricao};{m.valor:.2f}".replace(".", ",") for m in conta.itertuples()
    ]
    return "\n".join(linhas).encode("utf-8")


@st.cache_data(show_spinner=False)
def documentos_de_exemplo():
    """Três faturas fictícias seguidas e o extrato da conta dos mesmos meses, num .zip, para testar o modo Minha fatura."""
    no_cartao = extrato_simulado[extrato_simulado["meio"] == "cartao_credito"]
    dono = no_cartao["id_usuario"].value_counts().idxmax()  # quem mais usa o cartão
    nome = usuarios_simulados.set_index("id_usuario")["nome"][dono]
    meses_exemplo = meses_simulados[-3:]
    pacote = io.BytesIO()
    with zipfile.ZipFile(pacote, "w") as arquivo_zip:
        for mes_exemplo in meses_exemplo:
            pdf = gerar_fatura_pdf(compras_no_cartao(extrato_simulado, dono, mes_exemplo), f"{nome} (FICTICIA)", mes_exemplo)
            arquivo_zip.writestr(f"fatura_ficticia_{mes_exemplo}.pdf", pdf)
        arquivo_zip.writestr("extrato_ficticio_conta.csv", _extrato_csv_de_exemplo(dono, meses_exemplo))
    return pacote.getvalue()


if "respostas" not in st.session_state:
    st.session_state.respostas = {}

# ---------- Barra lateral ----------
SIMULACAO, MINHA_FATURA = "Usuário de simulação", "Minha fatura"
nomes_simulados = usuarios_simulados.set_index("id_usuario")["nome"]
documentos = {}  # assinatura do arquivo -> Documento (fatura ou extrato já lido)
with st.sidebar:
    st.title("SIDOF")
    st.caption("Sistema Inteligente de Diagnóstico e Orientação Financeira")
    fonte = st.radio("De quem é o diagnóstico?", [SIMULACAO, MINHA_FATURA], key="fonte")
    modo_fatura = fonte == MINHA_FATURA
    if not modo_fatura:
        usuario = st.selectbox("Usuário", list(nomes_simulados.index), format_func=lambda u: f"{u} · {nomes_simulados[u].title()}")
        mes = st.select_slider(
            "Mês atual (simulação)", options=meses_simulados[2:], value=meses_simulados[-1], format_func=mes_por_extenso,
            help="Simula os meses chegando: o sistema só enxerga o extrato até este mês.",
        )
    else:
        usuario = ID_FATURA
        nome_titular = st.text_input("Seu nome (opcional)", help="Aparece no cabeçalho e ajuda a reconhecer transferências para você mesmo.")
        renda_informada = st.number_input(
            "Renda mensal (opcional)", min_value=0.0, value=0.0, step=100.0, format="%.2f",
            help="Com a renda aparecem a sobra, as porcentagens e a comparação com as metas. Deixe 0 para não informar.",
        )
        arquivos = st.file_uploader(
            "Faturas ou extratos (PDF ou CSV)", type=["pdf", "csv"], accept_multiple_files=True,
            help="Faturas do cartão (uma por mês) e/ou extratos da conta. O sistema descobre sozinho qual é qual.",
        )
        st.download_button(
            "Baixar exemplos (3 faturas + extrato)", data=documentos_de_exemplo(), file_name="exemplos_ficticios_sidof.zip",
            mime="application/zip", use_container_width=True,
        )
        st.caption("Descompacte e envie os arquivos. Eles são lidos só em memória e nunca são salvos.")
        for arquivo in arquivos or []:
            conteudo = arquivo.getvalue()
            # O mesmo arquivo enviado duas vezes conta uma vez só
            documentos.setdefault(hashlib.sha256(conteudo).hexdigest(), ler_arquivo(conteudo, arquivo.name))
        com_compras = {chave: doc for chave, doc in documentos.items() if not doc.vazio}
        if com_compras:
            extrato, usuarios, avisos = extrato_de_documentos(
                list(com_compras.values()), normalizar_texto(nome_titular), renda_informada
            )
            meses = sorted(extrato["data"].str[:7].unique())
            if len(meses) > 1:
                mes = st.select_slider(
                    "Mês da fatura", options=meses, value=meses[-1], format_func=mes_por_extenso,
                    help="O diagnóstico olha os documentos até este mês.",
                )
            else:
                mes = meses[0]
    escuro = st.toggle("Tema escuro", key="tema_escuro")
    st.divider()
    if modo_fatura:
        st.caption("Protótipo de estudo. Só o nome da loja e a categoria que você confirmar entram no aprendizado coletivo. O sistema não recomenda investimentos.")
    else:
        st.caption("Protótipo de estudo. **Todos os dados são fictícios.** O sistema não recomenda investimentos.")

CORES = PALETAS["escuro" if escuro else "claro"]
aplicar_tema(CORES)

if modo_fatura:
    ilegiveis = [doc.nome for doc in documentos.values() if doc.vazio]
    if ilegiveis:
        st.warning(
            "Não encontrei movimentações em: " + ", ".join(ilegiveis) + ". "
            "Arquivos escaneados (imagem) ou com layout muito diferente não são lidos por este protótipo."
        )
    if not com_compras:
        st.header("Diagnóstico da sua fatura", anchor=False)
        st.markdown(
            "Envie **faturas do cartão e/ou extratos da conta** (PDF ou CSV) na barra lateral. "
            "Todo o diagnóstico, as perguntas, as parcelas e as metas passam a ser desses documentos."
        )
        st.caption(
            "Funciona com documentos fictícios ou reais. Na fatura, valores positivos são compras; no extrato, o sistema "
            "descobre o que entrou e o que saiu (pelas colunas Entrada/Saída, pelo sinal, pelo saldo ou pelas palavras). "
            "O arquivo não é salvo. Sem documento à mão? Baixe os exemplos na barra lateral."
        )
        st.stop()
    chave_fonte = "fatura|" + "|".join(sorted(com_compras)) + f"|{renda_informada}|{normalizar_texto(nome_titular)}"
    # Voto de fatura real só quando há alguma fatura que não é de exemplo
    origem_voto = "ficticio" if all(doc.ficticio for doc in com_compras.values()) else "fatura"
    primeiro_nome = nome_titular.strip().split()[0].title() if nome_titular.strip() else ""
    # Métrica do aprendizado: quantas saídas de cada documento novo viraram pergunta (só números)
    registradas = st.session_state.setdefault("faturas_registradas", set())
    for assinatura, doc in com_compras.items():
        if assinatura not in registradas:
            registradas.add(assinatura)
            extrato_do_doc, usuarios_do_doc, _ = extrato_de_documentos([doc], normalizar_texto(nome_titular))
            classificadas = Sistema(extrato_do_doc, usuarios_do_doc, modelo, conhecimento).saidas()
            try:
                registrar_uso_fatura(armazenamento, **contagem_do_documento(classificadas))
            except Exception:
                pass  # métrica opcional: não atrapalha o diagnóstico
else:
    extrato, usuarios, meses = extrato_simulado, usuarios_simulados, meses_simulados
    chave_fonte, origem_voto = "simulacao", "ficticio"
    primeiro_nome = nomes_simulados[usuario].title().split()[0]

meses_vistos = [m for m in meses if m <= mes]
# Só o usuário escolhido: no SIDOF tudo é calculado por pessoa (cada um comparado com o próprio histórico),
# então o resultado é o mesmo e a tela responde bem mais rápido
respostas_do_usuario = tuple(sorted((chave, categoria) for chave, categoria in st.session_state.respostas.items() if chave[0] == usuario))
resultado = calcular(
    f"{chave_fonte}|{usuario}", mes, respostas_do_usuario, tuple(sorted(conhecimento.items())),
    lojas_no_modelo, modelo, extrato[extrato["id_usuario"] == usuario], usuarios[usuarios["id_usuario"] == usuario],
)
indicador = resultado["indicadores"].set_index("id_usuario").loc[usuario]
secoes = indicador["secoes"]
perguntas_usuario = resultado["perguntas"][resultado["perguntas"]["id_usuario"] == usuario]
notificacoes_usuario = resultado["notificacoes"][resultado["notificacoes"]["id_usuario"] == usuario]
sem_renda = indicador["renda_media"] <= 0

# ---------- Cabeçalho ----------
st.header(f"Olá, {primeiro_nome}" if primeiro_nome else "Diagnóstico da sua fatura", anchor=False)
if modo_fatura:
    contagem = pd.Series([doc.tipo for doc in com_compras.values()]).value_counts()
    partes = [
        f"{contagem[tipo]} {nome}{'s' if contagem[tipo] > 1 else ''}"
        for tipo, nome in ((FATURA, "fatura"), (EXTRATO, "extrato")) if tipo in contagem
    ]
    st.markdown(f"**Diagnóstico de {' e '.join(partes)} até {mes_por_extenso(mes)}**")
    for aviso in avisos:
        st.info(md(aviso))
else:
    st.markdown(f"**Seu diagnóstico até {mes_por_extenso(mes)}**")
st.caption(md(secoes["renda"]))

taxa = indicador["taxa_de_sobra"]
colunas = st.columns(4)
if sem_renda:
    colunas[0].markdown(
        cartao("Renda efetiva média", "—", "não informada" if modo_fatura else "nenhuma renda identificada", "var(--suave)"),
        unsafe_allow_html=True,
    )
else:
    colunas[0].markdown(cartao("Renda efetiva média", reais_curto(indicador["renda_media"]), "por mês"), unsafe_allow_html=True)
colunas[1].markdown(cartao("Gastos médios", reais_curto(indicador["gastos_total"]), "por mês"), unsafe_allow_html=True)
if sem_renda:
    colunas[2].markdown(cartao("Sobra média", "—", "precisa da renda", "var(--suave)"), unsafe_allow_html=True)
else:
    colunas[2].markdown(
        cartao("Sobra média", reais_curto(indicador["sobra_media"]), f"{taxa:.0%} da renda", cor_da_sobra(taxa)),
        unsafe_allow_html=True,
    )
colunas[3].markdown(
    cartao("Parcelas no próximo mês", reais_curto(indicador["comprometido_proximo_mes"]),
           "por mês" if sem_renda else f"{indicador['percentual_comprometido']:.0%} da renda",
           "var(--vermelho)" if indicador["alto_comprometimento"] else "var(--texto)"),
    unsafe_allow_html=True,
)
st.write("")

nomes_abas = {
    "diagnostico": "Diagnóstico",
    "notificacoes": "Notificações",
    "perguntas": "Perguntas",
    "parcelas": "Parcelas",
    "metas": "Metas",
}
if modo_fatura:
    nomes_abas["compras"] = "Movimentações"
nomes_abas["aprendizado"] = "Aprendizado"
# key: a aba escolhida é lembrada entre um clique e outro (ex.: depois de confirmar uma pergunta)
abas = dict(zip(nomes_abas, st.tabs(list(nomes_abas.values()), key="aba_atual")))

# ---------- Diagnóstico ----------
with abas["diagnostico"]:
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
        compara_meses = len(meses_vistos) >= 2  # com um mês só não há evolução para mostrar
        linhas = []
        for nome, rotulo in BLOCOS:
            variacao = seta(indicador[f"variacao_{nome}"]) if nome != "a_confirmar" and compara_meses else ""
            parte_da_renda = "" if sem_renda else f"{indicador[nome] / indicador['renda_media']:.0%} da renda "
            titulo, _, detalhe = rotulo.partition(" (")
            detalhe = detalhe.rstrip(")")
            # Duas linhas: nome e valor em cima; detalhe, % da renda e variação embaixo
            linhas.append(
                f'<div class="bloco"><span class="bolinha" style="background:{CORES_BLOCOS[nome]}"></span>'
                f'<div class="corpo"><div class="topo"><span class="nome">{titulo}</span>'
                f'<span class="quanto">{reais(indicador[nome])}</span></div>'
                f'<div class="base"><span>{detalhe}</span><span>{parte_da_renda}{variacao}</span></div>'
                f'</div></div>'
            )
        st.markdown(html(f'<div class="cartao">{"".join(linhas)}</div>'), unsafe_allow_html=True)
        legenda = [] if sem_renda else ["% da renda efetiva"]
        if compara_meses:
            legenda.append("setas comparam a segunda metade do período com a primeira")
        if legenda:
            st.caption(" · ".join(legenda))
        if sem_renda:
            faixa = (
                f'<div class="faixa" style="background:#6B7280">Sobra média por mês'
                f'<div class="grande">Informe sua renda mensal na barra lateral para ver a sobra</div></div>'
            )
        else:
            faixa = (
                f'<div class="faixa" style="background:{cor_da_sobra(taxa, para_texto=False)}">Sobra média por mês'
                f'<div class="grande">{reais(indicador["sobra_media"])} · {taxa:.0%} da renda</div></div>'
            )
        st.markdown(html(faixa), unsafe_allow_html=True)
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
        relatorio = resultado["textos"][usuario]
        if modo_fatura:  # o código interno "FATURA" não diz nada para a pessoa
            relatorio = relatorio.replace(f"Diagnóstico de {ID_FATURA}", "Seu diagnóstico", 1)
        st.text(relatorio)

# ---------- Notificações ----------
with abas["notificacoes"]:
    avisos_no_mes = f"{len(notificacoes_usuario)} aviso" + ("s" if len(notificacoes_usuario) != 1 else "")
    st.markdown(f'<div class="secao">O que mudou em {mes_por_extenso(mes)} ({avisos_no_mes})</div>', unsafe_allow_html=True)
    if notificacoes_usuario.empty:
        st.markdown('<span class="etiqueta ok">Nenhuma notificação neste mês</span>', unsafe_allow_html=True)
    for linha in notificacoes_usuario.itertuples():
        cor = CORES_NOTIFICACAO.get(linha.tipo, AMARELO)
        st.markdown(
            html(f'<div class="aviso" style="border-left-color:{cor}"><div class="titulo" style="color:{cor}">{linha.tipo}</div>{linha.mensagem}</div>'),
            unsafe_allow_html=True,
        )
    if not modo_fatura:
        st.caption("Mude o mês na barra lateral para simular a chegada de um novo mês.")
    elif len(meses) > 1:
        st.caption("Mude o mês da fatura na barra lateral para ver o que mudou em cada mês.")
    else:
        st.caption("Com mais faturas (meses seguidos), aparecem avisos de queda de renda, novas parcelas e aumentos de gasto.")

# ---------- Perguntas ----------
with abas["perguntas"]:
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
            parcela = f" · parcela {linha.parcela}" if isinstance(linha.parcela, str) and linha.parcela else ""
            texto.markdown(md(f"**{linha.descricao}**  \n{reais(-linha.valor)} · {linha.data:%d/%m/%Y}{parcela}"))
            texto.caption(md(linha.explicacao_final))
            sugestao = linha.sugestao_modelo if linha.sugestao_modelo in opcoes else "nao_identificado"
            categoria = escolha.selectbox(
                "Categoria", opcoes, index=opcoes.index(sugestao), key=f"cat_{linha.id_transacao}",
                format_func=nome_exibicao, label_visibility="collapsed",
            )
            if botao.button("Confirmar", key=f"ok_{linha.id_transacao}", type="primary", use_container_width=True):
                with st.spinner("Salvando sua resposta e atualizando o diagnóstico..."):
                    st.session_state.respostas[(usuario, linha.contraparte)] = categoria
                    aprender(linha.contraparte, categoria, origem_voto, linha.descricao)
                st.rerun()
    if len(perguntas_usuario) > 10:
        st.caption(f"Mostrando 10 de {len(perguntas_usuario)}.")

# ---------- Parcelas ----------
def cartao_parcelamento(item):
    """Um parcelamento: onde, quanto por mês, barra de quanto já foi pago e até quando vai."""
    pagas = item["ultima_paga"] / item["total_parcelas"]
    if item["parcelas_restantes"] > 0:
        rodape = f'Faltam {reais(item["valor_restante"])} · até {mes_por_extenso(item["mes_final"])}'
    else:
        rodape = "Quitado"
    return html(
        f'<div class="cartao parcelamento">'
        f'<div class="topo"><div><div class="nome">{item["contraparte"]}</div>'
        f'<span class="tipo">{item["tipo"]}</span></div>'
        f'<div class="mensal">{reais(item["valor_parcela"])}<small>por mês</small></div></div>'
        f'<div class="barra"><div style="width:{pagas:.0%}"></div></div>'
        f'<div class="base"><span>{item["ultima_paga"]} de {item["total_parcelas"]} pagas</span><span>{rodape}</span></div>'
        f"</div>"
    )


with abas["parcelas"]:
    comprometimento = resultado["comprometimento"].set_index("id_usuario").loc[usuario]
    parcelas = resultado["parcelamentos"]
    parcelas = parcelas[parcelas["id_usuario"] == usuario].sort_values("parcelas_restantes", ascending=False)
    ativas = parcelas[parcelas["parcelas_restantes"] > 0]
    quitadas = parcelas[parcelas["parcelas_restantes"] == 0]

    colunas = st.columns(3)
    colunas[0].markdown(cartao("Parcelamentos em aberto", str(len(ativas))), unsafe_allow_html=True)
    colunas[1].markdown(cartao("Total que falta pagar", reais_curto(comprometimento["total_restante"])), unsafe_allow_html=True)
    ultimo_mes = comprometimento["ultimo_mes_com_parcela"]
    ultimo = f"{ultimo_mes[5:]}/{ultimo_mes[:4]}" if len(ativas) else "—"  # formato curto para caber no cartão
    colunas[2].markdown(cartao("Última parcela", ultimo), unsafe_allow_html=True)
    st.write("")
    cor_aviso = "var(--vermelho)" if comprometimento["alto_comprometimento"] else "#8B5CF6"
    st.markdown(
        html(f'<div class="aviso" style="border-left-color:{cor_aviso}">{comprometimento["explicacao"]}</div>'),
        unsafe_allow_html=True,
    )

    if len(ativas):
        compromissos = resultado["compromissos"].loc[usuario]
        por_mes = pd.DataFrame({"mes": [f"{m[5:]}/{m[2:4]}" for m in compromissos.index], "valor": compromissos.values})
        st.markdown('<div class="secao">Quanto já está reservado para parcelas nos próximos meses</div>', unsafe_allow_html=True)
        barras = alt.Chart(por_mes).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, color="#8B5CF6").encode(
            x=alt.X("mes:N", title=None, sort=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("valor:Q", title="R$"),
            tooltip=[alt.Tooltip("mes:N", title="Mês"), alt.Tooltip("valor:Q", title="R$", format=",.2f")],
        ).properties(height=200)
        st.altair_chart(estilo_grafico(barras), use_container_width=True)

        st.markdown('<div class="secao">Em aberto</div>', unsafe_allow_html=True)
        for coluna, item in zip(st.columns(2) * len(ativas), ativas.to_dict("records")):
            coluna.markdown(cartao_parcelamento(item), unsafe_allow_html=True)
    else:
        st.markdown('<span class="etiqueta ok">Nenhuma parcela em aberto</span>', unsafe_allow_html=True)

    if len(quitadas):
        with st.expander(f"Já quitados ({len(quitadas)})"):
            for item in quitadas.to_dict("records"):
                st.markdown(cartao_parcelamento(item), unsafe_allow_html=True)

# ---------- Metas ----------
def anel_de_progresso(fracao):
    """Anel com a parte da meta já guardada e a porcentagem no centro."""
    fracao = max(min(fracao, 1.0), 0.0)
    partes = pd.DataFrame({"parte": ["guardado", "falta"], "valor": [fracao, 1 - fracao], "ordem": [0, 1]})
    anel = alt.Chart(partes).mark_arc(innerRadius=62, outerRadius=82, cornerRadius=6).encode(
        theta=alt.Theta("valor:Q", stack=True),
        color=alt.Color("parte:N", legend=None, scale=alt.Scale(domain=["guardado", "falta"], range=["#0F766E", CORES["linha"]])),
        order="ordem:Q",
    )
    centro = alt.Chart(pd.DataFrame({"texto": [f"{fracao:.0%}"]})).mark_text(
        fontSize=26, fontWeight="bold", color=CORES["texto"]
    ).encode(text="texto:N")
    return estilo_grafico((anel + centro).properties(height=190))


def proximo_passo(meta, resumo):
    """Uma frase curta e neutra sobre o que manteria a meta no rumo."""
    if resumo["falta"] == 0:
        return "Meta atingida."
    if resumo["mensal_para_cumprir_prazo"]:
        return (
            f"Guardar {reais(resumo['mensal_para_cumprir_prazo'])} por mês mantém o prazo de "
            f"{mes_por_extenso(meta.mes_final)}."
        )
    if resumo["meses_previstos"]:
        return f"No ritmo atual ({reais(resumo['ritmo_mensal'])} por mês), a meta chega em cerca de {resumo['meses_previstos']} meses."
    return f"Reservar {reais(meta.valor_mensal)} por mês leva à meta no prazo."


with abas["metas"]:
    st.markdown('<div class="secao">Simular uma meta</div>', unsafe_allow_html=True)
    coluna_nome, coluna_valor, coluna_prazo = st.columns([2, 1, 1])
    nome_meta = coluna_nome.text_input("Objetivo", "Computador novo")
    valor_meta = coluna_valor.number_input("Valor (R$)", min_value=100.0, value=4000.0, step=100.0)
    prazo = coluna_prazo.number_input("Prazo (meses)", min_value=1, value=10, step=1)
    meta = Meta(nome_meta, valor_meta, int(prazo), meses[0])
    acompanhamento = acompanhar(meta, list(resultado["aportes"].loc[usuario]))
    resumo = previsao(meta, acompanhamento)
    fracao = resumo["acumulado"] / meta.valor_alvo if meta.valor_alvo else 0.0

    cores_situacao = {"concluída": "var(--verde)", "adiantada": "var(--verde)", "no ritmo": "var(--verde)", "atrasada": "var(--amarelo)"}
    cor_situacao = cores_situacao.get(resumo["situacao"], "var(--amarelo)")
    anel, painel = st.columns([1, 2], gap="large")
    with anel:
        st.altair_chart(anel_de_progresso(fracao), use_container_width=True)
        st.markdown(
            html(f'<div style="text-align:center;color:var(--suave)">{reais(resumo["acumulado"])} de {reais(meta.valor_alvo)}</div>'),
            unsafe_allow_html=True,
        )
    with painel:
        colunas = st.columns(2)
        colunas[0].markdown(cartao("Reservar por mês", reais_curto(meta.valor_mensal), f"até {mes_por_extenso(meta.mes_final)}"), unsafe_allow_html=True)
        colunas[1].markdown(cartao("Situação", resumo["situacao"].capitalize(), "comparado ao ritmo necessário", cor_situacao), unsafe_allow_html=True)
        st.write("")
        st.markdown(
            html(
                f'<div class="aviso" style="border-left-color:{cor_situacao}"><div class="titulo">Próximo passo</div>'
                f"{proximo_passo(meta, resumo)}</div>"
            ),
            unsafe_allow_html=True,
        )
        marcos = "".join(
            f'<span class="etiqueta{" ok" if fracao >= marco else " pendente"}">{marco:.0%}</span>'
            for marco in (0.25, 0.5, 0.75, 1.0)
        )
        st.markdown(f'<div style="color:var(--suave);font-size:.85rem;margin-bottom:.3rem">Marcos</div>{marcos}', unsafe_allow_html=True)

    grafico = acompanhamento.melt(id_vars="mes", value_vars=["acumulado", "esperado"], var_name="serie", value_name="valor")
    grafico["serie"] = grafico["serie"].map({"acumulado": "Guardado (poupança e investimentos)", "esperado": "Necessário para o prazo"})
    linhas = alt.Chart(grafico).mark_line(point=True, strokeWidth=3).encode(
        x=alt.X("mes:N", title=None),
        y=alt.Y("valor:Q", title="R$"),
        color=alt.Color("serie:N", title=None, scale=alt.Scale(range=["#0F766E", "#9CA3AF"]), legend=alt.Legend(orient="top")),
        strokeDash=alt.StrokeDash("serie:N", legend=None, scale=alt.Scale(range=[[1, 0], [6, 4]])),
    ).properties(height=260)
    st.altair_chart(estilo_grafico(linhas), use_container_width=True)
    with st.expander("Detalhes da meta"):
        sobra_para_meta = None if sem_renda else indicador["sobra_media"]
        st.write(md(plano_da_meta(meta, sobra_para_meta, indicador["alto_comprometimento"], indicador["tipo_renda"])))
        st.write(md(resumo["explicacao"]))
        if modo_fatura:
            st.caption(
                "O acompanhamento usa as aplicações e transferências para a poupança que aparecem nos extratos "
                "(uma fatura de cartão sozinha não mostra o que foi guardado)."
            )
        else:
            st.caption(f"O acompanhamento usa o que foi guardado (poupança e investimentos) desde {mes_por_extenso(meses[0])}.")

# ---------- Movimentações (só no modo Minha fatura) ----------
FORA_DOS_GASTOS_NA_TABELA = CATEGORIAS_FORA_DOS_GASTOS
if modo_fatura:
    with abas["compras"]:
        saidas_vistas = resultado["saidas"]
        saidas_vistas = saidas_vistas[(saidas_vistas["id_usuario"] == usuario) & (saidas_vistas["conta"] != "poupanca")]
        gastos_vistos = saidas_vistas[~saidas_vistas["categoria_final"].isin(FORA_DOS_GASTOS_NA_TABELA)]
        automaticas = (~saidas_vistas["perguntar_usuario"]).mean() if len(saidas_vistas) else 0.0
        pelo_coletivo = int((saidas_vistas["origem"] == "coletivo").sum())
        ignoradas = sum(doc.ignoradas for doc in com_compras.values())
        st.markdown(f'<div class="secao">Saídas lidas até {mes_por_extenso(mes)}</div>', unsafe_allow_html=True)
        st.caption(
            "Cada fatura conta como um mês (compras do fim do mês anterior entram no mês da fatura). "
            "Aplicações, transferências entre suas contas e pagamentos de fatura aparecem na tabela, mas não contam como gasto."
        )
        colunas = st.columns(4)
        colunas[0].markdown(cartao("Saídas lidas", str(len(saidas_vistas)), f"{ignoradas} linha(s) ignorada(s)"), unsafe_allow_html=True)
        colunas[1].markdown(cartao("Total dos gastos", reais_curto(-gastos_vistos["valor"].sum())), unsafe_allow_html=True)
        colunas[2].markdown(cartao("Classificadas sozinho", f"{automaticas:.0%}", "o resto vira pergunta"), unsafe_allow_html=True)
        colunas[3].markdown(cartao("Aprendidas com outros", str(pelo_coletivo), "lojas que usuários já ensinaram"), unsafe_allow_html=True)
        st.write("")

        por_categoria = (
            gastos_vistos.assign(categoria=gastos_vistos["categoria_final"].map(nome_exibicao), valor=-gastos_vistos["valor"])
            .groupby("categoria", as_index=False)["valor"].sum()
        )
        barras = alt.Chart(por_categoria).mark_bar(cornerRadius=4, color="#0F766E").encode(
            x=alt.X("valor:Q", title="R$"),
            y=alt.Y("categoria:N", title=None, sort="-x", axis=alt.Axis(labelOverlap=False, labelLimit=220)),
            tooltip=[alt.Tooltip("categoria:N", title="Categoria"), alt.Tooltip("valor:Q", title="R$", format=",.2f")],
        ).properties(height=max(140, 32 * len(por_categoria)))
        st.markdown('<div class="secao">Gastos por categoria</div>', unsafe_allow_html=True)
        st.altair_chart(estilo_grafico(barras), use_container_width=True)

        comparacao = comparar_com_banco(saidas_vistas)
        if comparacao:
            st.markdown('<div class="secao">O SIDOF concorda com o banco?</div>', unsafe_allow_html=True)
            st.caption(
                "O extrato traz a categoria que o próprio banco deu a cada saída. O SIDOF não usa essa coluna para "
                "classificar: ele classifica sozinho e só depois compara. Categorias do banco sem equivalente no SIDOF "
                "ficam de fora" + (f" ({', '.join(comparacao['categorias_sem_equivalente'])})." if comparacao["categorias_sem_equivalente"] else ".")
            )
            colunas = st.columns(3)
            colunas[0].markdown(
                cartao("Concordância", f"{comparacao['taxa']:.0%}", f"{comparacao['concordam']} de {comparacao['comparaveis']} saídas"),
                unsafe_allow_html=True,
            )
            colunas[1].markdown(cartao("Ainda a confirmar", str(comparacao["pendentes"]), "o SIDOF vai perguntar"), unsafe_allow_html=True)
            colunas[2].markdown(cartao("Sem equivalente", str(comparacao["sem_equivalente"]), "fora da comparação"), unsafe_allow_html=True)
            st.write("")
            por_banco = comparacao["por_categoria"]
            barras_banco = alt.Chart(por_banco).mark_bar(cornerRadius=4, color="#3B82F6").encode(
                x=alt.X("taxa:Q", title="Concordância", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
                y=alt.Y("categoria_banco:N", title=None, sort="-x", axis=alt.Axis(labelOverlap=False, labelLimit=220)),
                tooltip=[
                    alt.Tooltip("categoria_banco:N", title="Categoria do banco"),
                    alt.Tooltip("transacoes:Q", title="Saídas comparadas"),
                    alt.Tooltip("concordam:Q", title="Concordam"),
                ],
            ).properties(height=max(140, 30 * len(por_banco)))
            st.altair_chart(estilo_grafico(barras_banco), use_container_width=True)
            if len(comparacao["discordancias"]):
                with st.expander(f"Onde o SIDOF e o banco discordam ({len(comparacao['discordancias'])})"):
                    st.dataframe(
                        comparacao["discordancias"].rename(columns={"descricao": "Descrição", "categoria_banco": "Banco", "sidof": "SIDOF"}),
                        hide_index=True, use_container_width=True,
                    )
                    st.caption("Discordar não quer dizer que o SIDOF errou: academia, por exemplo, pode ser saúde ou assinatura.")

        tabela = saidas_vistas.sort_values("data").assign(
            Data=saidas_vistas["data"].dt.strftime("%d/%m/%Y"),
            Valor=(-saidas_vistas["valor"]).map(reais),
            Categoria=saidas_vistas["categoria_final"].map(nome_exibicao),
            Confiança=saidas_vistas["confianca_final"].map(lambda valor: f"{valor:.0%}"),
        ).rename(columns={"descricao": "Descrição", "parcela": "Parcela", "explicacao_final": "Por quê", "categoria_banco": "Banco"})
        mostrar = ["Data", "Descrição", "Parcela", "Valor", "Categoria", "Confiança", "Por quê"]
        if comparacao:
            mostrar.insert(5, "Banco")
        st.markdown('<div class="secao">Todas as saídas</div>', unsafe_allow_html=True)
        st.dataframe(tabela[mostrar], hide_index=True, use_container_width=True)
        if len(perguntas_usuario):
            st.caption(f"{len(perguntas_usuario)} saída(s) com confiança baixa estão na aba Perguntas, esperando sua confirmação.")

# ---------- Aprendizado ----------
with abas["aprendizado"]:
    st.markdown('<div class="secao">O SIDOF aprende com quem usa</div>', unsafe_allow_html=True)
    st.caption(
        f"Quando alguém confirma a categoria de uma loja (na aba Perguntas, com usuários de simulação ou com suas faturas), o voto é guardado. "
        f"Com {MINIMO_DE_CONFIRMACOES} confirmações de sessões diferentes, a loja passa a ser reconhecida para todos "
        "e entra no re-treino do modelo. PIX para pessoas, valores e datas nunca são guardados."
    )
    try:
        dados_aprendizado = resumo_do_aprendizado(armazenamento)
    except Exception:
        dados_aprendizado = None
        st.warning("Não foi possível ler o aprendizado coletivo agora.")

    if dados_aprendizado:
        if armazenamento.nome == "Firebase":
            st.markdown('<span class="etiqueta ok">Guardando no Firebase: o aprendizado é permanente e compartilhado</span>', unsafe_allow_html=True)
        else:
            st.markdown(
                '<span class="etiqueta">Sem Firebase configurado: o aprendizado vale enquanto o app estiver aberto</span>',
                unsafe_allow_html=True,
            )
        colunas = st.columns(4)
        colunas[0].markdown(cartao("Lojas aprendidas", str(dados_aprendizado["lojas_aprendidas"]), f"com {MINIMO_DE_CONFIRMACOES}+ confirmações"), unsafe_allow_html=True)
        colunas[1].markdown(cartao("Lojas com votos", str(dados_aprendizado["lojas_com_votos"]), "esperando confirmações"), unsafe_allow_html=True)
        colunas[2].markdown(cartao("Confirmações", str(dados_aprendizado["confirmacoes"]), f"de {dados_aprendizado['sessoes']} sessões"), unsafe_allow_html=True)
        colunas[3].markdown(cartao("Documentos analisados", str(len(dados_aprendizado["usos"]))), unsafe_allow_html=True)
        origem = dados_aprendizado["aprendidas_por_origem"]
        st.caption(
            f"Lojas aprendidas por origem: {origem['fatura']} de faturas reais enviadas · "
            f"{origem['ficticio']} do ambiente de teste (usuários fictícios). "
            f"O modelo atual foi treinado com {lojas_no_modelo} loja(s) aprendida(s)."
        )
        st.write("")

        usos = pd.DataFrame(dados_aprendizado["usos"])
        st.markdown('<div class="secao">Perguntas em lojas por documento, ao longo do tempo</div>', unsafe_allow_html=True)
        # Só documentos que já guardam a contagem sem PIX para pessoas (os mais antigos não têm esse número)
        if "compras_lojas" in usos:
            usos = usos[usos["compras_lojas"].fillna(0) > 0].reset_index(drop=True)
        else:
            usos = usos.iloc[0:0]
        if usos.empty:
            st.info("Ainda nenhum documento analisado. Escolha 'Minha fatura' na barra lateral e envie uma fatura ou extrato.")
        else:
            usos["documento"] = usos.index + 1
            usos["perguntas_pct"] = usos["perguntas_lojas"] / usos["compras_lojas"]
            linha_tempo = alt.Chart(usos).mark_line(point=True, strokeWidth=3, color="#0F766E").encode(
                x=alt.X("documento:O", title="Documento analisado (em ordem)"),
                y=alt.Y("perguntas_pct:Q", title="Lojas que viraram pergunta", axis=alt.Axis(format=".0%"), scale=alt.Scale(domain=[0, 1])),
                tooltip=[
                    alt.Tooltip("documento:O", title="Documento"),
                    alt.Tooltip("compras_lojas:Q", title="Gastos em lojas"),
                    alt.Tooltip("perguntas_lojas:Q", title="Perguntas sobre lojas"),
                    alt.Tooltip("resolvidas_pelo_coletivo:Q", title="Resolvidas pelo aprendizado"),
                ],
            ).properties(height=240)
            st.altair_chart(estilo_grafico(linha_tempo), use_container_width=True)
            st.caption(
                "Não conta os PIX para pessoas: esses sempre viram pergunta (só você sabe a finalidade) e nunca são "
                "aprendidos. Se o sistema aprende, a linha tende a cair: cada documento novo gera menos perguntas sobre lojas."
            )

        aprendidas = dados_aprendizado["conhecimento"]
        if aprendidas:
            st.markdown('<div class="secao">Últimas lojas aprendidas</div>', unsafe_allow_html=True)
            ultimas = [chave for _, chave in dados_aprendizado["ultimas"]][:15]
            st.dataframe(
                pd.DataFrame([
                    {"Loja": aprendidas[chave][2], "Categoria": nome_exibicao(aprendidas[chave][0]), "Votos": aprendidas[chave][1]}
                    for chave in ultimas
                ]),
                hide_index=True, use_container_width=True,
            )

        if st.button("Atualizar aprendizado (re-treinar o modelo agora)"):
            modelo_atual.clear()
            ler_conhecimento.clear()
            calcular.clear()
            st.rerun()
