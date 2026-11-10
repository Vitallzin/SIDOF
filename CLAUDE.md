# Sistema Inteligente de Diagnóstico e Orientação Financeira (protótipo)

Protótipo de estudo de um sistema de educação financeira que analisa o histórico de transações de um usuário, classifica movimentações, identifica renda, parcelas e anomalias, e gera diagnóstico, alertas e metas. Usa dados fictícios.

Contexto completo:
@docs/01_proposta_original.md
@docs/02_plano_do_prototipo.md

## Como trabalhar com o usuário

- O usuário é **iniciante em programação** e atua como maestro: ele decide o que fazer e o que não fazer.
- Responda **em português**, em linguagem simples. Ao usar um termo técnico, explique em uma frase.
- Trabalhe **uma fase por vez**, seguindo o plano. Ao terminar uma fase, resuma o que foi feito, mostre exemplos concretos e **espere aprovação** antes de começar a próxima.
- **Não altere decisões do plano** sem perguntar. Se achar que algo deveria mudar, proponha e explique o motivo.
- Antes de instalar pacotes novos ou apagar arquivos, avise.
- Se algo estiver ambíguo e impactar o resultado, pergunte (no máximo 5 perguntas por vez).

## Regras técnicas

- Linguagem: Python. Comentários e mensagens ao usuário em português.
- **Reprodutibilidade:** sempre use semente aleatória fixa (`random_state` / `seed`).
- **Testes:** cada funcionalidade nova vem com testes automáticos (pytest). Rode os testes antes de dizer que terminou.
- **Avaliação honesta:**
  - Compare todo modelo com um baseline simples.
  - Separe treino e teste por **usuário ou período**, nunca aleatoriamente por linha.
  - Mostre exemplos concretos (acertos e erros), não só métricas.
  - Lembre que os dados são sintéticos: resultados não provam desempenho no mundo real.
- **Anomalias:** o modelo é não supervisionado. Os rótulos das anomalias plantadas servem **só para avaliar**, nunca para treinar.
- **Dados:** os dados do projeto (gerador, testes, treino, avaliação) são sempre fictícios. Nunca colocar chaves de API ou credenciais no código.
- **Faturas em PDF (decisão do maestro):** a interface aceita faturas enviadas pelos testadores, inclusive reais. Elas são lidas só em memória: nunca salvas em disco, nunca no Git (`*.pdf` está no .gitignore) e nunca usadas para treinar.
- **Código:** simples e legível, funções pequenas, sem otimização prematura.

## Regras de produto (não negociáveis)

- Nunca rotular o usuário ("gastador", "irresponsável"). Use linguagem factual e neutra.
- Nunca recomendar ativos financeiros específicos.
- Nunca acusar o usuário de irregularidade fiscal. Entrada sem origem conhecida é "renda não identificada".
- Toda classificação tem nível de confiança. Confiança baixa significa perguntar ao usuário, não inventar.
- Todo alerta deve ter uma explicação curta de por que foi gerado.

## Comandos úteis

Rodar a partir da pasta do projeto (Windows):

- Instalar: `python -m venv .venv` e depois `.venv\Scripts\python -m pip install -r requirements.txt`
- Rodar: `.venv\Scripts\python -m financas`
- Testar: `.venv\Scripts\python -m pytest`
- Interface: `.venv\Scripts\streamlit run app.py`
