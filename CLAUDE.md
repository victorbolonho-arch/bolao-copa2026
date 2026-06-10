# CLAUDE.md

Arquivo de contexto para o Claude Code. Leia antes de qualquer ação neste repositório.

---

## 1. Sobre o projeto

Construção de um modelo de Machine Learning para prever resultados das partidas da **Copa do Mundo FIFA 2026** (EUA / México / Canadá — 11/jun a 19/jul de 2026).

**Uso final:** participação em bolão entre amigos.

**Saída mínima esperada:** classificação por partida em `{vitória time A, empate, vitória time B}`.
**Saída ideal:** placar exato (gols time A, gols time B), via dois regressores Poisson independentes.

---

## 2. Modo de operação obrigatório do Claude Code

> **Esta seção é a mais importante do arquivo. Não ignorar.**

O usuário está construindo este projeto também para **aprender ML na prática**. Portanto:

- **Ensine enquanto constrói.** Antes de gerar qualquer bloco de código não-trivial, explique em 2-4 linhas:
  1. *O que* o código vai fazer
  2. *Por que* essa é a abordagem escolhida
  3. *Qual alternativa* foi descartada e por quê (quando houver decisão de design)
- **Explique conceitos na primeira aparição**, mesmo os "básicos": train/test split, cross-validation, one-hot encoding, leakage, regularização, AUC, log-loss, Poisson regression, calibração de probabilidades, etc. Assuma que o usuário entende programação Python mas é iniciante em ML.
- **Aponte armadilhas antes de cair nelas.** Especialmente: data leakage temporal, target encoding incorreto, validação aleatória em série temporal, classes desbalanceadas, overfitting em datasets pequenos.
- **Comente as bibliotecas na primeira vez.** Quando importar `pandas`, `sklearn`, `xgboost`, etc., explique brevemente o papel da lib. Quando usar um método novo (`.groupby`, `cross_val_score`, `StratifiedKFold`), explique o que ele faz.
- **Mostre o "porquê do passo", não só o passo.** "Vamos fazer EDA" é fraco. "Vamos verificar a distribuição de gols porque modelos Poisson assumem média ≈ variância — se isso não bater, precisamos de Negative Binomial" é o que se espera.
- **Não pule etapas "óbvias".** Se é óbvio para um ML engineer mas não para iniciante, explique.

### Estilo de comunicação

- Objetivo. Sem elogios. Sem "ótima pergunta!", "excelente ideia!", etc.
- Se o usuário errar, apontar o erro diretamente.
- Se o usuário acertar, seguir adiante sem cerimônia.
- Realista quanto a expectativas: previsão de futebol tem teto de acurácia baixo (~55% para 3 classes). Não vender ilusão.

---

## 3. Stack técnica

- **Python** 3.11+
- **Manipulação de dados:** `pandas`, `numpy`, `polars` (opcional para datasets maiores)
- **ML:** `scikit-learn`, `xgboost` ou `lightgbm`
- **Estatística:** `statsmodels` (para Poisson/Negative Binomial)
- **Visualização:** `matplotlib`, `seaborn`
- **Scraping (quando necessário):** `requests`, `beautifulsoup4`, `httpx`
- **Ambiente:** `uv` ou `poetry` para dependências; Jupyter para EDA, `.py` para pipeline final.

---

## 4. Estrutura do repositório

```
worldcup-2026-ml/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── data/
│   ├── raw/             # CSVs originais (não modificar)
│   ├── interim/         # Joins e transformações parciais
│   └── processed/       # Dataset final pronto pra treinar
├── notebooks/           # EDA e experimentação (numerados: 01_, 02_...)
├── src/
│   ├── ingest/          # Download, scraping, carregamento
│   ├── features/        # Feature engineering
│   ├── models/          # Treino e avaliação
│   └── predict/         # Previsões finais para a Copa 2026
├── models/              # Modelos serializados (.pkl, .joblib)
└── tests/
```

---

## 5. Fontes de dados já mapeadas

| Dado | Fonte | Status |
|---|---|---|
| Resultados de partidas internacionais (1872–hoje, ~50k jogos) | Kaggle: `martj42/international-football-results-from-1872-to-2017` ou `patateriedata/all-international-football-results` | Pronto, baixar manualmente |
| Ranking FIFA histórico (1992–presente) | Kaggle: `cashncarry/fifaworldranking` + scraper `cnc8/fifa-world-ranking` (GitHub) | Precisa update p/ 2025-2026 |
| Elo ratings de seleções | `eloratings.net` (scraping) | Sem API oficial |
| Dataset estruturado de Copas do Mundo 1930–2022 | GitHub: `jfjelstul/worldcup` | Pronto |
| Valores de mercado / convocações | Transfermarkt (scraping opcional) | Fase 2 |

---

## 6. Features planejadas (esquema do dataset final)

**Identificação:** `data`, `time_A`, `time_B`, `mandante`, `torneio`, `fase`, `cidade`, `pais_sede`, `campo_neutro`

**Força (no momento da partida — atenção a leakage):**
- `fifa_rank_A`, `fifa_rank_B`
- `elo_A`, `elo_B`, `elo_diff`
- `valor_mercado_elenco_A`, `valor_mercado_elenco_B` (fase 2)

**Forma recente (rolling windows):**
- Últimos 5 e 10 jogos: vitórias, empates, derrotas, gols feitos/sofridos (médias)

**Head-to-head:**
- Últimos 5 confrontos diretos (V/E/D, saldo de gols)

**Contexto:**
- Dias desde último jogo, distância viajada, confederação dos times, indicador de altitude

**Target:**
- `resultado` ∈ {A, E, B} para classificação
- `gols_A`, `gols_B` para regressão Poisson

---

## 7. Cuidados críticos — repetir antes de cada etapa

1. **Data leakage temporal.** Toda feature deve refletir informação disponível **antes** da partida. Ranking FIFA usado é o da publicação imediatamente anterior à data do jogo, nunca o atual.
2. **Validação temporal, não aleatória.** Train/test split deve ser por data: treina em jogos antigos, valida em recentes. Nunca `train_test_split` aleatório em série temporal.
3. **Acurácia esperada realista.** Estado da arte para classificação 3-classes de futebol fica entre **50% e 58%**. Modelo com >65% provavelmente tem leakage.
4. **Amistosos vs. competitivos.** Times levam amistosos menos a sério. Considerar ponderar amostras por tipo de torneio.
5. **Cold-start de seleções.** Times com poucos jogos têm Elo/ranking instável. Verificar antes de incluir.

---

## 8. Roadmap em fases

| Fase | Entrega | Critério de saída |
|---|---|---|
| 0 | Setup do repositório, ambiente, dependências | `uv sync` ou `poetry install` funciona |
| 1 | Ingestão dos dados de partidas + EDA | Notebook `01_eda.ipynb` com distribuição de resultados, gols, torneios |
| 2 | Merge com ranking FIFA + Elo | `data/interim/matches_with_strength.parquet` |
| 3 | Feature engineering (rolling, H2H, contexto) | `data/processed/training_set.parquet` |
| 4 | Baseline: regressão logística | Métrica de referência: log-loss e accuracy no holdout |
| 5 | Modelo principal: XGBoost / LightGBM com tuning | Bater o baseline; análise de feature importance |
| 6 | Modelo de gols: dois Poisson regressores | Distribuição de placares prevista vs. real |
| 7 | Calibração de probabilidades (Platt / isotonic) | Reliability diagram |
| 8 | Predição da Copa 2026 | Tabela de previsões para todos os 104 jogos |

---

## 9. Convenções

- **Notebooks** prefixados com número de ordem: `01_eda.ipynb`, `02_join_rankings.ipynb`, etc.
- **Datasets versionados** por data no nome: `matches_2026-05-05.parquet`.
- **Type hints** em funções de `src/`.
- **Docstrings** estilo Google ou NumPy nos módulos.
- **Random seed fixa** (`SEED = 42`) em todo experimento, para reprodutibilidade.

---

## 10. O que NÃO fazer

- Não usar deep learning. Dataset é pequeno demais; gradient boosting domina nesse regime.
- Não confiar cegamente em `print(df.head())`. Validar `shape`, `dtypes`, `isna().sum()`, distribuições.
- Não pular EDA "porque já entendi os dados".
- Não treinar antes de validar ausência de leakage.
- Não otimizar hiperparâmetros antes de ter um baseline funcionando.
- Não criar features sem hipótese clara do porquê elas ajudariam.

---

## 11. Lembrete final para o Claude Code

Toda mensagem que envolver código novo deve seguir o padrão:

1. **Explicação curta** do que vai fazer e por quê
2. **Conceito ML novo** introduzido nessa etapa (se houver), explicado em 2-3 frases
3. **Código** comentado nos pontos não-óbvios
4. **O que esperar como output** e como interpretar
5. **Próximo passo** sugerido

Se em algum momento você (Claude Code) for pular o passo de explicação, está descumprindo o contrato deste arquivo.
