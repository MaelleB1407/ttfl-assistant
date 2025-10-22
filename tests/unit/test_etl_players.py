"""Tests for player ETL helpers."""
from __future__ import annotations

import sys
import types

sys.modules.setdefault("pandas", types.ModuleType("pandas"))

psycopg_stub = types.ModuleType("psycopg")
psycopg_stub.Connection = object  # type: ignore[attr-defined]
psycopg_stub.Cursor = object  # type: ignore[attr-defined]
psycopg_stub.connect = lambda *args, **kwargs: None  # type: ignore[attr-defined]
sys.modules.setdefault("psycopg", psycopg_stub)

nba_api_stub = types.ModuleType("nba_api")
nba_api_stats = types.ModuleType("nba_api.stats")
nba_api_stats_static = types.ModuleType("nba_api.stats.static")
nba_api_stats_static.teams = types.SimpleNamespace(get_teams=lambda: [])
nba_api_stats_endpoints = types.ModuleType("nba_api.stats.endpoints")
nba_api_stats_endpoints.commonteamroster = types.SimpleNamespace(CommonTeamRoster=None)
nba_api_stub.stats = nba_api_stats  # type: ignore[attr-defined]
sys.modules.setdefault("nba_api", nba_api_stub)
sys.modules.setdefault("nba_api.stats", nba_api_stats)
sys.modules.setdefault("nba_api.stats.static", nba_api_stats_static)
sys.modules.setdefault("nba_api.stats.endpoints", nba_api_stats_endpoints)

from etl.etl_players import parse_birth_date


def test_parse_birth_date_iso() -> None:
    assert parse_birth_date("1995-10-01T00:00:00") == "1995-10-01"


def test_parse_birth_date_named_months() -> None:
    assert parse_birth_date("Oct 1, 1995") == "1995-10-01"
    assert parse_birth_date("October 1, 1995") == "1995-10-01"


def test_parse_birth_date_invalid() -> None:
    assert parse_birth_date(None) is None
    assert parse_birth_date("Not a date") is None
