"""Synchronise ESPN injuries into the local database."""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
import requests
from bs4 import BeautifulSoup
from psycopg import Cursor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from common.db import DB_DSN  # noqa: E402

URL_ESPN = "https://www.espn.com/nba/injuries"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "close",
}

logger = logging.getLogger(__name__)


def _fetch_html_with_retries(url: str, tries: int = 5, backoff: float = 2.0) -> str:
    """Fetch a URL with exponential backoff to limit ESPN blocks."""
    delay = 1.0
    last_exc: Exception | None = None
    for attempt in range(1, tries + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning("Attempt %s/%s fetching %s failed: %s", attempt, tries, url, exc)
        except Exception as exc:  # pragma: no cover - defensive logging
            last_exc = exc
            logger.exception("Unexpected error while fetching %s", url)
        time.sleep(delay)
        delay *= backoff

    raise RuntimeError(f"Failed to fetch {url}") from last_exc


def _normalize_team_name(name: str) -> str:
    """Normalise ESPN team labels to match local database values."""
    norm = (name or "").strip()
    norm = norm.replace("LA Clippers", "Los Angeles Clippers")
    norm = norm.replace("LA Lakers", "Los Angeles Lakers")
    norm = norm.replace("Phoenix Suns Suns", "Phoenix Suns")
    return norm


def fetch_espn_injuries_df() -> pd.DataFrame:
    """Return a tidy dataframe with TEAM, PLAYER, STATUS, EST_RETURN, COMMENT, CHECK_DATE."""
    html = _fetch_html_with_retries(URL_ESPN)
    soup = BeautifulSoup(html, "html.parser")

    rows: list[dict[str, Any]] = []
    for title in soup.find_all("div", class_="Table__Title"):
        team = _normalize_team_name(title.get_text(strip=True))
        table = title.find_next("table")
        if not table:
            continue
        dataframe = pd.read_html(StringIO(str(table)))[0]
        if dataframe.empty:
            continue

        columns = [col.upper() for col in dataframe.columns]
        try:
            idx_name = columns.index("NAME")
        except ValueError:
            idx_name = 0
        try:
            idx_est = next(i for i, col in enumerate(columns) if "EST" in col)
        except StopIteration:
            idx_est = 2
        try:
            idx_status = next(i for i, col in enumerate(columns) if "STATUS" in col)
        except StopIteration:
            idx_status = 3
        try:
            idx_comment = next(i for i, col in enumerate(columns) if "COMMENT" in col)
        except StopIteration:
            idx_comment = min(len(columns) - 1, 4)

        for _, series in dataframe.iterrows():
            player = str(series.iloc[idx_name]).strip()
            if not player or player.upper() == "NAME":
                continue

            est_return = str(series.iloc[idx_est]).strip() if pd.notna(series.iloc[idx_est]) else ""
            status = (
                str(series.iloc[idx_status]).strip() if pd.notna(series.iloc[idx_status]) else ""
            )
            comment = (
                str(series.iloc[idx_comment]).strip() if pd.notna(series.iloc[idx_comment]) else ""
            )
            rows.append(
                {
                    "TEAM": team,
                    "PLAYER": player,
                    "STATUS": status or "Unknown",
                    "EST_RETURN": est_return or "Unknown",
                    "COMMENT": comment,
                }
            )

    output = pd.DataFrame(rows)
    if output.empty:
        return pd.DataFrame(
            columns=["TEAM", "PLAYER", "STATUS", "EST_RETURN", "COMMENT", "CHECK_DATE"]
        )

    output["CHECK_DATE"] = datetime.now(tz=timezone.utc)
    return output


def _build_team_lookup(cursor: Cursor[Any]) -> dict[str, int]:
    """Load all team names once to avoid repeated queries per player."""
    cursor.execute("SELECT id, name, espn_name, tricode FROM teams")
    lookup: dict[str, int] = {}
    for team_id, name, espn_name, tricode in cursor.fetchall():
        for key in {name, espn_name, tricode}:
            if key:
                lookup[_normalize_team_name(str(key)).lower()] = team_id
    return lookup


def _map_team_name_to_id(
    cursor: Cursor[Any],
    team_name: str,
    lookup: dict[str, int],
    fallback_cache: dict[str, int | None],
) -> int | None:
    """Resolve an ESPN team name to the teams.id primary key."""
    normalized = _normalize_team_name(team_name).lower()
    if normalized in lookup:
        return lookup[normalized]
    if normalized in fallback_cache:
        return fallback_cache[normalized]

    cursor.execute("SELECT id FROM teams WHERE espn_name ILIKE %s LIMIT 1", (f"%{team_name}%",))
    row = cursor.fetchone()
    team_id = row[0] if row else None
    if team_id:
        lookup[normalized] = team_id
    fallback_cache[normalized] = team_id
    return team_id


def sync_injuries_once() -> None:
    """Fetch injuries from ESPN and upsert them into injuries_current/history."""
    dataframe = fetch_espn_injuries_df()
    if dataframe.empty:
        logger.warning("No ESPN injuries data fetched")
        return

    inserted = updated = unchanged = 0

    with psycopg.connect(DB_DSN) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT team_id, player, status, est_return FROM injuries_current")
            current = {
                (team_id, player.lower()): (status, est_return)
                for team_id, player, status, est_return in cursor.fetchall()
            }
            lookup = _build_team_lookup(cursor)
            fallback_cache: dict[str, int | None] = {}

            for _, row in dataframe.iterrows():
                team_id = _map_team_name_to_id(cursor, row["TEAM"], lookup, fallback_cache)
                if not team_id:
                    logger.debug("Skip unmapped team: %s", row["TEAM"])
                    continue

                player = row["PLAYER"].strip()
                status = (row["STATUS"] or "Unknown").strip() or "Unknown"
                est_return = (row["EST_RETURN"] or "Unknown").strip() or "Unknown"
                key = (team_id, player.lower())
                previous = current.get(key)

                if previous is None:
                    cursor.execute(
                        """
                        INSERT INTO injuries_current (team_id, player, status, est_return, source, updated_at)
                        VALUES (%s, %s, %s, %s, 'ESPN', now())
                        ON CONFLICT (team_id, player) DO NOTHING
                        """,
                        (team_id, player, status, est_return),
                    )
                    cursor.execute(
                        """
                        INSERT INTO injuries_history (check_date, team_id, player, status, est_return, source)
                        VALUES (%s, %s, %s, %s, %s, 'ESPN')
                        """,
                        (row["CHECK_DATE"], team_id, player, status, est_return),
                    )
                    inserted += 1
                    current[key] = (status, est_return)
                else:
                    old_status, old_return = previous
                    if old_status != status or old_return != est_return:
                        cursor.execute(
                            """
                            INSERT INTO injuries_history (check_date, team_id, player, status, est_return, source)
                            VALUES (%s, %s, %s, %s, %s, 'ESPN')
                            """,
                            (row["CHECK_DATE"], team_id, player, status, est_return),
                        )
                        cursor.execute(
                            """
                            UPDATE injuries_current
                               SET status=%s, est_return=%s, source='ESPN', updated_at=now()
                             WHERE team_id=%s AND player=%s
                            """,
                            (status, est_return, team_id, player),
                        )
                        updated += 1
                        current[key] = (status, est_return)
                    else:
                        unchanged += 1

        conn.commit()

    logger.info(
        "ESPN injuries sync — inserted=%s updated=%s unchanged=%s",
        inserted,
        updated,
        unchanged,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sync_injuries_once()
