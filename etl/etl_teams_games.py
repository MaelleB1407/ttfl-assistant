# etl_teams_games.py (robuste aux variations du JSON)
import os
import requests
import psycopg
from datetime import datetime, timezone

DB_DSN = os.getenv("DB_DSN", "postgresql://ttfl:ttfl@postgres:5432/ttfl_database")
URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"

def safe_get_game_dates(data: dict):
    """
    Certains dumps ont data['leagueSchedule']['gameDates'],
    d'autres peuvent aplatir à data['gameDates'].
    """
    ls = data.get("leagueSchedule", {})
    if isinstance(ls, dict) and "gameDates" in ls:
        return ls["gameDates"]
    return data.get("gameDates", [])

def infer_season_from_game(g: dict) -> int:
    """
    On n'utilise plus leagueSchedule.season : on infère.
    - Priorité au gameCode: "20251023/DENGSW" -> 2025
    - Sinon à partir de la date tipoff UTC -> année
    """
    code = g.get("gameCode")
    if code and len(code) >= 4 and code[:4].isdigit():
        return int(code[:4])
    tip = g.get("gameDateTimeUTC")
    if tip:
        try:
            return datetime.fromisoformat(tip.replace("Z", "+00:00")).year
        except Exception:
            pass
    # fallback très conservateur
    return 1970

def upsert_teams_and_games():
    data = requests.get(URL, timeout=30).json()
    game_dates = safe_get_game_dates(data)
    if not game_dates:
        raise RuntimeError("Aucune 'gameDates' trouvée dans le JSON NBA (clé manquante ou format inattendu).")

    # 1) Collecte des équipes valides
    teams = {}  # tri -> dict
    for day in game_dates:
        for g in day.get("games", []):
            for side in ("homeTeam", "awayTeam"):
                t = g.get(side, {}) or {}
                tri = (t.get("teamTricode") or "").strip()
                tid = t.get("teamId") or 0
                name = (t.get("teamName") or "").strip()
                city = (t.get("teamCity") or "").strip()

                # ignorer les entrées incomplètes (TBD, events)
                if not tri or not name or not tid:
                    continue

                teams[tri] = {
                    "nba_team_id": int(tid),
                    "name": name,
                    "city": city,
                    "espn_name": f"{city} {name}".strip() if city else name,
                }

    with psycopg.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            # 2) Upsert TEAMS (avec garde supplémentaire)
            for tri, info in teams.items():
                if not tri or not info.get("nba_team_id") or not info.get("name"):
                    continue
                cur.execute(
                    """
                    INSERT INTO teams (tricode, nba_team_id, name, city, espn_name, updated_at)
                    VALUES (%s, %s, %s, %s, %s, now())
                    ON CONFLICT (tricode) DO UPDATE SET
                        nba_team_id = EXCLUDED.nba_team_id,
                        name        = EXCLUDED.name,
                        city        = EXCLUDED.city,
                        espn_name   = EXCLUDED.espn_name,
                        updated_at  = now();
                    """,
                    (tri, info["nba_team_id"], info["name"], info["city"], info["espn_name"]),
                )

            # 3) Upsert GAMES (seulement si on résout les deux équipes)
            inserted_games = skipped_games = 0

            for day in game_dates:
                for g in day.get("games", []):
                    tip_str = g.get("gameDateTimeUTC")
                    if not tip_str:
                        skipped_games += 1
                        continue

                    ht = g.get("homeTeam", {}) or {}
                    at = g.get("awayTeam", {}) or {}
                    home_tri = (ht.get("teamTricode") or "").strip()
                    away_tri = (at.get("teamTricode") or "").strip()
                    if not home_tri or not away_tri:
                        skipped_games += 1
                        continue

                    # Résoudre team IDs DB
                    cur.execute("SELECT id FROM teams WHERE tricode=%s", (home_tri,))
                    row_h = cur.fetchone()
                    cur.execute("SELECT id FROM teams WHERE tricode=%s", (away_tri,))
                    row_a = cur.fetchone()
                    if not row_h or not row_a:
                        skipped_games += 1
                        continue

                    # tipoff & saison
                    tip_utc = datetime.fromisoformat(tip_str.replace("Z", "+00:00")).astimezone(timezone.utc)
                    season = infer_season_from_game(g)

                    cur.execute(
                        """
                        INSERT INTO games (
                            game_id, season, tipoff_utc, home_team_id, away_team_id,
                            arena_name, arena_city, arena_state, game_status, game_status_text, postponed, updated_at
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                        ON CONFLICT (game_id) DO UPDATE SET
                            season           = EXCLUDED.season,
                            tipoff_utc       = EXCLUDED.tipoff_utc,
                            home_team_id     = EXCLUDED.home_team_id,
                            away_team_id     = EXCLUDED.away_team_id,
                            arena_name       = EXCLUDED.arena_name,
                            arena_city       = EXCLUDED.arena_city,
                            arena_state      = EXCLUDED.arena_state,
                            game_status      = EXCLUDED.game_status,
                            game_status_text = EXCLUDED.game_status_text,
                            postponed        = EXCLUDED.postponed,
                            updated_at       = now();
                        """,
                        (
                            g.get("gameId"),
                            season,
                            tip_utc,
                            row_h[0],
                            row_a[0],
                            g.get("arenaName"),
                            g.get("arenaCity"),
                            g.get("arenaState"),
                            g.get("gameStatus"),
                            g.get("gameStatusText"),
                            True if g.get("postponedStatus") == "Y" else False,
                        ),
                    )
                    inserted_games += 1

        conn.commit()

    print(f"✅ Teams upserted: {len(teams)} — Games inserted/updated: {inserted_games} — Skipped (incomplete): {skipped_games}")

if __name__ == "__main__":
    upsert_teams_and_games()
