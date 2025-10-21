"""Import NBA teams and schedule into the injuries database."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import psycopg
import requests
from psycopg import Connection, Cursor

DB_DSN = os.getenv("DB_DSN", "postgresql://injuries:injuries@postgres:5432/injuries")
URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"

logger = logging.getLogger(__name__)


def safe_get_game_dates(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the nested schedule list regardless of the JSON variant."""
    league_schedule = data.get("leagueSchedule", {})
    if isinstance(league_schedule, dict) and "gameDates" in league_schedule:
        return league_schedule["gameDates"]
    return data.get("gameDates", [])


def infer_season_from_game(game: dict[str, Any]) -> int:
    """Infer the season from the gameCode or the tipoff date."""
    code = game.get("gameCode")
    if code and len(code) >= 4 and code[:4].isdigit():
        return int(code[:4])
    tipoff = game.get("gameDateTimeUTC")
    if tipoff:
        try:
            return datetime.fromisoformat(tipoff.replace("Z", "+00:00")).year
        except ValueError:
            logger.debug("Unable to parse tipoff %s to infer season", tipoff)
    return 1970


def _upsert_teams(cursor: Cursor[Any], teams: dict[str, dict[str, Any]]) -> None:
    """Insert or update every team collected from the schedule feed."""
    for tricode, info in teams.items():
        if not tricode or not info.get("nba_team_id") or not info.get("name"):
            continue
        cursor.execute(
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
            (tricode, info["nba_team_id"], info["name"], info["city"], info["espn_name"]),
        )


def upsert_teams_and_games() -> None:
    """Download the NBA schedule feed and populate teams and games tables."""
    response = requests.get(URL, timeout=30)
    response.raise_for_status()
    payload = response.json()

    game_dates = safe_get_game_dates(payload)
    if not game_dates:
        raise RuntimeError("Unable to find 'gameDates' in NBA schedule JSON")

    teams: dict[str, dict[str, Any]] = {}
    for day in game_dates:
        for game in day.get("games", []):
            for side in ("homeTeam", "awayTeam"):
                team = game.get(side, {}) or {}
                tricode = (team.get("teamTricode") or "").strip()
                team_id = team.get("teamId") or 0
                name = (team.get("teamName") or "").strip()
                city = (team.get("teamCity") or "").strip()

                if not tricode or not name or not team_id:
                    continue

                teams[tricode] = {
                    "nba_team_id": int(team_id),
                    "name": name,
                    "city": city,
                    "espn_name": f"{city} {name}".strip() if city else name,
                }

    inserted_games = skipped_games = 0

    with psycopg.connect(DB_DSN) as connection:
        with connection.cursor() as cursor:
            _upsert_teams(cursor, teams)

            for day in game_dates:
                for game in day.get("games", []):
                    tipoff_str = game.get("gameDateTimeUTC")
                    if not tipoff_str:
                        skipped_games += 1
                        continue

                    home = game.get("homeTeam", {}) or {}
                    away = game.get("awayTeam", {}) or {}
                    home_tri = (home.get("teamTricode") or "").strip()
                    away_tri = (away.get("teamTricode") or "").strip()
                    if not home_tri or not away_tri:
                        skipped_games += 1
                        continue

                    cursor.execute("SELECT id FROM teams WHERE tricode=%s", (home_tri,))
                    home_row = cursor.fetchone()
                    cursor.execute("SELECT id FROM teams WHERE tricode=%s", (away_tri,))
                    away_row = cursor.fetchone()
                    if not home_row or not away_row:
                        skipped_games += 1
                        continue

                    tipoff_utc = datetime.fromisoformat(
                        tipoff_str.replace("Z", "+00:00")
                    ).astimezone(timezone.utc)
                    season = infer_season_from_game(game)

                    cursor.execute(
                        """
                        INSERT INTO games (
                            game_id, season, tipoff_utc, home_team_id, away_team_id,
                            arena_name, arena_city, arena_state, game_status, game_status_text, postponed, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
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
                            game.get("gameId"),
                            season,
                            tipoff_utc,
                            home_row[0],
                            away_row[0],
                            game.get("arenaName"),
                            game.get("arenaCity"),
                            game.get("arenaState"),
                            game.get("gameStatus"),
                            game.get("gameStatusText"),
                            True if game.get("postponedStatus") == "Y" else False,
                        ),
                    )
                    inserted_games += 1

        connection.commit()

    logger.info(
        "Teams upserted=%s — games upserted=%s — games skipped=%s",
        len(teams),
        inserted_games,
        skipped_games,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    upsert_teams_and_games()
