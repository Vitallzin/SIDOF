# Sistema Inteligente de Diagnóstico e Orientação Financeira (protótipo)

Protótipo de estudo que analisa o histórico de transações de um usuário, classifica as movimentações, identifica renda, parcelas e anomalias, e gera diagnóstico, alertas e metas.

> **Todos os dados são fictícios.** Nenhum dado financeiro real é usado neste projeto.

Detalhes: [proposta original](docs/01_proposta_original.md) e [plano do protótipo](docs/02_plano_do_prototipo.md).

## Como instalar (Windows)

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Como usar

```bash
.venv\Scripts\python -m financas
```

Hoje esse comando gera os dados sintéticos em `dados_gerados/` (semente fixa 42, sempre os mesmos dados):

| Arquivo | Conteúdo | Quem usa |
|---|---|---|
| `extrato.csv` | Transações como num extrato de banco | O sistema |
| `usuarios.csv` | Nome de cada usuário | O sistema |
| `verdade.csv` | Categoria real e anomalias plantadas | Só a avaliação |
| `usuarios_verdade.csv` | Perfil real de cada usuário | Só a avaliação |
| `classificacao_regras.csv` | Extrato limpo + categoria, confiança e explicação de cada transação | Fases seguintes |
| `relatorio_regras.txt` | Quanto as regras reconheceram, erros e casos não identificados | O maestro |
| `classificacao_hibrida_teste.csv` | Regras + modelo nas saídas dos usuários de teste | Avaliação |
| `relatorio_modelo.txt` | Comparação regras x modelo, por categoria e mês a mês | O maestro |
| `relatorio_teste_duro.txt` | O modelo testado em lojas que nunca viu | O maestro |
| `entradas_classificadas.csv` | Origem de cada entrada (salário, cliente, ajuda, transferência...) | Fases seguintes |
| `perfis_de_renda.csv` | Tipo de renda, média, menor mês, variação e renda de referência | Fases seguintes |
| `relatorio_renda.txt` | Acertos, perfis identificados e casos difíceis | O maestro |
| `parcelamentos.csv` | Cada compra parcelada ou dívida: total, parcela, quanto falta e até quando | Fases seguintes |
| `compromissos_futuros.csv` | Valor já comprometido com parcelas em cada um dos próximos 12 meses | Fases seguintes |
| `comprometimento_da_renda.csv` | % da renda de referência comprometida no próximo mês | Fases seguintes |
| `relatorio_parcelas.txt` | Resumo de parcelas por usuário | O maestro |
| `indicadores.csv` | Renda, gastos por bloco, sobra, evolução e comprometimento de cada usuário | Fases seguintes |
| `relatorio_diagnostico.txt` | Diagnóstico em texto de cada usuário e precisão do diagnóstico | O maestro |
| `relatorio_metas.txt` | Meta exemplo (R$ 4.000 em 10 meses) acompanhada para cada usuário | O maestro |
| `alertas.csv` | Alertas de anomalia dos dois métodos, com explicação | Fases seguintes |
| `relatorio_anomalias.txt` | Precisão e revocação por tipo, exemplos detectados e perdidos | O maestro |
| `relatorio_sistema.txt` | O sistema em uso (modelo treinado numa base separada) nos usuários atendidos | O maestro |
| `fatura_exemplo.pdf` | Uma fatura fictícia gerada pelo sistema | Testar a importação |
| `relatorio_faturas.txt` | Leitura e classificação das faturas fictícias em PDF | O maestro |

O comando leva cerca de 1 minuto e meio, porque o modelo é treinado várias vezes no experimento.

## Interface

```bash
.venv\Scripts\streamlit run app.py
```

Abre no navegador (http://localhost:8501). Na barra lateral: escolha o usuário e o "mês atual",
que simula os meses chegando. Abas: diagnóstico, notificações do mês, perguntas (suas respostas
valem para pagamentos parecidos), parcelas e metas. A interface usa só o sistema em uso
(`financas/sistema.py`), que nunca lê a verdade dos usuários.

### Importar fatura em PDF

Na aba **Importar fatura** é possível enviar uma fatura de cartão em PDF (fictícia ou real) no formato
comum "data, descrição, parcela, valor". O sistema lê as compras, classifica cada uma e pergunta o que
não souber. O botão "Fatura de exemplo" gera uma fatura fictícia para testar.

- O arquivo é lido **só em memória**: não é salvo, não vai para o Git e não é usado para treinar.
- Faturas escaneadas (imagem) ou com layout muito diferente não são lidas.
- Internamente, o sistema gera uma fatura fictícia de cada usuário em cada mês, lê de volta e confere
  com a verdade (`relatorio_faturas.txt`). O modelo também treina com as compras como aparecem nessas faturas.

## Como rodar os testes

```bash
.venv\Scripts\python -m pytest
```

## Estrutura

| Pasta | O que tem |
|---|---|
| `financas/` | Código do sistema (`sistema.py` é o sistema em uso; os outros módulos são as fases) |
| `tests/` | Testes automáticos (pytest) |
| `dados_gerados/` | CSVs criados pelo gerador (não vão para o repositório) |
| `docs/` | Proposta e plano |

## Situação

- [x] Fase 0: preparação do ambiente
- [x] Fase 1: gerador de dados sintéticos
- [x] Fase 2: normalização e classificação por regras
- [x] Fase 3: modelo de classificação
- [x] Fase 4: renda e transferências internas (inclui troca de emprego e salário sem a palavra "salário")
- [x] Fase 5: parcelas e compromissos futuros
- [x] Fase 6: indicadores e diagnóstico
- [x] Fase 7: metas financeiras
- [x] Fase 8: anomalias
- [x] Fase 9: interface e monitoramento simulado (aguardando aprovação)
- [ ] Fase 10: avaliação e documentação
