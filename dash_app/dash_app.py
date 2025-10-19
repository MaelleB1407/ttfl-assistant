import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import psycopg
from dash import Dash, dcc, html, dash_table, Input, Output

DB_DSN = os.getenv("DB_DSN", "postgresql://injuries:injuries@postgres:5432/injuries")
PARIS = ZoneInfo("Europe/Paris")

def db_conn():
    return psycopg.connect(DB_DSN)

def paris_window(date_str: str, start_h: int = 18, end_h_next: int = 8):
    base = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=PARIS)
    start_paris = base.replace(hour=start_h, minute=0, second=0, microsecond=0)
    end_paris = (base + timedelta(days=1)).replace(hour=end_h_next, minute=0, second=0, microsecond=0)
    return start_paris.astimezone(ZoneInfo("UTC")), end_paris.astimezone(ZoneInfo("UTC"))

def load_games(date_str: str) -> pd.DataFrame:
    start_utc, end_utc = paris_window(date_str)
    q = """
        SELECT
          g.game_id,
          ((g.tipoff_utc AT TIME ZONE 'UTC') AT TIME ZONE 'Europe/Paris') AS tip_paris,
          th.tricode AS home, ta.tricode AS away,
          g.arena_name
        FROM games g
        JOIN teams th ON th.id = g.home_team_id
        JOIN teams ta ON ta.id = g.away_team_id
        WHERE g.tipoff_utc >= %s AND g.tipoff_utc < %s
        ORDER BY g.tipoff_utc;
    """
    with db_conn() as conn:
        games = pd.read_sql(q, conn, params=[start_utc, end_utc])
    if not games.empty:
        games["tip_paris"] = pd.to_datetime(games["tip_paris"]).dt.strftime("%Y-%m-%d %H:%M")
        games = games.rename(columns={
            "game_id": "GAME_ID", "tip_paris": "TIP_PARIS",
            "home": "HOME", "away": "AWAY", "arena_name": "ARENA"
        })
    return games

def load_injuries_for_window(date_str: str) -> pd.DataFrame:
    """Tous les blessés des équipes qui jouent dans la fenêtre Paris 18→8."""
    start_utc, end_utc = paris_window(date_str)
    q = """
        WITH playing AS (
          SELECT home_team_id AS team_id FROM games
          WHERE tipoff_utc >= %s AND tipoff_utc < %s
          UNION
          SELECT away_team_id FROM games
          WHERE tipoff_utc >= %s AND tipoff_utc < %s
        )
        SELECT
          t.tricode AS team,
          ic.player  AS player,
          ic.status  AS status,
          ic.est_return AS est_return
        FROM injuries_current ic
        JOIN playing p ON p.team_id = ic.team_id
        JOIN teams t    ON t.id = ic.team_id
        ORDER BY t.tricode, ic.status, ic.player;
    """
    with db_conn() as conn:
        df = pd.read_sql(q, conn, params=[start_utc, end_utc, start_utc, end_utc])

    if df.empty:
        return pd.DataFrame(columns=["TEAM","PLAYER","STATUS","EST_RETURN"])

    # Harmonise les noms & valeurs pour le DataTable
    df = df.rename(columns={
        "team": "TEAM",
        "player": "PLAYER",
        "status": "STATUS",
        "est_return": "EST_RETURN",
    })
    # Remplacer None/NaN par '' pour éviter les cellules vides
    df = df.fillna("")
    # Convertir en str (Dash n’affiche pas None et peut rendre vide)
    for col in ["TEAM","PLAYER","STATUS","EST_RETURN"]:
        df[col] = df[col].astype(str)

    return df[["TEAM","PLAYER","STATUS","EST_RETURN"]]

# ---------- Dash UI ----------
app = Dash(__name__)
app.title = "NBA Night View"

today_str = datetime.now(PARIS).strftime("%Y-%m-%d")

app.layout = html.Div(
    style={"fontFamily": "system-ui, -apple-system, Segoe UI, Roboto, sans-serif", "padding": "16px"},
    children=[
        html.H2("NBA — Fenêtre Paris 18h → 8h (matchs & blessés)"),
        html.Label("Date (heure Paris)"),
        dcc.DatePickerSingle(
            id="date-pick",
            display_format="YYYY-MM-DD",
            date=today_str,
            first_day_of_week=1
        ),
        html.Div(style={"height": "16px"}),

        html.H4(id="title-games"),
        dash_table.DataTable(
            id="tbl-games",
            columns=[
                {"name": "TIP_PARIS", "id": "TIP_PARIS"},
                {"name": "AWAY", "id": "AWAY"},
                {"name": "HOME", "id": "HOME"},
                {"name": "ARENA", "id": "ARENA"},
                {"name": "GAME_ID", "id": "GAME_ID"},
            ],
            data=[],
            page_size=12,
            style_table={"overflowX": "auto"},
            style_cell={"padding": "6px", "fontSize": 14},
        ),

        html.Div(style={"height": "20px"}),

        html.H4(id="title-inj"),
        dash_table.DataTable(
            id="tbl-injuries",
            columns=[
                {"name": "TEAM", "id": "TEAM"},
                {"name": "PLAYER", "id": "PLAYER"},
                {"name": "STATUS", "id": "STATUS"},
                {"name": "EST_RETURN", "id": "EST_RETURN"},
            ],
            data=[],
            page_size=20,
            style_table={"overflowX": "auto"},
            style_cell={"padding": "6px", "fontSize": 14},
            style_data_conditional=[
                {"if": {"filter_query": "{STATUS} contains 'Out'"}, "backgroundColor": "#ffe8e8"},
                {"if": {"filter_query": "{STATUS} contains 'Day-To-Day'"}, "backgroundColor": "#fff6e0"},
            ],
        ),
    ]
)

# ---------- Callbacks ----------
@app.callback(
    Output("tbl-games", "data"),
    Output("title-games", "children"),
    Output("tbl-injuries", "data"),
    Output("title-inj", "children"),
    Input("date-pick", "date"),
    prevent_initial_call=False
)
def refresh(date_str):
    if not date_str:
        return [], "Matchs (aucune date)", [], "Blessés (aucune date)"
    games = load_games(date_str)
    inj = load_injuries_for_window(date_str)

    title_games = f"Matchs pour {date_str} (fenêtre 18h→8h Paris) — {len(games)} trouvé(s)"
    title_inj = f"Blessés — équipes jouant le {date_str} (fenêtre 18h→8h) — {len(inj)} joueur(s)"

    return games.to_dict("records"), title_games, inj.to_dict("records"), title_inj

if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=8050, debug=False)
