"""
Camada de persistência — Bolão Copa 2026
Camada 2: Google Sheets com fallback automático para CSV local.

Regra: se st.secrets tiver a chave [gsheets], usa GSheets.
       Se não tiver (local sem secrets.toml), usa CSV.
O resto do app não sabe qual backend está ativo.
"""
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread

# ─── Paths para o fallback local ─────────────────────────────────────────────
ROOT           = Path(__file__).resolve().parent.parent
DATA           = ROOT / "data"
PALPITES_CSV   = DATA / "bolao_palpites.csv"
RESULTADOS_CSV = DATA / "resultados_reais.csv"

# Escopos do Google necessários:
# spreadsheets → ler/escrever na planilha
# drive.file   → abrir arquivos criados pelo app (menos permissivo que drive completo)
_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

_PALPITES_HDR   = ["usuario", "jogo_id", "gols_home", "gols_away", "timestamp"]
_RESULTADOS_HDR = ["jogo_id", "gols_home_real", "gols_away_real"]


# ══════════════════════════════════════════════════════════════════════════════
# Detecção e conexão
# ══════════════════════════════════════════════════════════════════════════════

def _use_gsheets() -> bool:
    """
    Verifica se as credenciais do GSheets estão configuradas em st.secrets.
    O try/except é necessário porque st.secrets levanta FileNotFoundError
    em ambiente local sem o arquivo .streamlit/secrets.toml.
    """
    try:
        return "gsheets" in st.secrets
    except Exception:
        return False


@st.cache_resource
def _get_client() -> gspread.Client:
    """
    Cria e cacheia o cliente gspread.

    @st.cache_resource vs @st.cache_data:
    - cache_data: serializa e cacheia valores (DataFrames, dicts, strings)
    - cache_resource: cacheia objetos não-serializáveis como conexões de rede,
      modelos ML carregados em memória, clientes HTTP. O objeto fica vivo
      enquanto o servidor Streamlit rodar — sem reconectar a cada rerender.
    """
    creds = Credentials.from_service_account_info(
        st.secrets["gsheets"]["credentials"],
        scopes=_SCOPES,
    )
    return gspread.authorize(creds)


def _get_spreadsheet() -> gspread.Spreadsheet:
    return _get_client().open_by_key(st.secrets["gsheets"]["spreadsheet_id"])


def _get_or_create_ws(name: str, headers: list[str]) -> gspread.Worksheet:
    """
    Abre a aba pelo nome. Se não existir, cria e adiciona cabeçalho.
    Isso permite que o app inicialize a planilha sozinho na primeira execução.
    """
    sp = _get_spreadsheet()
    try:
        ws = sp.worksheet(name)
        # Garantir cabeçalho caso a aba exista mas esteja vazia
        if ws.row_count == 0 or not ws.acell("A1").value:
            ws.clear()
            ws.append_row(headers, value_input_option="RAW")
    except gspread.exceptions.WorksheetNotFound:
        ws = sp.add_worksheet(title=name, rows=2000, cols=len(headers))
        ws.append_row(headers, value_input_option="RAW")
    return ws


# ══════════════════════════════════════════════════════════════════════════════
# Backend Google Sheets
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=20)
def _load_palpites_gs() -> pd.DataFrame:
    """
    ttl=20s: o DataFrame fica em cache por 20 segundos antes de reler a API.
    Isso reduz chamadas ao Google Sheets para ~3 por minuto por usuário ativo,
    dentro do limite gratuito de 300 leituras/minuto por projeto.
    """
    ws      = _get_or_create_ws("palpites", _PALPITES_HDR)
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame(columns=_PALPITES_HDR)
    df = pd.DataFrame(records)
    df["jogo_id"]   = pd.to_numeric(df["jogo_id"],   errors="coerce").fillna(0).astype(int)
    df["gols_home"] = pd.to_numeric(df["gols_home"], errors="coerce").fillna(0).astype(int)
    df["gols_away"] = pd.to_numeric(df["gols_away"], errors="coerce").fillna(0).astype(int)
    return df


def _save_palpites_gs(usuario: str, palpites: dict[int, tuple[int, int]]) -> None:
    """
    Estratégia de escrita: ler tudo → remover linhas do usuário → reescrever.
    Custo: 3 chamadas à API (get_all_values, clear, update).
    Alternativa descartada: deletar linha a linha (N chamadas à API — mais lento).
    """
    ws         = _get_or_create_ws("palpites", _PALPITES_HDR)
    all_values = ws.get_all_values()           # lista de listas, inclui cabeçalho

    # Manter linhas de outros usuários; descartar as do usuário atual
    other_rows = [
        row for row in all_values[1:]
        if row and row[0] != usuario
    ]

    timestamp = datetime.now().isoformat()
    user_rows = [
        [usuario, jid, int(h), int(a), timestamp]
        for jid, (h, a) in sorted(palpites.items())
    ]

    new_data = [_PALPITES_HDR] + other_rows + user_rows
    ws.clear()
    ws.update("A1", new_data)

    # Invalidar cache — próximo load lerá da API com os dados novos
    _load_palpites_gs.clear()


@st.cache_data(ttl=20)
def _load_resultados_gs() -> pd.DataFrame:
    ws      = _get_or_create_ws("resultados", _RESULTADOS_HDR)
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame(columns=_RESULTADOS_HDR)
    df = pd.DataFrame(records)
    df["jogo_id"]        = pd.to_numeric(df["jogo_id"],        errors="coerce").fillna(0).astype(int)
    df["gols_home_real"] = pd.to_numeric(df["gols_home_real"], errors="coerce").fillna(0).astype(int)
    df["gols_away_real"] = pd.to_numeric(df["gols_away_real"], errors="coerce").fillna(0).astype(int)
    return df


def _save_resultado_gs(jogo_id: int, gh: int, ga: int) -> None:
    ws         = _get_or_create_ws("resultados", _RESULTADOS_HDR)
    all_values = ws.get_all_values()

    other_rows = [
        row for row in all_values[1:]
        if row and str(row[0]) != str(jogo_id)
    ]
    new_data = [_RESULTADOS_HDR] + other_rows + [[jogo_id, gh, ga]]
    ws.clear()
    ws.update("A1", new_data)
    _load_resultados_gs.clear()


# ══════════════════════════════════════════════════════════════════════════════
# Backend CSV local (Camada 1 — fallback)
# ══════════════════════════════════════════════════════════════════════════════

def _load_palpites_local() -> pd.DataFrame:
    if not PALPITES_CSV.exists():
        return pd.DataFrame(columns=_PALPITES_HDR)
    df = pd.read_csv(PALPITES_CSV)
    df["jogo_id"]   = df["jogo_id"].astype(int)
    df["gols_home"] = df["gols_home"].astype(int)
    df["gols_away"] = df["gols_away"].astype(int)
    return df


def _save_palpites_local(usuario: str, palpites: dict[int, tuple[int, int]]) -> None:
    df = _load_palpites_local()
    df = df[df["usuario"] != usuario]
    new_rows = pd.DataFrame([
        {"usuario": usuario, "jogo_id": jid, "gols_home": int(h),
         "gols_away": int(a), "timestamp": datetime.now().isoformat()}
        for jid, (h, a) in palpites.items()
    ])
    pd.concat([df, new_rows], ignore_index=True).to_csv(PALPITES_CSV, index=False)


def _load_resultados_local() -> pd.DataFrame:
    if not RESULTADOS_CSV.exists():
        return pd.DataFrame(columns=_RESULTADOS_HDR)
    df = pd.read_csv(RESULTADOS_CSV)
    df["jogo_id"]        = df["jogo_id"].astype(int)
    df["gols_home_real"] = df["gols_home_real"].astype(int)
    df["gols_away_real"] = df["gols_away_real"].astype(int)
    return df


def _save_resultado_local(jogo_id: int, gh: int, ga: int) -> None:
    df = _load_resultados_local()
    df = df[df["jogo_id"] != jogo_id]
    pd.concat([df, pd.DataFrame([{
        "jogo_id": jogo_id, "gols_home_real": gh, "gols_away_real": ga
    }])], ignore_index=True).to_csv(RESULTADOS_CSV, index=False)


# ══════════════════════════════════════════════════════════════════════════════
# Interface pública — mesma assinatura da Camada 1
# (o resto do app usa estas funções sem saber qual backend está ativo)
# ══════════════════════════════════════════════════════════════════════════════

def load_palpites() -> pd.DataFrame:
    if _use_gsheets():
        return _load_palpites_gs()
    return _load_palpites_local()


def save_palpites_batch(usuario: str, palpites: dict[int, tuple[int, int]]) -> None:
    if _use_gsheets():
        _save_palpites_gs(usuario, palpites)
    else:
        _save_palpites_local(usuario, palpites)


def load_resultados() -> pd.DataFrame:
    if _use_gsheets():
        return _load_resultados_gs()
    return _load_resultados_local()


def save_resultado(jogo_id: int, gh: int, ga: int) -> None:
    if _use_gsheets():
        _save_resultado_gs(jogo_id, gh, ga)
    else:
        _save_resultado_local(jogo_id, gh, ga)


def backend_label() -> str:
    """Texto curto indicando qual backend está ativo (para mostrar na sidebar)."""
    return "☁️ Google Sheets" if _use_gsheets() else "💾 Arquivo local"
