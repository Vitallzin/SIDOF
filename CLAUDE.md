# SIDOF — Sistema Inteligente de Diagnóstico e Orientação Financeira (protótipo)

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
- **Faturas e extratos (decisão do maestro):** a interface aceita faturas de cartão e extratos de conta (PDF ou CSV) enviados pelos testadores, inclusive reais. O arquivo nunca é salvo (nem em disco, nem no Git: `*.pdf` está no .gitignore). Sem duplicar: a renda do extrato vale mais que a digitada; o pagamento da fatura no extrato não é gasto; o mesmo documento em dois formatos conta uma vez. A categoria que o banco põe no extrato nunca é usada para classificar, só para comparar.
- **Aprendizado contínuo (decisão do maestro):** só o par loja → categoria que o usuário confirma (aba Perguntas, com usuários de simulação ou no modo Minha fatura) vai para o aprendizado coletivo (Firebase, chave só nos Secrets do Streamlit), com a origem do voto e um código aleatório de sessão. Nunca guardar valores, datas, o arquivo, PIX para pessoas, renda, transferências ou CPF/CNPJ (o documento só decide "pessoa ou loja" e é apagado na leitura). Uma loja vale para todos com 2 confirmações de sessões diferentes e entra no re-treino do modelo.
- **Categorias (decisão do maestro, 24/11/2026):** além da lista da Sessão 1, existem Veículos (essencial: combustível, manutenção, seguro, IPVA, licenciamento, multas; acessórios e limpeza do carro são Compras), Transferência familiar, Impostos e contribuições, Tarifas e juros bancários (prioritários), Saque em dinheiro (discricionário; desde 25/11/2026 "Jogos" faz parte de Lazer, e votos antigos em jogos valem como lazer) e Guardar/investir (fora dos gastos, soma na reserva). "Impostos" não é categoria única: IPTU é moradia, IPVA é veículo, o resto é imposto. Transporte é ônibus, metrô e aplicativo. Transferência familiar nunca vai para o aprendizado coletivo. Parcela ("5/18", "PARCELA 5 DE 18" ou coluna Parcela) conta no bloco das parcelas; se a categoria for desconhecida, o sistema pergunta do que é a compra.
- **Código:** simples e legível, funções pequenas, sem otimização prematura.

## Regras de produto (não negociáveis)

- Nunca rotular o usuário ("gastador", "irresponsável"). Use linguagem factual e neutra.
- Nunca recomendar ativos financeiros específicos.
- Nunca falar de impostos sobre os ganhos nem acusar irregularidade fiscal (decisão do maestro, 25/11/2026: o SIDOF não pergunta sobre entradas; todo dinheiro que entra é renda, menos transferências próprias, aplicações, rendimentos, reembolsos, empréstimos e ajuda da família, reconhecidos sozinhos). Dos ganhos, só importa se a renda é fixa ou variável.
- Toda classificação tem nível de confiança. Confiança baixa significa perguntar ao usuário, não inventar (vale para gastos; sobre ganhos o sistema não pergunta).
- Todo alerta deve ter uma explicação curta de por que foi gerado.

## Comandos úteis

Rodar a partir da pasta do projeto (Windows):

- Instalar: `python -m venv .venv` e depois `.venv\Scripts\python -m pip install -r requirements.txt`
- Rodar: `.venv\Scripts\python -m financas`
- Testar: `.venv\Scripts\python -m pytest`
- Interface: `.venv\Scripts\streamlit run app.py`
- Documentos em PDF: `.venv\Scripts\python documentos\fontes\gerar_pdfs.py`
