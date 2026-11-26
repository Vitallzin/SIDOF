# SIDOF — Sistema Inteligente de Diagnóstico e Orientação Financeira

Protótipo de estudo de **educação financeira**. A partir do histórico de transações de uma pessoa (PIX, boletos,
cartão de débito e crédito, transferências), o sistema classifica cada gasto com um nível de confiança, entende a
renda, projeta as parcelas futuras, monta um diagnóstico em linguagem neutra, acompanha metas e aponta gastos fora
do padrão. Também aceita faturas de cartão e extratos de conta, em PDF ou CSV.

- **Testar o app online:** https://mvp-sidof.streamlit.app/
- **Explorar o código com explicações (DeepWiki):** https://deepwiki.com/Vitallzin/SIDOF

> **Todos os dados de desenvolvimento são fictícios.** Eles mostram que o sistema funciona e é coerente, mas não
> provam o desempenho com extratos reais (veja [Limitações](#limitações)).

## Documentação

| Documento | Para quem |
|---|---|
| [Documentação técnica (PDF)](documentos/Documentacao_Tecnica_Diagnostico_Financeiro.pdf) | Explicação completa do projeto e de todo o algoritmo, com resultados |
| [Como funciona, explicação simples (PDF)](documentos/Como_Funciona_Explicacao_Simples.pdf) | Quem quer entender a ideia sem termos técnicos |
| [Documentação do projeto (Word)](documentos/Documentacao_Projeto_Diagnostico_Financeiro.docx) | Modelo de documentação do curso, preenchido |
| [Proposta original](docs/01_proposta_original.md) e [plano do protótipo](docs/02_plano_do_prototipo.md) | Contexto e decisões do projeto |
| [Decisões da detecção de anomalias](docs/03_decisoes_anomalias.md) | Limites definidos antes de ver os resultados |

Os PDFs são gerados a partir dos HTMLs em `documentos/fontes/` com `.venv\Scripts\python documentos\fontes\gerar_pdfs.py`
(usa o Microsoft Edge instalado no Windows).

## Principais resultados (dados sintéticos)

| O que foi medido | Resultado |
|---|---|
| Saídas decididas sozinho pelo sistema em uso | **92,2%**, com **99,8%** de acerto e 0,2% de erros silenciosos |
| Só regras (baseline) × regras + modelo + respostas do usuário | 52,8% → **95,8%** decididas sozinho, com 99,1% de acerto |
| Modelo em lojas já vistas × nunca vistas (teste duro) | 95,7% × **34,2%** de acerto (nesses casos ele pergunta) |
| Origem das entradas / perfis de renda | 100% corretas / **12 de 12** perfis, incluindo trocas de emprego |
| Parcelamentos encontrados (inclui IPVA e IPTU) | **38 de 38** |
| Anomalias encontradas (método estatístico) | 93% dos tipos previstos e 65% dos não previstos |
| Faturas fictícias em PDF lidas de volta | **807 de 807** compras sem erro |
| Extrato fictício de 6 meses: SIDOF × categoria do banco | **86%** de concordância nas saídas comparáveis |
| Testes automáticos | **274**, todos passando |

## Como instalar (Windows)

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Como usar

**Rodar todas as fases e gerar os relatórios** (cerca de 1,5 minuto):

```bash
.venv\Scripts\python -m financas
```

**Abrir a interface** no navegador (http://localhost:8501):

```bash
.venv\Scripts\streamlit run app.py
```

Na barra lateral, escolha de quem é o diagnóstico:

- **Usuário de simulação**: um dos 12 usuários fictícios e o "mês atual", que simula os meses chegando (o sistema só
  enxerga o extrato até ele).
- **Minha fatura**: envie faturas do cartão e/ou extratos da conta, em PDF ou CSV, com seu nome e a renda mensal
  (ambos opcionais). Todas as abas passam a mostrar o diagnóstico desses documentos. Sem renda (nem no extrato, nem
  digitada), aparecem só os gastos; com ela, aparecem também a sobra, as porcentagens e a comparação com as metas.
  Há um botão para baixar exemplos fictícios (3 faturas em PDF e o extrato da conta em CSV).

Também há o tema claro ou escuro. Abas:

- **Diagnóstico**: para onde foi o dinheiro, sobra, evolução, compromissos, reserva e pontos de atenção.
- **Notificações**: o que mudou no mês (queda de renda, nova parcela, cobrança duplicada, compra alta em lugar novo…).
- **Perguntas**: o que o sistema não sabe; cada resposta vale também para pagamentos parecidos.
- **Parcelas**: valor já reservado nos próximos 12 meses e cada parcelamento com barra de progresso.
- **Metas**: quanto reservar por mês, progresso, marcos e próximo passo.
- **Movimentações** (só no modo Minha fatura): cada saída lida, com categoria, confiança e o porquê; quando o extrato
  traz a categoria do banco, mostra também quanto o SIDOF concorda com ela.
- **Aprendizado**: o que o SIDOF já aprendeu com os usuários e o gráfico de perguntas por fatura ao longo do tempo.

**Rodar os testes:**

```bash
.venv\Scripts\python -m pytest
```

### Faturas, extratos e privacidade

Fatura e extrato usam o sinal ao contrário: na fatura, valor positivo é compra; no extrato, negativo é saída. Por isso
o sistema primeiro descobre o tipo do documento (título "Extrato"/"Fatura", colunas Entrada/Saída/Saldo). No extrato,
decide se cada linha entrou ou saiu, do jeito mais seguro para o mais fraco: coluna Entrada/Saída (pela posição na
página), sinal escrito ("-92,79", "92,79 D"), variação do saldo e, por último, palavras ("PIX RECEBIDO", "SALÁRIO").
O CSV aceita `;` ou `,`, vírgula ou ponto decimal, acentos em UTF-8 ou Latin-1 e reconhece as colunas pelo nome.

Para não contar nada duas vezes:

- **Renda:** se o extrato já mostra salário num mês, vale o do extrato; a renda digitada entra só nos meses sem renda.
- **Fatura + extrato:** o pagamento da fatura no extrato não é gasto (as compras já estão na fatura). Sem a fatura,
  a tela avisa que as compras do cartão não aparecem em detalhe.
- **Mesmo documento em dois formatos** (ex.: PDF e CSV): cada movimentação conta uma vez.

Aplicações e resgates (CDB, poupança) contam como dinheiro guardado; rendimentos e reembolsos entram, mas não são
renda do trabalho. Quando o extrato traz a categoria do banco, o SIDOF **não a usa para classificar**: classifica
sozinho e depois compara. Num extrato fictício de 6 meses, concordou com o banco em 86% das saídas comparáveis.

O arquivo **nunca é salvo**: não fica no servidor nem vai para o repositório (`*.pdf` está no `.gitignore`, exceto os
PDFs de `documentos/`). Documentos escaneados (imagem) ou com layout muito diferente não são lidos.

### Aprendizado contínuo (Firebase)

Quando alguém confirma a categoria de uma loja (aba **Perguntas**, nos dois modos), o voto vai para o
aprendizado coletivo. Com **2 confirmações de sessões diferentes**, a loja passa a ser reconhecida para todos (com a
explicação "aprendido com confirmações de outros usuários") e entra no **re-treino do modelo**, feito a cada 1 hora
ou pelo botão da aba Aprendizado.

- **Guardado:** nome da loja, categoria votada, origem do voto (fatura real ou usuário fictício) e um código aleatório
  de sessão, que não identifica ninguém. Por fatura, só números (compras, perguntas, resolvidas pelo aprendizado).
- **Nunca guardado:** valores, datas, o arquivo da fatura, PIX para pessoas, renda e transferências.
- **Onde:** no Firestore (Firebase). A chave fica nos **Secrets** do Streamlit Cloud, nunca no código. Sem a chave
  (rodando no seu computador, por exemplo), o app usa a memória local e funciona do mesmo jeito.

Para configurar, crie um projeto no Firebase, ative o Firestore, gere a chave da conta de serviço e cole os campos
dela nos Secrets do app, numa seção `[firebase]`.

## Como funciona (resumo)

1. **Normalização**: limpa o texto e separa a operação (PIX, débito, boleto), a contraparte e a parcela "k/n".
2. **Classificação híbrida**: regras de palavra-chave → memória das respostas do usuário → modelo
   (TF-IDF de pedaços de 2 a 4 letras + regressão logística). Abaixo de 0,70 de confiança, vira pergunta.
   Em PIX para pessoas, o modelo nunca decide sozinho.
3. **Renda** (sem nenhuma pergunta): todo dinheiro que entra conta como renda, menos transferências entre contas
   próprias, aplicações, rendimentos, reembolsos, empréstimos e ajuda da família. O sistema diz se a renda é fixa ou
   variável e percebe troca de emprego, salário que começou e salário que parou (período sem emprego fixo).
4. **Parcelas**: valor total, restante e comprometimento da renda nos próximos 12 meses.
5. **Diagnóstico e metas**: blocos de gasto, sobra, evolução, pontos de atenção e acompanhamento de metas.
6. **Anomalias**: método estatístico (histórico do próprio usuário) comparado ao IsolationForest.

A avaliação separa treino e teste **por usuário**, compara todo modelo com um baseline simples e usa a "verdade"
dos dados sintéticos apenas para medir. O sistema em uso (`financas/sistema.py`) treina numa base separada de
usuários fictícios e nunca lê a verdade dos usuários atendidos.

## Relatórios gerados

O comando `python -m financas` grava em `dados_gerados/` (semente fixa 42, sempre os mesmos dados):

| Arquivo | Conteúdo |
|---|---|
| `extrato.csv`, `usuarios.csv` | O que o sistema vê: transações e nomes |
| `verdade.csv`, `usuarios_verdade.csv` | Categoria real, anomalias plantadas e perfis (só para avaliação) |
| `relatorio_regras.txt` | Quanto as regras reconhecem, erros e casos não identificados |
| `relatorio_modelo.txt`, `relatorio_teste_duro.txt` | Regras × modelo, por categoria e mês a mês; teste com lojas nunca vistas |
| `relatorio_renda.txt` | Origem das entradas e perfis de renda |
| `relatorio_parcelas.txt` | Parcelamentos e comprometimento futuro |
| `relatorio_diagnostico.txt`, `indicadores.csv` | Diagnóstico de cada usuário e precisão do diagnóstico |
| `relatorio_metas.txt` | Meta exemplo (R$ 4.000 em 10 meses) acompanhada para cada usuário |
| `relatorio_anomalias.txt`, `alertas.csv` | Precisão e revocação por tipo de anomalia, exemplos detectados e perdidos |
| `relatorio_sistema.txt` | O sistema em uso nos usuários atendidos |
| `relatorio_faturas.txt`, `fatura_exemplo.pdf` | Leitura e classificação das faturas fictícias em PDF |
| `relatorio_final.txt`, `indicadores_finais.csv` | Indicadores da seção 19 da proposta, por perfil |

## Estrutura

| Pasta | O que tem |
|---|---|
| `financas/` | Código do sistema (`sistema.py` é o sistema em uso; os outros módulos são as fases) |
| `app.py`, `.streamlit/` | Interface Streamlit e tema |
| `financas/aprendizado.py` | Aprendizado contínuo (memória local ou Firebase) |
| `tests/` | 168 testes automáticos (pytest) |
| `documentos/` | Documentação em PDF e Word, e os HTMLs que geram os PDFs |
| `docs/` | Proposta, plano e decisões registradas |
| `dados_gerados/` | Dados e relatórios criados pelo comando (não vão para o repositório) |

## Limitações

- **Dados sintéticos:** o mesmo autor escreveu o gerador, as regras e os detectores, então os números são otimistas.
  O protótipo demonstra o funcionamento do pipeline, não a eficácia no mundo real.
- **Lojas novas:** o modelo de texto decorou as lojas que viu e acerta só 34,2% em lojas novas; quem resolve esses
  casos são as regras e as respostas do usuário.
- **PIX entre pessoas** é ambíguo por natureza: a resposta correta é baixa confiança e pergunta ao usuário.
  Para saber se um PIX foi para pessoa ou loja, o sistema usa o CPF/CNPJ quando o arquivo traz (CNPJ = loja), a
  mesma loja vista no cartão e o primeiro nome. Num banco, o CPF/CNPJ viria sempre; nos arquivos, nem sempre.
  O número do documento é apagado na leitura e nunca é guardado nem mostrado.
  O mesmo sobrenome só sugere "transferência familiar"; quem confirma é o usuário.
- **Gastos legítimos raros e altos** (ex.: conserto do carro) também geram o alerta de "lugar novo"; por isso 67% dos
  alertas acertam uma anomalia plantada.
- **Nomes curtos de loja** ("EMPORIO DONA ROSA") podem ser tratados como pessoa e virar pergunta.
- **Nova assinatura recorrente** não é detectada como anomalia por nenhum dos métodos.
- **Limites de decisão** (0,70 de confiança, 30% de comprometimento, 3 desvios padrão, reserva de 3 ou 6 meses) são
  escolhas de projeto e precisam ser revistos com dados reais.
- **Efeito no comportamento** (poupar mais, reduzir dívidas) não pode ser medido com dados sintéticos; exige usuários
  reais acompanhados ao longo do tempo.
- A fatura de janeiro é estimada (não há dezembro) e "guardado para a meta" é tudo o que foi para a poupança.
- **Aprendizado coletivo** depende da boa-fé dos testadores: a regra de 2 confirmações reduz, mas não elimina, o
  risco de alguém ensinar uma categoria errada. PIX para lojas de nome curto não entra no aprendizado (por segurança,
  é tratado como possível pessoa).

## Tecnologias

Python 3.12 · pandas · NumPy · scikit-learn · Streamlit · Altair · pdfplumber · fpdf2 · Firebase (firebase-admin) · pytest

## Situação

- [x] Fase 0: preparação do ambiente
- [x] Fase 1: gerador de dados sintéticos
- [x] Fase 2: normalização e classificação por regras
- [x] Fase 3: modelo de classificação (com teste duro em lojas nunca vistas)
- [x] Fase 4: renda e transferências internas (inclui troca de emprego e salário sem a palavra "salário")
- [x] Fase 5: parcelas e compromissos futuros
- [x] Fase 6: indicadores e diagnóstico
- [x] Fase 7: metas financeiras
- [x] Fase 8: anomalias (com tipos não previstos)
- [x] Fase 9: interface e monitoramento simulado (com importação de faturas em PDF)
- [x] Fase 10: avaliação e documentação
