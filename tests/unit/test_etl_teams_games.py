"""Tests for schedule ETL helpers."""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

psycopg_stub = types.ModuleType("psycopg")
psycopg_stub.Connection = object  # type: ignore[attr-defined]
psycopg_stub.Cursor = object  # type: ignore[attr-defined]
psycopg_stub.connect = lambda *args, **kwargs: None  # type: ignore[attr-defined]
sys.modules.setdefault("psycopg", psycopg_stub)
sys.modules.setdefault("pandas", types.ModuleType("pandas"))

from etl.etl_teams_games import infer_season_from_game, safe_get_game_dates


def test_safe_get_game_dates_nested_structure() -> None:
    payload = {"leagueSchedule": {"gameDates": [{"games": []}]}}
    assert safe_get_game_dates(payload) == [{"games": []}]


def test_safe_get_game_dates_fallback_structure() -> None:
    payload = {"gameDates": [{"games": []}]}
    assert safe_get_game_dates(payload) == [{"games": []}]


def test_infer_season_from_game_code() -> None:
    game = {"gameCode": "20251023/DENGSW"}
    assert infer_season_from_game(game) == 2025


def test_infer_season_from_tipoff() -> None:
    tipoff = datetime(2023, 1, 5, tzinfo=timezone.utc).isoformat()
    game = {"gameDateTimeUTC": tipoff}
    assert infer_season_from_game(game) == 2023


def test_infer_season_default() -> None:
    assert infer_season_from_game({}) == 1970
