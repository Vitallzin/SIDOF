# Decisões da Fase 8 tomadas ANTES de ver os novos resultados

Registro feito para que os limites não sejam ajustados olhando os números de teste.

## 1. Limite do detector de pico

- **Antes:** média + 2 desvios padrão, a partir de 2 meses de histórico.
- **Agora:** média + **3 desvios padrão**, a partir de **3 meses de histórico**.
- **Motivo (princípio, não resultado):** são cerca de 600 verificações de pico (12 usuários × ~15
  categorias × ~3 meses). Com 2 desvios, ~5% das verificações normais passam do limite por
  acaso, ou seja, ~30 alarmes falsos esperados. Com 3 desvios, ~0,3%, ou seja, ~2 esperados.
  Com 3 meses de histórico, o desvio padrão é estimado com pelo menos 3 valores.
- Isso altera a decisão do plano ("2 desvios padrão, ajustável"), com aprovação do maestro.
- Os outros limites (duplicada, loja nova, frequência, IsolationForest) **não mudam**.

## 2. Anomalias não previstas

O gerador passa a plantar 3 tipos de anomalia para os quais **nenhum detector foi pensado**.
Os detectores **não serão alterados** depois de ver o resultado nesses tipos.

| Tipo | O que é |
|---|---|
| `conta_fixa_disparada` | Uma conta mensal (energia, água ou telefone) vem 2,5 a 3,5 vezes maior em um mês |
| `pix_alto_desconhecido` | Um PIX para uma pessoa nunca vista, de 30% a 60% da renda base |
| `cobranca_recorrente_nova` | Uma nova cobrança mensal pequena no cartão a partir de abril (ex.: assinatura não reconhecida) |

Cada usuário recebe 1 ou 2 desses tipos, sempre entre abril e junho. O relatório mostra a revocação
dos tipos previstos e dos não previstos separadamente.
