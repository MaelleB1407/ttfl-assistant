"""Helpers to load injuries for the Paris game window."""

from __future__ import annotations

import pandas as pd

from .db import db_conn
from .time_windows import paris_window

_INJURY_COLUMNS = ["TEAM", "PLAYER", "STATUS", "EST_RETURN"]

_QUERY = """
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


def load_injuries_for_window(date_str: str) -> pd.DataFrame:
    """Return injuries in the Paris window as a tidy DataFrame."""
    start_utc, end_utc = paris_window(date_str)
    with db_conn() as conn:
        df = pd.read_sql(_QUERY, conn, params=[start_utc, end_utc, start_utc, end_utc])

    if df.empty:
        return pd.DataFrame(columns=_INJURY_COLUMNS)

    df = (
        df.rename(
            columns={
                "team": "TEAM",
                "player": "PLAYER",
                "status": "STATUS",
                "est_return": "EST_RETURN",
            }
        )
        .fillna("")
        .astype(str)
    )

    return df[_INJURY_COLUMNS]
