"""Integration checks ensuring the dashboard data sources return rows."""
from __future__ import annotations

import os
from datetime import timedelta

import psycopg
import pytest

os.environ.setdefault("DB_DSN", "postgresql://injuries:injuries@127.0.0.1:5432/injuries")

from common.injuries import load_injuries_for_window
from common.time_windows import paris_window
from dash_app.dash_app import load_games

TEST_DATE = "2024-03-15"


@pytest.fixture(scope="module")
def seeded_db() -> None:
    """Seed minimal data into Postgres so dashboard queries have content."""
    dsn = os.environ["DB_DSN"]
    try:
        conn = psycopg.connect(dsn, autocommit=True)
    except Exception as exc:  # pragma: no cover - skip when DB is down
        pytest.skip(f"Postgres unavailable for integration tests: {exc}")

    try:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE injuries_history, injuries_current, players, games, teams RESTART IDENTITY CASCADE;"
            )
            cur.execute(
                """
                INSERT INTO teams (tricode, nba_team_id, name, city, espn_name)
                VALUES
                    ('BOS', 1610612738, 'Celtics', 'Boston', 'Boston Celtics'),
                    ('NYK', 1610612752, 'Knicks', 'New York', 'New York Knicks')
                RETURNING tricode, id;
                """
            )
            ids = dict(cur.fetchall())

            start_utc, _ = paris_window(TEST_DATE)
            tipoff_utc = start_utc + timedelta(hours=1)

            cur.execute(
                """
                INSERT INTO games (
                    game_id, season, tipoff_utc, home_team_id, away_team_id,
                    arena_name, arena_city, arena_state, game_status, game_status_text, postponed
                )
                VALUES (
                    'TEST001', 2025, %s, %s, %s,
                    'TD Garden', 'Boston', 'MA', 1, 'Scheduled', false
                );
                """,
                (tipoff_utc, ids["BOS"], ids["NYK"]),
            )

            cur.execute(
                """
                INSERT INTO injuries_current (team_id, player, status, est_return)
                VALUES (%s, %s, %s, %s);
                """,
                (ids["BOS"], "Jaylen Brown", "Out", "Day-to-day"),
            )
            cur.execute(
                """
                INSERT INTO injuries_history (check_date, team_id, player, status, est_return)
                VALUES (now(), %s, %s, %s, %s);
                """,
                (ids["BOS"], "Jaylen Brown", "Out", "Day-to-day"),
            )

        yield
    finally:
        with psycopg.connect(dsn, autocommit=True) as cleanup:
            with cleanup.cursor() as cur:
                cur.execute(
                    "TRUNCATE injuries_history, injuries_current, players, games, teams RESTART IDENTITY CASCADE;"
                )
        conn.close()


def test_games_table_not_empty(seeded_db: None) -> None:
    games = load_games(TEST_DATE)
    assert not games.empty, "Expected at least one game in the dashboard data."
    assert {"GAME_ID", "TIP_PARIS", "HOME", "AWAY"}.issubset(set(games.columns))


def test_injuries_table_not_empty(seeded_db: None) -> None:
    injuries = load_injuries_for_window(TEST_DATE)
    assert not injuries.empty, "Expected at least one injury for teams playing that night."
    assert injuries["PLAYER"].str.contains("Jaylen Brown").any()
