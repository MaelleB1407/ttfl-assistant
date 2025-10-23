"""Import NBA rosters into the local database using nba_api."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any

import pandas as pd
import psycopg
from nba_api.stats.endpoints import commonteamroster
from nba_api.stats.static import teams as static_teams
from psycopg import Connection, Cursor
from requests.exceptions import RequestException

DB_DSN = os.getenv("DB_DSN", "postgresql://injuries:injuries@postgres:5432/injuries")
SEASON = os.getenv("NBA_SEASON_LABEL", "2025-26")
SLEEP_BETWEEN_CALLS = float(os.getenv("NBA_API_SLEEP", "0.6"))

logger = logging.getLogger(__name__)


def parse_birth_date(value: Any) -> str | None:
    """Normalise various nba_api birth date formats to ISO YYYY-MM-DD."""
    if not value:
        return None
    string = str(value).strip()
    if len(string) >= 10 and string[4] == "-" and string[7] == "-":
        return string[:10]
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            dt = datetime.strptime(string, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def upsert_players_from_roster_df(
    cursor: Cursor[Any], team_db_id: int, dataframe: pd.DataFrame
) -> None:
    """Insert or update the players for a given roster dataframe."""
    for _, row in dataframe.iterrows():
        try:
            nba_player_id = int(row["PLAYER_ID"])
        except Exception:  # pragma: no cover - defensive guard
            logger.debug("Skip row without numeric PLAYER_ID: %s", row.to_dict())
            continue

        display = str(row.get("PLAYER") or "").strip()
        parts = display.split()
        first = parts[0] if parts else display
        last = " ".join(parts[1:]) if len(parts) > 1 else ""

        jersey = str(row.get("NUM") or "").strip() or None
        position = str(row.get("POSITION") or "").strip() or None
        birth_date = parse_birth_date(row.get("BIRTH_DATE"))

        height_cm: int | None = None
        height_raw = str(row.get("HEIGHT") or "")
        if "-" in height_raw:
            try:
                feet, inches = height_raw.split("-")
                inches_total = int(feet) * 12 + int(inches)
                height_cm = int(round(inches_total * 2.54))
            except (TypeError, ValueError):
                logger.debug("Failed to parse height %s", height_raw)

        weight_kg: int | None = None
        weight_raw = str(row.get("WEIGHT") or "")
        if weight_raw.isdigit():
            weight_kg = int(round(int(weight_raw) * 0.453592))

        country = row.get("NATIONALITY") or None

        cursor.execute(
            """
            INSERT INTO players
              (nba_player_id, team_id, first_name, last_name, display_name,
               jersey_number, position, height_cm, weight_kg,
               birth_date, country, active, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, now())
            ON CONFLICT (nba_player_id) DO UPDATE SET
               team_id       = EXCLUDED.team_id,
               position      = EXCLUDED.position,
               jersey_number = EXCLUDED.jersey_number,
               active        = TRUE,
               updated_at    = now();
            """,
            (
                nba_player_id,
                team_db_id,
                first,
                last,
                display,
                jersey,
                position,
                height_cm,
                weight_kg,
                birth_date,
                country,
            ),
        )


def map_tricode_to_db_id(connection: Connection[Any]) -> dict[str, int]:
    """Return a mapping from NBA tricode to teams.id."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT tricode, id FROM teams")
        return {tricode: team_id for tricode, team_id in cursor.fetchall()}


def run_import() -> None:
    """Sync all NBA rosters for the configured season."""
    api_teams = static_teams.get_teams()
    tri_to_api_id = {team["abbreviation"]: team["id"] for team in api_teams}

    with psycopg.connect(DB_DSN) as connection:
        tri_to_db = map_tricode_to_db_id(connection)

        processed = skipped = 0

        for tricode, api_team_id in tri_to_api_id.items():
            team_db_id = tri_to_db.get(tricode)
            if not team_db_id:
                skipped += 1
                logger.warning("Skip %s — team not found in database", tricode)
                continue

            for attempt in range(1, 4):
                try:
                    result = commonteamroster.CommonTeamRoster(team_id=api_team_id, season=SEASON)
                    dataframes = result.get_data_frames()
                    if not dataframes or dataframes[0].empty:
                        processed += 1
                        break

                    roster_df = dataframes[0]
                    with connection.transaction():
                        with connection.cursor() as cursor:
                            upsert_players_from_roster_df(cursor, team_db_id, roster_df)

                    processed += 1
                    time.sleep(SLEEP_BETWEEN_CALLS)
                    break

                except RequestException as exc:
                    logger.warning("[%s] network error attempt %s: %s", tricode, attempt, exc)
                    time.sleep(1.0 * attempt)
                except psycopg.Error as exc:
                    logger.warning("[%s] SQL error attempt %s: %s", tricode, attempt, exc)
                    time.sleep(0.8 * attempt)
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.exception("[%s] unexpected error attempt %s", tricode, attempt)
                    time.sleep(0.8 * attempt)

        logger.info("Rosters import completed — processed=%s skipped=%s", processed, skipped)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_import()
