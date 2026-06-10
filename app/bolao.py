"""
Bolão Copa do Mundo 2026 — Aplicação Web
Camada 2: persistência via Google Sheets (fallback automático para CSV local)

Rodar: streamlit run app/bolao.py
"""
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
from persistence import (
    load_palpites,
    save_palpites_batch,
    load_resultados,
    save_resultado,
    backend_label,
)

# ─── Configuração da página ────────────────────────────────────────────────────
# st.set_page_config() DEVE ser o primeiro comando Streamlit do script.
st.set_page_config(
    page_title="Bolão Copa 2026",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Caminhos (apenas o que o bolao.py ainda usa diretamente) ─────────────────
ROOT      = Path(__file__).resolve().parent.parent
DATA      = ROOT / "data"
GAMES_CSV = DATA / "processed" / "palpites_bolao_2026.csv"
EXTRAS_CSV = DATA / "jogos_extras.csv"   # jogos do mata-mata (admin adiciona)

# ─── Regras de pontuação 365Scores ─────────────────────────────────────────────
# Tupla: (pontos_resultado_certo, pontos_placar_exato)
PONTUACAO: dict[str, tuple[int, int]] = {
    "Fase de Grupos": (1,  3),
    "16-avos":        (2,  5),
    "Oitavas":        (2,  5),
    "Quartas":        (4,  8),
    "Semifinal":      (5, 10),
    "Terceiro lugar": (5, 10),
    "Final":          (8, 15),
}

FASES_ORDEM = [
    "Fase de Grupos", "16-avos", "Oitavas",
    "Quartas", "Semifinal", "Terceiro lugar", "Final",
]

# ─── Tradução inglês → português ──────────────────────────────────────────────
TRADUZ: dict[str, str] = {
    "Brazil":                  "Brasil",
    "France":                  "França",
    "Germany":                 "Alemanha",
    "Spain":                   "Espanha",
    "England":                 "Inglaterra",
    "Portugal":                "Portugal",
    "Netherlands":             "Holanda",
    "Belgium":                 "Bélgica",
    "Italy":                   "Itália",
    "United States":           "EUA",
    "Mexico":                  "México",
    "Argentina":               "Argentina",
    "Uruguay":                 "Uruguai",
    "Colombia":                "Colômbia",
    "Ecuador":                 "Equador",
    "Paraguay":                "Paraguai",
    "Canada":                  "Canadá",
    "Panama":                  "Panamá",
    "Haiti":                   "Haiti",
    "Japan":                   "Japão",
    "South Korea":             "Coreia do Sul",
    "Australia":               "Austrália",
    "New Zealand":             "Nova Zelândia",
    "Saudi Arabia":            "Arábia Saudita",
    "Iran":                    "Irã",
    "Iraq":                    "Iraque",
    "Jordan":                  "Jordânia",
    "Uzbekistan":              "Uzbequistão",
    "Qatar":                   "Catar",
    "Morocco":                 "Marrocos",
    "Senegal":                 "Senegal",
    "Egypt":                   "Egito",
    "Algeria":                 "Argélia",
    "Tunisia":                 "Tunísia",
    "Ghana":                   "Gana",
    "Ivory Coast":             "Costa do Marfim",
    "South Africa":            "África do Sul",
    "Cape Verde":              "Cabo Verde",
    "DR Congo":                "R.D. Congo",
    "Switzerland":             "Suíça",
    "Austria":                 "Áustria",
    "Croatia":                 "Croácia",
    "Sweden":                  "Suécia",
    "Norway":                  "Noruega",
    "Scotland":                "Escócia",
    "Turkey":                  "Turquia",
    "Czech Republic":          "Rep. Tcheca",
    "Bosnia and Herzegovina":  "Bósnia e Hez.",
    "Curaçao":                 "Curaçao",
}


# ─── Funções utilitárias ────────────────────────────────────────────────────────

def tn(name: str) -> str:
    """Traduz nome do time; mantém original se não encontrar tradução."""
    return TRADUZ.get(name, name)


def parse_placar(s) -> tuple[int, int]:
    """
    Extrai gols do formato '2-0(15%)'.
    Retorna (0, 0) se a string estiver ausente ou malformada.
    """
    try:
        score = str(s).split("(")[0].strip()
        h, a = score.split("-")
        return int(h.strip()), int(a.strip())
    except Exception:
        return 0, 0


def resultado_de(h: int, a: int) -> str:
    """Converte placar em resultado: 'H' (casa vence), 'A' (fora vence), 'D' (empate)."""
    if h > a:
        return "H"
    if h < a:
        return "A"
    return "D"


def label_resultado(r: str, home: str, away: str) -> str:
    """Converte código de resultado em frase legível com nomes dos times."""
    if r == "H":
        return f"{tn(home)} vence"
    if r == "A":
        return f"{tn(away)} vence"
    return "Empate"


def format_date(date_str: str) -> str:
    """Formata '2026-06-11' → 'Qui, 11/jun'."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        dias  = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        meses = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"]
        return f"{dias[d.weekday()]}, {d.day}/{meses[d.month - 1]}"
    except Exception:
        return date_str


def badge_confianca(c: float) -> str:
    """Ícone visual da confiança do modelo."""
    if c >= 0.65:
        return "🟢"
    if c >= 0.45:
        return "🟡"
    return "🔴"


# ─── Dados dos jogos (leitura do CSV estático — não muda entre sessões) ────────

@st.cache_data(ttl=3600)
def load_games() -> pd.DataFrame:
    """
    Carrega os jogos da Copa 2026 (fase de grupos + extras do mata-mata).
    @st.cache_data com TTL=1h: o CSV de jogos não muda em runtime.
    """
    df = pd.read_csv(GAMES_CSV)
    df["jogo_id"] = range(len(df))
    if EXTRAS_CSV.exists():
        extras = pd.read_csv(EXTRAS_CSV)
        extras["jogo_id"] = range(len(df), len(df) + len(extras))
        df = pd.concat([df, extras], ignore_index=True)
    df["jogo_id"] = df["jogo_id"].astype(int)
    return df


# ─── Pontuação e ranking ────────────────────────────────────────────────────────

def calcular_pontos(ph: int, pa: int, rh: int, ra: int, fase: str) -> int:
    """
    Calcula pontos de um palpite dado o resultado real.
    Hierarquia: placar exato > resultado correto > zero.
    Placar exato já implica resultado correto, por isso retorna diretamente pts_pla.
    """
    pts_res, pts_pla = PONTUACAO.get(fase, (1, 3))
    if ph == rh and pa == ra:
        return pts_pla
    if resultado_de(ph, pa) == resultado_de(rh, ra):
        return pts_res
    return 0


def calcular_ranking() -> pd.DataFrame:
    """Cruza palpites × resultados reais e agrega pontos por usuário."""
    games      = load_games()
    palpites   = load_palpites()
    resultados = load_resultados()

    if palpites.empty or resultados.empty:
        return pd.DataFrame(
            columns=["posição", "usuário", "pontos", "placares exatos", "resultados certos"]
        )

    df = (
        palpites
        .merge(resultados, on="jogo_id", how="inner")   # só jogos com resultado real
        .merge(games[["jogo_id", "fase", "home_team", "away_team"]], on="jogo_id", how="left")
    )

    df["pontos"] = df.apply(
        lambda r: calcular_pontos(
            r.gols_home, r.gols_away,
            r.gols_home_real, r.gols_away_real,
            r.fase,
        ),
        axis=1,
    )
    df["placar_exato"]    = (df.gols_home == df.gols_home_real) & (df.gols_away == df.gols_away_real)
    df["resultado_certo"] = df.apply(
        lambda r: resultado_de(r.gols_home, r.gols_away)
               == resultado_de(r.gols_home_real, r.gols_away_real),
        axis=1,
    )

    ranking = (
        df.groupby("usuario")
        .agg(
            pontos            = ("pontos",          "sum"),
            placares_exatos   = ("placar_exato",    "sum"),
            resultados_certos = ("resultado_certo", "sum"),
        )
        .sort_values(["pontos", "placares_exatos"], ascending=False)
        .reset_index()
        .rename(columns={
            "usuario":          "usuário",
            "pontos":           "pontos",
            "placares_exatos":  "placares exatos",
            "resultados_certos":"resultados certos",
        })
    )
    ranking.insert(0, "posição", range(1, len(ranking) + 1))
    return ranking


def palpites_do_usuario_com_pontos(usuario: str) -> pd.DataFrame:
    """Retorna os palpites do usuário com pontuação já calculada (onde há resultado real)."""
    games      = load_games()
    palpites   = load_palpites()
    resultados = load_resultados()

    user_p = palpites[palpites["usuario"] == usuario].copy()
    if user_p.empty:
        return pd.DataFrame()

    df = user_p.merge(games[["jogo_id","data","home_team","away_team","fase"]], on="jogo_id", how="left")
    df = df.merge(resultados, on="jogo_id", how="left")

    df["resultado_real"] = df.apply(
        lambda r: resultado_de(int(r.gols_home_real), int(r.gols_away_real))
        if pd.notna(r.gols_home_real) else "—",
        axis=1,
    )
    df["pontos"] = df.apply(
        lambda r: calcular_pontos(
            int(r.gols_home), int(r.gols_away),
            int(r.gols_home_real), int(r.gols_away_real), r.fase
        ) if pd.notna(r.gols_home_real) else "—",
        axis=1,
    )
    return df.sort_values("data").reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════════
# UI — SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.title("⚽ Bolão Copa 2026")
    st.caption("Copa do Mundo FIFA 2026 · 11/jun – 19/jul")
    st.divider()

    # Identificação por nome (sem login/senha — propositalmente simples)
    st.subheader("Quem é você?")

    # st.session_state persiste entre re-renders da mesma sessão de browser.
    # Usamos um form para que o "Entrar" só dispare ao clicar, não a cada tecla.
    with st.form("form_login", clear_on_submit=False):
        nome_input = st.text_input(
            "Seu nome:",
            value=st.session_state.get("usuario", ""),
            placeholder="Ex: João Silva",
        )
        entrar = st.form_submit_button("Entrar ▶", type="primary", use_container_width=True)

    if entrar:
        nome = nome_input.strip()
        if nome:
            if nome != st.session_state.get("usuario"):
                # Limpar inputs do usuário anterior do session_state
                for k in list(st.session_state.keys()):
                    if k.startswith(("h_", "a_")):
                        del st.session_state[k]
                st.session_state["loaded_for"] = None
            st.session_state["usuario"] = nome
            st.rerun()
        else:
            st.warning("Digite um nome para continuar.")

    usuario = st.session_state.get("usuario", "")
    if usuario:
        st.success(f"Olá, **{usuario}**! 👋")

        # Mostrar progresso de palpites salvos
        palpites_salvos = load_palpites()
        n_salvos = len(palpites_salvos[palpites_salvos["usuario"] == usuario])
        n_total  = len(load_games())
        st.progress(n_salvos / n_total if n_total > 0 else 0,
                    text=f"{n_salvos}/{n_total} palpites salvos")

    st.divider()

    # Indicador de backend ativo
    st.caption(f"Backend: **{backend_label()}**")

    # Modo administrador — sem senha (contexto de amigos, prazo apertado)
    admin = st.toggle("🔧 Modo administrador")
    if admin:
        st.caption("Use com responsabilidade: este modo insere resultados reais e afeta o ranking de todos.")


# ══════════════════════════════════════════════════════════════════════════════════
# TELA DE BOAS-VINDAS (usuário não identificado)
# ══════════════════════════════════════════════════════════════════════════════════

if not usuario:
    st.title("⚽ Bolão Copa do Mundo 2026")
    st.markdown("""
    ### Como funciona

    1. **Digite seu nome** na barra lateral e clique em **Entrar**.
    2. Para cada jogo da fase de grupos, você vê a **sugestão do modelo de IA** (probabilidades e placar provável).
    3. **Ajuste ou confirme** o palpite e clique em **Salvar**.
    4. Conforme os resultados saírem, o **ranking** é atualizado automaticamente.

    ---
    #### Tabela de pontuação (regras 365Scores)

    | Fase | Resultado certo | Placar exato |
    |------|:-:|:-:|
    | Fase de Grupos | 1 pt | 3 pts |
    | 16-avos / Oitavas | 2 pts | 5 pts |
    | Quartas de final | 4 pts | 8 pts |
    | Semifinal / 3º lugar | 5 pts | 10 pts |
    | Final | 8 pts | 15 pts |

    ---
    *Powered by LightGBM + Regressão de Poisson · Modelo treinado com jogos de 1872–2026*
    """)
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════════
# APP PRINCIPAL (usuário identificado)
# ══════════════════════════════════════════════════════════════════════════════════

games = load_games()

# Inicializar session_state com os palpites do usuário (uma vez por usuário).
# O padrão quando não há palpite salvo é a sugestão do modelo.
if st.session_state.get("loaded_for") != usuario:
    palpites_existentes = load_palpites()
    user_bets = palpites_existentes[palpites_existentes["usuario"] == usuario]
    bets_by_id = {
        int(r["jogo_id"]): (int(r["gols_home"]), int(r["gols_away"]))
        for _, r in user_bets.iterrows()
    }
    for _, game in games.iterrows():
        jid      = int(game["jogo_id"])
        key_h    = f"h_{jid}"
        key_a    = f"a_{jid}"
        # Só inicializa se a key não existir — preserva edições feitas na sessão atual
        if key_h not in st.session_state:
            if jid in bets_by_id:
                st.session_state[key_h] = bets_by_id[jid][0]
                st.session_state[key_a] = bets_by_id[jid][1]
            else:
                dh, da = parse_placar(game.get("placar_mais_provavel", "0-0"))
                st.session_state[key_h] = dh
                st.session_state[key_a] = da
    st.session_state["loaded_for"] = usuario

# Carregar dados necessários nas tabs
palpites_df  = load_palpites()
resultados_df = load_resultados()
user_bets_idx = set(
    palpites_df.loc[palpites_df["usuario"] == usuario, "jogo_id"].tolist()
)

tab_palpites, tab_ranking, tab_meus = st.tabs([
    "⚽ Palpites",
    "🏆 Ranking",
    f"📋 Meus palpites ({usuario})",
])


# ──────────────────────────────────────────────────────────────────────────────
# TAB 1 — PALPITES
# ──────────────────────────────────────────────────────────────────────────────

with tab_palpites:
    st.header("⚽ Palpites — Fase de Grupos")

    n_salvos = len(user_bets_idx)
    n_total  = len(games)

    col_info1, col_info2, col_info3 = st.columns(3)
    col_info1.metric("Jogos na fase de grupos", n_total)
    col_info2.metric("Seus palpites salvos", n_salvos)
    col_info3.metric("Faltam palpitar", n_total - n_salvos)

    st.info(
        "💡 **Como usar:** O palpite já vem pré-preenchido com a sugestão do modelo. "
        "Altere se discordar e clique em **Salvar todos os palpites** quando terminar. "
        "Você pode salvar e voltar depois — seus palpites ficam guardados.",
        icon=None,
    )

    # Botão salvar — lê todos os number_inputs do session_state
    if st.button("💾 Salvar todos os palpites", type="primary", use_container_width=False):
        palpites_para_salvar = {
            int(game["jogo_id"]): (
                int(st.session_state.get(f"h_{int(game['jogo_id'])}", 0)),
                int(st.session_state.get(f"a_{int(game['jogo_id'])}", 0)),
            )
            for _, game in games.iterrows()
        }
        save_palpites_batch(usuario, palpites_para_salvar)
        st.success(f"✅ {len(palpites_para_salvar)} palpites salvos com sucesso!")
        st.balloons()
        # Marcar como precisando recarregar no próximo render para atualizar badge de status
        st.session_state["loaded_for"] = None
        st.rerun()

    st.divider()

    # Nota sobre o mata-mata
    st.caption(
        "⚠️ **Esta versão mostra apenas os 72 jogos da fase de grupos.** "
        "Os jogos do mata-mata serão adicionados conforme os grupos se encerram "
        "(o admin pode inserir via modo administrador)."
    )

    # ── Jogos agrupados por data ──────────────────────────────────────────────
    for date_str, date_games in games.groupby("data", sort=True):
        n_dia     = len(date_games)
        n_salvos_dia = len([g for _, g in date_games.iterrows()
                           if int(g["jogo_id"]) in user_bets_idx])
        label_exp = (
            f"📅 **{format_date(date_str)}** — {n_dia} jogos "
            f"({'✅ ' + str(n_salvos_dia) + '/' + str(n_dia) if n_salvos_dia == n_dia else str(n_salvos_dia) + '/' + str(n_dia) + ' salvos'})"
        )
        # Expander aberto por padrão — usuário pode colapsar datas já resolvidas
        with st.expander(label_exp, expanded=True):
            for _, game in date_games.iterrows():
                jid   = int(game["jogo_id"])
                home  = game["home_team"]
                away  = game["away_team"]
                fase  = game.get("fase", "Fase de Grupos")
                obs   = str(game.get("observacao", "")) if pd.notna(game.get("observacao")) else ""

                # Verificar se já existe resultado real para este jogo
                result_real = resultados_df[resultados_df["jogo_id"] == jid]
                tem_resultado = len(result_real) > 0
                ja_salvo      = jid in user_bets_idx

                with st.container(border=True):
                    # Linha do cabeçalho do jogo
                    h_col1, h_col2 = st.columns([6, 2])
                    with h_col1:
                        st.markdown(
                            f"**{tn(home)}** &nbsp;×&nbsp; **{tn(away)}** "
                            f"&nbsp;·&nbsp; 📍 {game.get('cidade', '')}"
                        )
                    with h_col2:
                        status_txt = ""
                        if tem_resultado:
                            rh = int(result_real.iloc[0]["gols_home_real"])
                            ra = int(result_real.iloc[0]["gols_away_real"])
                            status_txt = f"🏁 Resultado: **{rh}–{ra}**"
                        elif ja_salvo:
                            status_txt = "✅ Palpite salvo"
                        else:
                            status_txt = "⏳ Não palpitado"
                        st.markdown(status_txt)

                    # Linha central: palpite do usuário | modelo
                    c_palpite, c_sep, c_modelo = st.columns([3, 0.2, 4])

                    with c_palpite:
                        st.markdown("**Seu palpite:**")
                        ci1, ci2, ci3 = st.columns([2, 0.5, 2])
                        with ci1:
                            st.number_input(
                                f"{tn(home)}",
                                min_value=0, max_value=20,
                                key=f"h_{jid}",
                                disabled=tem_resultado,
                            )
                        with ci2:
                            st.markdown(
                                "<p style='text-align:center;padding-top:1.7rem;font-size:1.2rem'>×</p>",
                                unsafe_allow_html=True,
                            )
                        with ci3:
                            st.number_input(
                                f"{tn(away)}",
                                min_value=0, max_value=20,
                                key=f"a_{jid}",
                                disabled=tem_resultado,
                            )

                    with c_sep:
                        st.markdown(
                            "<div style='border-left:1px solid #ddd;height:100%;margin:0 auto'></div>",
                            unsafe_allow_html=True,
                        )

                    with c_modelo:
                        # Sugestão do modelo — destaque visual principal
                        res_label  = label_resultado(
                            game.get("resultado_previsto", "H"), home, away
                        )
                        conf       = float(game.get("confianca", 0))
                        badge      = badge_confianca(conf)
                        p_home     = float(game.get("P_home", 0))
                        p_draw     = float(game.get("P_draw", 0))
                        p_away     = float(game.get("P_away", 0))
                        placar_pvl = str(game.get("placar_mais_provavel", "—"))
                        top3       = str(game.get("top3_placares", ""))

                        st.markdown(
                            f"🤖 **Modelo:** {badge} **{res_label}** ({conf:.0%})"
                        )
                        # Barra de probabilidades visual
                        st.markdown(
                            f"<div style='display:flex;gap:4px;margin:4px 0'>"
                            f"<div style='flex:{p_home:.2f};background:#2ecc71;height:8px;border-radius:4px 0 0 4px'></div>"
                            f"<div style='flex:{p_draw:.2f};background:#95a5a6;height:8px'></div>"
                            f"<div style='flex:{p_away:.2f};background:#e74c3c;height:8px;border-radius:0 4px 4px 0'></div>"
                            f"</div>"
                            f"<div style='display:flex;justify-content:space-between;font-size:0.75rem;color:#888'>"
                            f"<span>🟢 {tn(home)} {p_home:.0%}</span>"
                            f"<span>⚪ Empate {p_draw:.0%}</span>"
                            f"<span>🔴 {tn(away)} {p_away:.0%}</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                        st.caption(f"Placar mais provável: **{placar_pvl}** | Top 3: {top3}")

                        if obs:
                            st.caption(f"⚠️ {obs}")

                        # Pontos caso o usuário siga o modelo (informativo)
                        pts_res, pts_pla = PONTUACAO.get(fase, (1, 3))
                        st.caption(
                            f"💰 Pontos possíveis (fase de grupos): "
                            f"resultado certo = **{pts_res} pt** | placar exato = **{pts_pla} pts**"
                        )

    st.divider()
    # Segundo botão salvar no final da página (conveniência)
    if st.button("💾 Salvar todos os palpites", type="primary", key="salvar_bottom"):
        palpites_para_salvar = {
            int(game["jogo_id"]): (
                int(st.session_state.get(f"h_{int(game['jogo_id'])}", 0)),
                int(st.session_state.get(f"a_{int(game['jogo_id'])}", 0)),
            )
            for _, game in games.iterrows()
        }
        save_palpites_batch(usuario, palpites_para_salvar)
        st.success(f"✅ {len(palpites_para_salvar)} palpites salvos!")
        st.session_state["loaded_for"] = None
        st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# TAB 2 — RANKING
# ──────────────────────────────────────────────────────────────────────────────

with tab_ranking:
    st.header("🏆 Ranking")

    n_com_resultado = len(resultados_df)
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Jogos disputados", n_com_resultado)
    col_m2.metric("Jogos restantes", n_total - n_com_resultado)
    col_m3.metric("Participantes", palpites_df["usuario"].nunique())

    if n_com_resultado == 0:
        st.info(
            "🏁 O ranking aparecerá assim que o administrador inserir "
            "o resultado do primeiro jogo (11/jun)."
        )
    else:
        ranking = calcular_ranking()
        if ranking.empty:
            st.warning("Nenhum palpite registrado ainda.")
        else:
            # Destacar o usuário atual
            def highlight_user(row):
                if row["usuário"] == usuario:
                    return ["background-color: #fff3cd"] * len(row)
                return [""] * len(row)

            st.dataframe(
                ranking.style.apply(highlight_user, axis=1),
                use_container_width=True,
                hide_index=True,
            )

            # Detalhamento de pontos por fase
            st.subheader("Pontos máximos possíveis (referência)")
            max_pts = sum(
                pts_pla * len(games[games["fase"] == fase])
                for fase, (_, pts_pla) in PONTUACAO.items()
            )
            st.caption(
                f"Pontuação máxima teórica (todos placares exatos): **{max_pts} pts**. "
                "Na prática, acertar 35-45% dos resultados já é muito bom."
            )

            # Download do ranking
            st.download_button(
                "⬇️ Baixar ranking (CSV)",
                data=ranking.to_csv(index=False).encode("utf-8-sig"),
                file_name="ranking_bolao_2026.csv",
                mime="text/csv",
            )


# ──────────────────────────────────────────────────────────────────────────────
# TAB 3 — MEUS PALPITES
# ──────────────────────────────────────────────────────────────────────────────

with tab_meus:
    st.header(f"📋 Meus palpites — {usuario}")

    meus = palpites_do_usuario_com_pontos(usuario)
    if meus.empty:
        st.info("Você ainda não salvou nenhum palpite.")
    else:
        # Enriquecer com nomes traduzidos
        meus["mandante"] = meus["home_team"].map(tn)
        meus["visitante"] = meus["away_team"].map(tn)
        meus["meu_placar"] = meus.apply(
            lambda r: f"{int(r.gols_home)}–{int(r.gols_away)}", axis=1
        )
        meus["resultado_real_placar"] = meus.apply(
            lambda r: f"{int(r.gols_home_real)}–{int(r.gols_away_real)}"
            if pd.notna(r.gols_home_real) else "—",
            axis=1,
        )

        # Métricas pessoais
        pontos_num = [p for p in meus["pontos"] if p != "—"]
        total_pts  = sum(int(p) for p in pontos_num)
        n_exatos   = sum(
            1 for _, r in meus.iterrows()
            if pd.notna(r.gols_home_real)
            and int(r.gols_home) == int(r.gols_home_real)
            and int(r.gols_away) == int(r.gols_away_real)
        )

        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Palpites salvos", len(meus))
        mc2.metric("Jogos pontuados", len(pontos_num))
        mc3.metric("Meus pontos", total_pts)
        mc4.metric("Placares exatos", n_exatos)

        show_cols = ["data", "mandante", "visitante", "meu_placar",
                     "resultado_real_placar", "pontos"]
        labels    = {
            "data": "Data", "mandante": "Mandante", "visitante": "Visitante",
            "meu_placar": "Meu palpite", "resultado_real_placar": "Resultado real",
            "pontos": "Pontos",
        }
        st.dataframe(
            meus[show_cols].rename(columns=labels),
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "⬇️ Baixar meus palpites (CSV)",
            data=meus[show_cols].rename(columns=labels).to_csv(index=False).encode("utf-8-sig"),
            file_name=f"palpites_{usuario.replace(' ', '_')}.csv",
            mime="text/csv",
        )


# ══════════════════════════════════════════════════════════════════════════════════
# PAINEL DO ADMINISTRADOR (condicional)
# ══════════════════════════════════════════════════════════════════════════════════

if admin:
    st.divider()
    st.header("🔧 Administrador")

    adm_tab1, adm_tab2 = st.tabs(["Inserir resultados reais", "Adicionar jogo do mata-mata"])

    # ── Inserir resultados ────────────────────────────────────────────────────
    with adm_tab1:
        st.subheader("Inserir resultado real de um jogo")
        st.caption(
            "Use esta seção conforme os jogos acontecem. "
            "Inserir o resultado dispara o cálculo de pontos de todos os participantes."
        )

        # Montar opções: mostrar jogos sem resultado primeiro
        resultados_ids = set(resultados_df["jogo_id"].tolist())
        opcoes = []
        for _, g in games.sort_values("data").iterrows():
            jid_g   = int(g["jogo_id"])
            status  = "✅" if jid_g in resultados_ids else "⏳"
            label_g = (
                f"{status} {format_date(g['data'])} | "
                f"{tn(g['home_team'])} × {tn(g['away_team'])}"
            )
            opcoes.append((label_g, jid_g))

        sel_label = st.selectbox(
            "Selecione o jogo:",
            [o[0] for o in opcoes],
            key="adm_sel_jogo",
        )
        sel_jid = [o[1] for o in opcoes if o[0] == sel_label][0]
        sel_game = games[games["jogo_id"] == sel_jid].iloc[0]

        # Preencher com resultado já inserido, se existir
        res_atual = resultados_df[resultados_df["jogo_id"] == sel_jid]
        def_h = int(res_atual.iloc[0]["gols_home_real"]) if len(res_atual) > 0 else 0
        def_a = int(res_atual.iloc[0]["gols_away_real"]) if len(res_atual) > 0 else 0

        st.markdown(
            f"**{tn(sel_game['home_team'])}** × **{tn(sel_game['away_team'])}** "
            f"— {format_date(sel_game['data'])}"
        )

        r1, r2, r3 = st.columns([2, 0.5, 2])
        with r1:
            real_h = st.number_input(
                f"Gols {tn(sel_game['home_team'])}",
                min_value=0, max_value=20,
                value=def_h,
                key=f"adm_h_{sel_jid}",
            )
        with r2:
            st.markdown(
                "<p style='text-align:center;padding-top:1.7rem;font-size:1.2rem'>×</p>",
                unsafe_allow_html=True,
            )
        with r3:
            real_a = st.number_input(
                f"Gols {tn(sel_game['away_team'])}",
                min_value=0, max_value=20,
                value=def_a,
                key=f"adm_a_{sel_jid}",
            )

        if st.button("💾 Salvar resultado", type="primary", key="adm_salvar_resultado"):
            save_resultado(sel_jid, int(real_h), int(real_a))
            st.success(
                f"Resultado salvo: {tn(sel_game['home_team'])} {int(real_h)}–{int(real_a)} "
                f"{tn(sel_game['away_team'])}"
            )
            st.rerun()

        # Tabela de resultados já inseridos
        if not resultados_df.empty:
            st.subheader("Resultados já inseridos")
            res_enriq = resultados_df.merge(
                games[["jogo_id","data","home_team","away_team"]], on="jogo_id", how="left"
            )
            res_enriq["mandante"]  = res_enriq["home_team"].map(tn)
            res_enriq["visitante"] = res_enriq["away_team"].map(tn)
            res_enriq["placar"]    = res_enriq.apply(
                lambda r: f"{int(r.gols_home_real)}–{int(r.gols_away_real)}", axis=1
            )
            st.dataframe(
                res_enriq[["data","mandante","visitante","placar"]].sort_values("data"),
                use_container_width=True, hide_index=True,
            )

    # ── Adicionar jogo do mata-mata ───────────────────────────────────────────
    with adm_tab2:
        st.subheader("Adicionar jogo do mata-mata")
        st.caption(
            "Quando a fase de grupos encerrar, use este formulário para cadastrar "
            "os confrontos do mata-mata. O palpite do modelo será gerado com base "
            "nas probabilidades do CSV (se existirem para o par) ou ficará zerado."
        )

        with st.form("form_extra", clear_on_submit=True):
            fc1, fc2 = st.columns(2)
            with fc1:
                extra_home  = st.text_input("Time mandante (em inglês):", placeholder="Ex: Brazil")
                extra_data  = st.date_input("Data do jogo:", value=None)
                extra_fase  = st.selectbox("Fase:", FASES_ORDEM[1:])  # sem Fase de Grupos
            with fc2:
                extra_away  = st.text_input("Time visitante (em inglês):", placeholder="Ex: France")
                extra_cidade = st.text_input("Cidade:", placeholder="Ex: Los Angeles")

            add_extra = st.form_submit_button("➕ Adicionar jogo", type="primary")

        if add_extra:
            if not extra_home or not extra_away or extra_data is None:
                st.error("Preencha os campos obrigatórios: times e data.")
            else:
                novo_jogo = pd.DataFrame([{
                    "data":                str(extra_data),
                    "home_team":           extra_home.strip(),
                    "away_team":           extra_away.strip(),
                    "cidade":              extra_cidade.strip(),
                    "fase":                extra_fase,
                    "P_home":              0.0,
                    "P_draw":              0.0,
                    "P_away":              0.0,
                    "lambda_home":         0.0,
                    "lambda_away":         0.0,
                    "placar_mais_provavel":"—",
                    "top3_placares":       "—",
                    "resultado_previsto":  "H",
                    "confianca":           0.0,
                    "observacao":          "jogo do mata-mata — palpite do modelo não disponível",
                }])
                if EXTRAS_CSV.exists():
                    extras = pd.read_csv(EXTRAS_CSV)
                    extras = pd.concat([extras, novo_jogo], ignore_index=True)
                else:
                    extras = novo_jogo
                extras.to_csv(EXTRAS_CSV, index=False)
                load_games.clear()  # invalida o cache para incluir o novo jogo
                st.success(
                    f"Jogo adicionado: {tn(extra_home)} × {tn(extra_away)} ({extra_fase})"
                )
                st.rerun()
