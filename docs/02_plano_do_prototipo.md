# Plano do Protótipo: Sistema Inteligente de Diagnóstico e Orientação Financeira

Este documento complementa `01_proposta_original.md`. A proposta explica **o quê e por quê**. Este plano define **como vamos construir o protótipo**, quais decisões já foram tomadas e em que ordem o trabalho acontece.

## 1. Contexto e escopo

- **Natureza do projeto:** protótipo de estudo/portfólio para demonstrar a ideia. Não é um produto.
- **Dados:** 100% fictícios (gerados por nós) e, opcionalmente, datasets públicos para o treino inicial de categorias. Nenhum dado financeiro real entra no projeto.
- **Fora do escopo:** integração real com bancos (Open Finance), aspectos regulatórios e jurídicos formais (LGPD, contratos). A proposta menciona esses temas como requisitos de um produto real; aqui basta **não criar nada que os impeça**: sem dados reais no repositório, coleta mínima de dados, código organizado para permitir controle de acesso no futuro.
- **Quem trabalha:** o usuário é o **maestro**. Ele é iniciante em programação, decide o que fazer e o que não fazer, e aprova cada etapa. O Claude Code escreve, testa e explica.

## 2. Decisões já tomadas

### Abordagem híbrida de classificação
1. **Regras** resolvem os casos óbvios (ex.: descrição contendo nome de uma concessionária de energia vira "energia").
2. Para o que sobrar, um **modelo do scikit-learn** lê a descrição da transação e prevê a categoria. Ponto de partida: `TfidfVectorizer` + `LogisticRegression`.
3. O modelo devolve uma probabilidade, que vira o **nível de confiança**.
4. Abaixo de um limite de confiança, o sistema **pergunta ao usuário** em vez de inventar.
5. Cada correção do usuário vira um **novo exemplo de treino**.

### Detecção de anomalias (dois níveis)
- **Estatística simples por usuário e categoria:** compara o mês atual com o histórico da própria pessoa (média e desvio padrão, ou método IQR). É fácil de explicar em linguagem natural.
- **`IsolationForest` (scikit-learn):** para anomalias que dependem de várias características ao mesmo tempo.
- **Importante:** o modelo é **não supervisionado**, ou seja, não recebe rótulos de "isto é anomalia". As anomalias que injetarmos nos dados sintéticos servem **apenas para avaliar** se o modelo as encontra (precisão e revocação por tipo de anomalia).

### Princípios do produto (vêm da proposta)
- Sem rótulos negativos para o usuário ("gastador", "irresponsável"). Usar linguagem factual: "aumento dos gastos", "alto comprometimento da renda".
- **Nunca** recomendar ativos financeiros específicos. O foco é educação financeira e reserva.
- Nunca acusar o usuário de irregularidade fiscal. Entrada sem origem conhecida vira "renda não identificada".
- Toda classificação carrega um nível de confiança. Baixa confiança gera pergunta ao usuário.
- A decisão final é sempre do usuário.

### Dados
- **Gerador de dados sintéticos brasileiros:** PIX, boleto, cartão de débito e crédito, parcelas, transferências entre contas do próprio usuário, renda fixa, variável e eventual (ex.: ajuda dos pais).
- **Vários perfis de usuário**, para que anomalia seja sempre relativa ao histórico de cada um:
  1. Renda fixa, poucos compromissos
  2. Renda variável (autônomo)
  3. Renda fixa com muitas parcelas e dívidas
  4. Renda baixa com pouca margem
- **Horizonte:** 6 meses de histórico por usuário.
- **Semente aleatória fixa** (`random_state` / `seed`) em tudo, para resultados reproduzíveis.
- **Datasets públicos (opcionais):** podem ser usados no treino inicial de categorias. Candidatos: "Comprehensive Credit Card Transactions" (Kaggle), "Financial Transaction Categorization" (Hugging Face, majoritariamente sintético, em inglês) e "MoneyData" (Mendeley, ~6.500 transações reais anonimizadas, uma conta). Nenhum contém PIX/boleto brasileiro. **Verificar licença antes de usar** e registrar a fonte no README.

### Tecnologias sugeridas (o Claude Code pode propor mudanças, justificando)
Python 3, pandas, scikit-learn, SQLite (ou CSV no início), pytest, Streamlit para a interface.

## 3. Fases do trabalho

Regra geral: ao final de cada fase o Claude Code roda os testes, resume o que fez **em linguagem simples**, mostra **exemplos concretos** (não só números) e **espera a aprovação do maestro** antes de seguir.

**Fase 0: Preparação.** Estrutura de pastas, ambiente virtual, `requirements.txt`, pytest funcionando, `README.md` inicial.
*Pronto quando:* um teste de exemplo passa e o projeto roda com um comando.

**Fase 1: Gerador de dados sintéticos.** Perfis de usuário, categorias, casos ambíguos de PIX, transferências internas, parcelas, renda eventual. Gera dois tipos de saída: (a) o extrato que o sistema vê e (b) um arquivo separado com a "verdade" (categoria real e anomalias plantadas), usado só para avaliação.
*Pronto quando:* CSVs gerados de forma reproduzível e uma amostra revisada pelo maestro.

**Fase 2: Normalização e classificação por regras.** Limpeza dos dados, regras de categorização, nível de confiança por regra, categoria "não identificada".
*Pronto quando:* relatório com % classificado por regra e lista de casos não identificados.

**Fase 3: Modelo de classificação (scikit-learn).** Treino para o que as regras não resolvem, com comparação contra o baseline (só regras), divisão treino/teste **por usuário ou período**, e simulação do ciclo de correção do usuário.
*Pronto quando:* métricas por categoria, exemplos de acertos e erros, e resposta clara à pergunta "o modelo melhorou em relação às regras?".

**Fase 4: Renda e transferências internas.** Classificar renda fixa, variável ou autônoma (média, mínima histórica, variação). Distinguir renda efetiva de ajuda eventual e de transferência entre contas próprias.
*Pronto quando:* cada perfil sintético é identificado corretamente e os casos difíceis são revisados.

**Fase 5: Parcelas e compromissos futuros.** Valor total da compra, parcela mensal, comprometimento futuro da renda.
*Pronto quando:* exemplo do documento (R$ 1.200 em 12 x R$ 100) reproduzido corretamente.

**Fase 6: Indicadores e diagnóstico.** Renda média e estabilidade, essenciais, discricionários, parcelas, capacidade de poupança, evolução dos gastos. Relatório em texto, com linguagem neutra.
*Pronto quando:* o exemplo da proposta (renda de R$ 3.000 dividida em essenciais, discricionários, parcelas e sobra) sai como relatório legível.

**Fase 7: Metas financeiras.** Meta de valor e prazo, cálculo do quanto reservar por mês, acompanhamento e aviso de atraso.
*Pronto quando:* exemplo da proposta (R$ 4.000 em 10 meses) funciona, inclusive quando o ritmo real é menor que o necessário.

**Fase 8: Anomalias.** Método estatístico e `IsolationForest`, comparados entre si. Tipos de anomalia plantadas: pico em uma categoria, cobrança duplicada, estabelecimento novo com valor alto, frequência incomum de transações.
*Pronto quando:* precisão e revocação por tipo de anomalia, 10 anomalias detectadas e 10 não detectadas mostradas como exemplo, e cada alerta com explicação em uma frase.

**Fase 9: Interface e monitoramento simulado.** Interface simples (Streamlit) mostrando diagnóstico, alertas e metas; simulação de novos meses chegando e gerando notificações.
*Pronto quando:* o maestro consegue abrir a interface e navegar pelos perfis de usuário.

**Fase 10: Avaliação e documentação.** Indicadores da seção 19 da proposta aplicados ao que for possível medir nos dados sintéticos; README final com limitações declaradas.
*Pronto quando:* o projeto pode ser apresentado do começo ao fim.

## 4. O que será feito no primeiro prompt (Sessão 1)

**Nesta sessão ainda não se escreve o sistema.** O objetivo é alinhar o entendimento e deixar o ambiente pronto.

1. Ler `CLAUDE.md`, `docs/01_proposta_original.md` e este plano.
2. Resumir em até 10 linhas o que entendeu do projeto.
3. Listar **até 5 dúvidas** que impactam as decisões da Fase 1 (se não houver, dizer que não há).
4. Propor, para aprovação: (a) estrutura de pastas, (b) lista final de categorias, (c) formato do CSV de transações e do arquivo de "verdade".
5. Executar **somente a Fase 0**.
6. Parar, resumir o que foi feito em linguagem simples e esperar o "ok" do maestro.

## 5. Decisões em aberto (propostas iniciais para o maestro aprovar ou mudar)

| Tema | Proposta inicial |
|---|---|
| Categorias | **Essencial:** moradia, energia, água, alimentação básica, transporte, telecom. **Prioritário:** educação, saúde, pagamento de dívidas. **Discricionário:** restaurantes e bares, lazer, jogos, compras, assinaturas. **Outros:** transferência interna, renda (fixa, variável, eventual), não identificado |
| Confiança mínima para não perguntar | 0,70 (ajustável) |
| Limite de anomalia (estatístico) | Acima de 2 desvios padrão do histórico do usuário na categoria (ajustável) |
| Interface | Streamlit (na Fase 9) |
| Datasets públicos | Começar só com dados sintéticos e avaliar os públicos depois da Fase 2 |

## 6. Critérios de sucesso do protótipo

- O pipeline roda de ponta a ponta com um comando.
- O modelo é comparado com o baseline de regras, e o resultado é reportado com honestidade, mesmo que ele não melhore.
- Precisão e revocação das anomalias são reportadas **por tipo** de anomalia plantada.
- O diagnóstico é legível, neutro e explica de onde vêm os números.
- Todos os testes passam.

## 7. Limitações que devem constar no README final

- Os dados são sintéticos: um modelo que vai bem neles **não prova** que funcionaria com dados reais. O protótipo demonstra o funcionamento do pipeline, não a eficácia no mundo real.
- PIX entre pessoas continua sendo ambíguo por natureza. A resposta correta nesses casos é baixa confiança e pergunta ao usuário.
- Categorias e limites de anomalia são escolhas de projeto e devem ser revisados com dados reais em uma versão futura.
