# etl_players_nba_api.py — robuste dates + transactions
import os
import time
import psycopg
import pandas as pd
from datetime import datetime
from nba_api.stats.static import teams as static_teams
from nba_api.stats.endpoints import commonteamroster
from requests.exceptions import RequestException

DB_DSN = os.getenv("DB_DSN", "postgresql://injuries:injuries@postgres:5432/injuries")
SEASON = os.getenv("NBA_SEASON_LABEL", "2025-26")  # format 'YYYY-YY'
SLEEP_BETWEEN_CALLS = float(os.getenv("NBA_API_SLEEP", "0.6"))

def parse_birth_date(val):
    """
    Accepte:
      - '1995-10-01T00:00:00' -> '1995-10-01'
      - 'Oct 1, 1995' / 'October 1, 1995' -> '1995-10-01'
      - sinon -> None
    """
    if not val:
        return None
    s = str(val).strip()
    # ISO-like
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        return s[:10]
    # Month name short/long
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass
    return None

def upsert_players_from_roster_df(cur, team_db_id: int, df: pd.DataFrame):
    for _, r in df.iterrows():
        try:
            nba_player_id = int(r["PLAYER_ID"])
        except Exception:
            continue

        display = str(r.get("PLAYER") or "").strip()
        parts = display.split()
        first = parts[0] if parts else display
        last = " ".join(parts[1:]) if len(parts) > 1 else ""

        jersey = (str(r.get("NUM") or "").strip() or None)
        pos    = (str(r.get("POSITION") or "").strip() or None)

        # dates
        birth_date = parse_birth_date(r.get("BIRTH_DATE"))

        # tailles/poids
        height_cm = None
        h = str(r.get("HEIGHT") or "")
        if "-" in h:
            try:
                feet, inches = h.split("-")
                inches_total = int(feet) * 12 + int(inches)
                height_cm = int(round(inches_total * 2.54))
            except Exception:
                height_cm = None

        weight_kg = None
        w = str(r.get("WEIGHT") or "")
        if w.isdigit():
            try:
                weight_kg = int(round(int(w) * 0.453592))
            except Exception:
                weight_kg = None

        country = (r.get("NATIONALITY") or None)

        cur.execute("""
            INSERT INTO players
              (nba_player_id, team_id, first_name, last_name, display_name,
               jersey_number, position, height_cm, weight_kg,
               birth_date, country, active, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE, now())
            ON CONFLICT (nba_player_id) DO UPDATE SET
               team_id       = EXCLUDED.team_id,
               position      = EXCLUDED.position,
               jersey_number = EXCLUDED.jersey_number,
               active        = TRUE,
               updated_at    = now();
        """, (
            nba_player_id, team_db_id, first, last, display,
            jersey, pos, height_cm, weight_kg,
            birth_date, country
        ))

def map_tricode_to_db_id(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT tricode, id FROM teams")
        return {tri: _id for tri, _id in cur.fetchall()}

def run_import():
    api_teams = static_teams.get_teams()  # [{'id', 'abbreviation', ...}]
    tri_to_api_id = {t["abbreviation"]: t["id"] for t in api_teams}

    with psycopg.connect(DB_DSN) as conn:
        tri_to_db = map_tricode_to_db_id(conn)

        done = skipped = 0

        for tricode, api_team_id in tri_to_api_id.items():
            team_db_id = tri_to_db.get(tricode)
            if not team_db_id:
                skipped += 1
                continue

            for attempt in range(1, 4):
                try:
                    res = commonteamroster.CommonTeamRoster(team_id=api_team_id, season=SEASON)
                    dfs = res.get_data_frames()
                    if not dfs or dfs[0].empty:
                        # Pas de roster (rare) : on considère traité
                        done += 1
                        break

                    roster_df = dfs[0]

                    # Transaction par équipe : rollback automatique si erreur
                    with conn.transaction():
                        with conn.cursor() as cur:
                            upsert_players_from_roster_df(cur, team_db_id, roster_df)

                    done += 1
                    time.sleep(SLEEP_BETWEEN_CALLS)
                    break

                except RequestException as e:
                    print(f"[{tricode}] network error attempt {attempt}: {e}")
                    time.sleep(1.0 * attempt)
                except psycopg.Error as e:
                    # Erreur SQL (ex: date invalide) -> on loggue et RETRY après rollback implicite
                    print(f"[{tricode}] SQL error attempt {attempt}: {e}")
                    time.sleep(0.8 * attempt)
                except Exception as e:
                    print(f"[{tricode}] error attempt {attempt}: {e}")
                    time.sleep(0.8 * attempt)

        print(f"✅ Rosters importés — équipes traitées: {done}, ignorées (non mappées): {skipped}")

if __name__ == "__main__":
    run_import()
