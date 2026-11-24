# SIDOF — Sistema Inteligente de Diagnóstico e Orientação Financeira

Protótipo de estudo de **educação financeira**. A partir do histórico de transações de uma pessoa (PIX, boletos,
cartão de débito e crédito, transferências), o sistema classifica cada gasto com um nível de confiança, entende a
renda, projeta as parcelas futuras, monta um diagnóstico em linguagem neutra, acompanha metas e aponta gastos fora
do padrão. Também aceita faturas de cartão em PDF.

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
| Saídas decididas sozinho pelo sistema em uso | **89,7%**, com **99,8%** de acerto e 0,2% de erros silenciosos |
| Só regras (baseline) × regras + modelo + respostas do usuário | 51,5% → **93,9%** decididas sozinho, mantendo 99,9% de acerto |
| Modelo em lojas já vistas × nunca vistas (teste duro) | 93,1% × **18,8%** de acerto (nesses casos ele pergunta) |
| Origem das entradas / perfis de renda | 98,5% corretas / **12 de 12** perfis, incluindo trocas de emprego |
| Parcelamentos encontrados | **27 de 27** |
| Anomalias encontradas (método estatístico) | 95% dos tipos previstos e 65% dos não previstos |
| Faturas fictícias em PDF lidas de volta | **907 de 907** compras sem erro |
| Testes automáticos | **168**, todos passando |

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

Na barra lateral, escolha o usuário e o "mês atual", que simula os meses chegando (o sistema só enxerga o extrato
até ele), e o tema claro ou escuro. Abas:

- **Diagnóstico**: para onde foi o dinheiro, sobra, evolução, compromissos, reserva e pontos de atenção.
- **Notificações**: o que mudou no mês (queda de renda, nova parcela, cobrança duplicada, compra alta em lugar novo…).
- **Perguntas**: o que o sistema não sabe; cada resposta vale também para pagamentos parecidos.
- **Parcelas**: valor já reservado nos próximos 12 meses e cada parcelamento com barra de progresso.
- **Metas**: quanto reservar por mês, progresso, marcos e próximo passo.
- **Importar fatura**: envie uma fatura de cartão em PDF (fictícia ou real) ou baixe uma de exemplo.

**Rodar os testes:**

```bash
.venv\Scripts\python -m pytest
```

### Faturas em PDF e privacidade

O leitor é genérico e entende linhas no formato "data, descrição, parcela, valor". Faturas enviadas pela interface
são lidas **só em memória**: não são salvas, não vão para o repositório (`*.pdf` está no `.gitignore`, exceto os
PDFs de `documentos/`) e não são usadas para treinar. Faturas escaneadas (imagem) ou com layout muito diferente não
são lidas.

## Como funciona (resumo)

1. **Normalização**: limpa o texto e separa a operação (PIX, débito, boleto), a contraparte e a parcela "k/n".
2. **Classificação híbrida**: regras de palavra-chave → memória das respostas do usuário → modelo
   (TF-IDF de pedaços de 2 a 4 letras + regressão logística). Abaixo de 0,70 de confiança, vira pergunta.
   Em PIX para pessoas, o modelo nunca decide sozinho.
3. **Renda**: salário (com ou sem a palavra "salário"), autônomo, ajuda da família, renda não identificada,
   transferências entre contas próprias e troca de emprego.
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
| `tests/` | 168 testes automáticos (pytest) |
| `documentos/` | Documentação em PDF e Word, e os HTMLs que geram os PDFs |
| `docs/` | Proposta, plano e decisões registradas |
| `dados_gerados/` | Dados e relatórios criados pelo comando (não vão para o repositório) |

## Limitações

- **Dados sintéticos:** o mesmo autor escreveu o gerador, as regras e os detectores, então os números são otimistas.
  O protótipo demonstra o funcionamento do pipeline, não a eficácia no mundo real.
- **Lojas novas:** o modelo de texto decorou as lojas que viu e acerta só 18,8% em lojas novas; quem resolve esses
  casos são as regras e as respostas do usuário.
- **PIX entre pessoas** é ambíguo por natureza: a resposta correta é baixa confiança e pergunta ao usuário.
- **Nomes curtos de loja** ("EMPORIO DONA ROSA") podem ser tratados como pessoa e virar pergunta.
- **Nova assinatura recorrente** não é detectada como anomalia por nenhum dos métodos.
- **Limites de decisão** (0,70 de confiança, 30% de comprometimento, 3 desvios padrão, reserva de 3 ou 6 meses) são
  escolhas de projeto e precisam ser revistos com dados reais.
- **Efeito no comportamento** (poupar mais, reduzir dívidas) não pode ser medido com dados sintéticos; exige usuários
  reais acompanhados ao longo do tempo.
- A fatura de janeiro é estimada (não há dezembro) e "guardado para a meta" é tudo o que foi para a poupança.

## Tecnologias

Python 3.12 · pandas · NumPy · scikit-learn · Streamlit · Altair · pdfplumber · fpdf2 · pytest

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
