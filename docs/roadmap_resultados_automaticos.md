# Roadmap: Resultados Automáticos via API

## Por que isso importa

Atualmente o admin insere resultados manualmente após cada jogo. Isso cria dois problemas:

1. **Dependência humana** — se o admin esquecer ou demorar, o ranking fica desatualizado para todos.
2. **Risco de manipulação** — o admin pode inserir um placar errado (mesmo que sem má-fé) e distorcer a pontuação de toda a turma.

Com automação via API, a fonte de verdade passa a ser um serviço externo auditável. O admin continua necessário apenas para os jogos do mata-mata, que a API pode não ter com antecedência suficiente.

---

## API recomendada: football-data.org

| Item | Detalhe |
|------|---------|
| **URL base** | `https://api.football-data.org/v4` |
| **Plano free** | Cobre Copa do Mundo (`competitionCode = WC`) |
| **Delay no plano free** | ~1 minuto após o jogo terminar |
| **Endpoint de partidas** | `GET /v4/competitions/WC/matches` |
| **Autenticação** | Header `X-Auth-Token: SUA_CHAVE` |
| **Registro** | https://www.football-data.org/client/register |

O plano free é suficiente para o bolão: a Copa tem 104 jogos, e um script que roda uma vez por dia consome bem dentro dos limites.

---

## Como funcionaria na prática

```
[Cron job / botão manual no app]
         │
         ▼
buscar_resultados_copa()
  → GET /v4/competitions/WC/matches?status=FINISHED
         │
         ▼
para cada jogo terminado:
  mapear ID da API → jogo_id do bolão
  se resultado ainda não inserido:
    salvar na aba "resultados" do Google Sheets
         │
         ▼
app recalcula ranking no próximo load
(sem intervenção do admin)
```

O script pode rodar:
- **Manualmente** (botão "Atualizar resultados" visível apenas para o admin)
- **Automaticamente** via GitHub Actions com `schedule: cron` (roda de hora em hora durante os dias de jogo)

---

## Exemplo de código — esqueleto do fetch

```python
import requests

API_KEY = "sua_chave_aqui"   # usar st.secrets["FOOTBALL_DATA_KEY"] no app

def buscar_resultados_copa() -> list[dict]:
    """Retorna lista de partidas FINISHED da Copa 2026."""
    url = "https://api.football-data.org/v4/competitions/WC/matches"
    resp = requests.get(
        url,
        headers={"X-Auth-Token": API_KEY},
        params={"status": "FINISHED"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("matches", [])


def atualizar_resultados(matches: list[dict], save_fn) -> int:
    """
    Para cada partida terminada, chama save_fn(jogo_id, gols_home, gols_away).
    Retorna o número de novos resultados gravados.

    save_fn é a função save_resultado() do persistence.py — o módulo de persistência
    não precisa saber de onde veio o dado.
    """
    inseridos = 0
    for m in matches:
        score = m.get("score", {}).get("fullTime", {})
        home_goals = score.get("home")
        away_goals = score.get("away")
        api_id     = m["id"]

        if home_goals is None or away_goals is None:
            continue   # jogo sem placar definido (ex: pênaltis ainda não processados)

        jogo_id = _mapear_api_id_para_bolao(api_id)
        if jogo_id is None:
            continue   # jogo da API não está no bolão (ex: qualificatórias)

        save_fn(jogo_id, int(home_goals), int(away_goals))
        inseridos += 1

    return inseridos


def _mapear_api_id_para_bolao(api_id: int) -> int | None:
    """
    Tabela de mapeamento entre o ID da API (ex: 417789) e o jogo_id do bolão
    (sequencial, 0-indexed, derivado do CSV de jogos).

    Esta tabela precisa ser construída uma vez manualmente ou via script auxiliar
    que compare times + datas entre as duas fontes.
    """
    MAPA = {
        # api_id: jogo_id_bolao
        # 417789: 0,
        # 417790: 1,
        # ...preencher após o início da Copa...
    }
    return MAPA.get(api_id)
```

---

## O desafio do mapeamento de IDs

A API retorna IDs próprios (ex: `417789`). O bolão usa um índice sequencial derivado do CSV (`0`, `1`, `2`...). Para casar os dois é necessário uma etapa de mapeamento.

**Abordagem recomendada:**
1. No primeiro dia da Copa, chamar `GET /v4/competitions/WC/matches` e listar todos os jogos com seus `id`, `homeTeam.name`, `awayTeam.name` e `utcDate`.
2. Cruzar com o CSV do bolão por `(home_team, away_team, data)`.
3. Gerar o dicionário `MAPA` acima.

Esse trabalho é feito uma única vez antes do início da fase de grupos.

---

## Por que isso elimina a manipulação de resultados

Com a API como fonte de verdade:

- O admin **não consegue mais inserir resultados** da fase de grupos — o script só aceita placares finalizados pela API.
- O admin mantém acesso **apenas para jogos do mata-mata** que a API não antecipa (ex: inserir "Brasil × Argentina — Quartas de Final" antes da API ter o confronto definido).
- Todo histórico de inserções fica auditável na aba `resultados` do Google Sheets, com timestamp.

---

## Próximos passos para implementar

- [ ] Registrar conta gratuita em football-data.org e obter chave de API
- [ ] Adicionar `FOOTBALL_DATA_KEY` em `st.secrets` (local e Streamlit Cloud)
- [ ] Construir o dicionário de mapeamento de IDs no início da Copa
- [ ] Implementar botão "Sincronizar resultados" no painel admin (fase 1)
- [ ] Opcionalmente, configurar GitHub Actions para rodar o sync automaticamente (fase 2)
