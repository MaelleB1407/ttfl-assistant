import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import psycopg
from dash import Dash, dcc, html, dash_table, Input, Output

# --- Connexion DB ---
DB_DSN = os.getenv("DB_DSN", "postgresql://injuries:injuries@postgres:5432/injuries")
PARIS = ZoneInfo("Europe/Paris")

def db_conn():
    return psycopg.connect(DB_DSN)

def paris_window(date_str: str, start_h: int = 18, end_h_next: int = 8):
    base = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=PARIS)
    start_paris = base.replace(hour=start_h, minute=0, second=0, microsecond=0)
    end_paris = (base + timedelta(days=1)).replace(hour=end_h_next, minute=0, second=0, microsecond=0)
    return start_paris.astimezone(ZoneInfo("UTC")), end_paris.astimezone(ZoneInfo("UTC"))

# --- Chargement des matchs ---
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

# --- Chargement des blessures ---
def load_injuries_for_window(date_str: str) -> pd.DataFrame:
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
        return pd.DataFrame(columns=["TEAM", "PLAYER", "STATUS", "EST_RETURN"])

    df = df.rename(columns={
        "team": "TEAM",
        "player": "PLAYER",
        "status": "STATUS",
        "est_return": "EST_RETURN",
    }).fillna("")

    for col in ["TEAM", "PLAYER", "STATUS", "EST_RETURN"]:
        df[col] = df[col].astype(str)

    return df[["TEAM", "PLAYER", "STATUS", "EST_RETURN"]]


# --- Dash UI ---
app = Dash(__name__)
app.title = "NBA Night View"

today_str = datetime.now(PARIS).strftime("%Y-%m-%d")

app.layout = html.Div(
    style={
        "fontFamily": "Inter, system-ui, sans-serif",
        "backgroundColor": "#f4f8fc",
        "padding": "24px",
        "color": "#111",
        "height": "100vh",
        "overflow": "hidden",
    },
    children=[
        html.H1(
            "🏀 NBA Night View — Matchs & Blessés (Fenêtre Paris 18h→8h)",
            style={
                "textAlign": "center",
                "color": "#003366",
                "marginBottom": "20px",
                "fontSize": "26px",
                "fontWeight": "600",
            },
        ),

        html.Div(
            style={
                "display": "flex",
                "justifyContent": "center",
                "alignItems": "center",
                "gap": "16px",
                "marginBottom": "25px",
            },
            children=[
                html.Label("📅 Date :", style={"fontWeight": "bold"}),
                dcc.DatePickerSingle(
                    id="date-pick",
                    display_format="YYYY-MM-DD",
                    date=today_str,
                    first_day_of_week=1,
                    style={
                        "border": "1px solid #ccc",
                        "padding": "6px",
                        "borderRadius": "6px",
                        "backgroundColor": "#fff",
                    },
                ),
                html.Label("🧩 Équipe :", style={"fontWeight": "bold"}),
                dcc.Dropdown(
                    id="team-filter",
                    options=[{"label": "Toutes les équipes", "value": "ALL"}],
                    value="ALL",
                    clearable=False,
                    style={"width": "220px"},
                ),
            ],
        ),

        html.Div(
            style={
                "display": "grid",
                "gridTemplateColumns": "1fr 1fr",
                "gap": "24px",
                "height": "75vh",
            },
            children=[
                html.Div([
                    html.H3("🏟️ Matchs à venir", style={"borderBottom": "3px solid #0066cc", "paddingBottom": "6px", "color": "#003366"}),
                    dash_table.DataTable(
                        id="tbl-games",
                        columns=[
                            {"name": "TIP_PARIS", "id": "TIP_PARIS"},
                            {"name": "AWAY", "id": "AWAY"},
                            {"name": "HOME", "id": "HOME"},
                            {"name": "ARENA", "id": "ARENA"},
                        ],
                        data=[],
                        page_size=15,
                        style_table={"height": "100%", "overflowY": "auto", "borderRadius": "8px"},
                        style_cell={
                            "padding": "8px",
                            "textAlign": "center",
                            "fontSize": 14,
                            "backgroundColor": "#ffffff",
                            "color": "#111",
                        },
                        style_header={
                            "backgroundColor": "#d8e7f8",
                            "fontWeight": "bold",
                            "borderBottom": "2px solid #ccc",
                            "color": "#003366",
                        },
                        style_data_conditional=[
                            {"if": {"row_index": "odd"}, "backgroundColor": "#f2f6fa"},
                        ],
                    ),
                ]),
                html.Div([
                    html.H3("🤕 Joueurs blessés", style={"borderBottom": "3px solid #0066cc", "paddingBottom": "6px", "color": "#003366"}),
                    dash_table.DataTable(
                        id="tbl-injuries",
                        columns=[
                            {"name": "TEAM", "id": "TEAM"},
                            {"name": "PLAYER", "id": "PLAYER"},
                            {"name": "STATUS", "id": "STATUS"},
                            {"name": "EST_RETURN", "id": "EST_RETURN"},
                        ],
                        data=[],
                        page_size=15,
                        style_table={
                            "height": "100%",
                            "overflowY": "auto",
                            "borderRadius": "10px",
                        },
                        style_cell={
                            "padding": "8px",
                            "textAlign": "center",
                            "fontSize": 14,
                            "backgroundColor": "#ffffff",
                            "color": "#111",
                            "border": "1px solid #e5e7eb",
                        },
                        style_header={
                            "backgroundColor": "#d8e7f8",
                            "fontWeight": "bold",
                            "borderBottom": "2px solid #99bde5",
                            "color": "#003366",
                        },
                        style_data_conditional=[
                            # ✅ Statut "Out" — rouge doux
                            {
                                "if": {"filter_query": "{STATUS} contains 'Out'"},
                                "backgroundColor": "#ffe5e5",
                                "color": "#8b0000",
                                "fontWeight": "500",
                            },
                            # ✅ Statut "Day-To-Day" — jaune pâle
                            {
                                "if": {"filter_query": "{STATUS} contains 'Day-To-Day'"},
                                "backgroundColor": "#fff6d9",
                                "color": "#705000",
                                "fontWeight": "500",
                            },
                            # ✅ Hover global (sans casser les couleurs)
                            {
                                "if": {"state": "active"},
                                "backgroundColor": "#e8f0fc",
                                "border": "1px solid #aac8f0",
                            },
                        ],
                    )

                ]),
            ],
        ),
    ],
)

# --- Callbacks ---
@app.callback(
    Output("tbl-games", "data"),
    Output("tbl-injuries", "data"),
    Output("team-filter", "options"),
    Input("date-pick", "date"),
    Input("team-filter", "value"),
)
def refresh(date_str, selected_team):
    if not date_str:
        return [], [], [{"label": "Toutes les équipes", "value": "ALL"}]

    games = load_games(date_str)
    inj = load_injuries_for_window(date_str)

    # Dropdown teams
    team_options = [{"label": "Toutes les équipes", "value": "ALL"}]
    if not inj.empty:
        team_options += [{"label": t, "value": t} for t in sorted(inj["TEAM"].unique())]

    if selected_team != "ALL" and not inj.empty:
        inj = inj[inj["TEAM"] == selected_team]

    print(f"[dash refresh] {date_str} → games={len(games)}, injuries={len(inj)}", flush=True)

    return games.to_dict("records"), inj.to_dict("records"), team_options


if __name__ == "__main__":
    print("✅ Dash app started", flush=True)
    app.run_server(host="0.0.0.0", port=8050, debug=False)
