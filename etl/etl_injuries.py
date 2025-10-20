import os
import sys
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import psycopg
import requests
import pandas as pd
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from common.db import DB_DSN
URL_ESPN = "https://www.espn.com/nba/injuries"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "close",
}

def _fetch_html_with_retries(url: str, tries: int = 5, backoff: float = 2.0) -> str:
    delay = 1.0
    last = None
    for i in range(1, tries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            return r.text
        except Exception as e:
            last = e
            time.sleep(delay)
            delay *= backoff
    raise RuntimeError(f"Failed to fetch {url}: {last}")

def _normalize_team_name(name: str) -> str:
    """Petite normalisation pour coller à teams.espn_name/full_name."""
    n = (name or "").strip()
    # Harmonise quelques variantes ESPN
    n = n.replace("LA Clippers", "Los Angeles Clippers")
    n = n.replace("LA Lakers", "Los Angeles Lakers")
    n = n.replace("Phoenix Suns Suns", "Phoenix Suns")
    return n

def fetch_espn_injuries_df() -> pd.DataFrame:
    """Scrape ESPN et renvoie TEAM, PLAYER, STATUS, EST_RETURN, COMMENT, CHECK_DATE."""
    html = _fetch_html_with_retries(URL_ESPN)
    soup = BeautifulSoup(html, "html.parser")

    rows = []
    for title in soup.find_all("div", class_="Table__Title"):
        team = _normalize_team_name(title.get_text(strip=True))
        table = title.find_next("table")
        if not table:
            continue
        df = pd.read_html(StringIO(str(table)))[0]
        if df.empty or "NAME" not in df.columns[0]:
            continue
        # ESPN: NAME | POS | EST. RETURN | STATUS | COMMENT  (l'ordre peut varier)
        cols = [c.upper() for c in df.columns]
        # Essaie de repérer colonnes par nom
        try:
            i_name = cols.index("NAME")
        except ValueError:
            i_name = 0
        # heuristique EST / STATUS (garde robustes)
        try:
            i_est = next(i for i,c in enumerate(cols) if "EST" in c)
        except StopIteration:
            i_est = 2
        try:
            i_status = next(i for i,c in enumerate(cols) if "STATUS" in c)
        except StopIteration:
            i_status = 3
        try:
            i_comment = next(i for i,c in enumerate(cols) if "COMMENT" in c)
        except StopIteration:
            i_comment = min(len(cols)-1, 4)

        for _, r in df.iterrows():
            player = str(r.iloc[i_name]).strip()
            if not player or player.upper() == "NAME":
                continue
            est_return = str(r.iloc[i_est]).strip() if pd.notna(r.iloc[i_est]) else ""
            status = str(r.iloc[i_status]).strip() if pd.notna(r.iloc[i_status]) else ""
            comment = str(r.iloc[i_comment]).strip() if pd.notna(r.iloc[i_comment]) else ""
            rows.append({
                "TEAM": team,
                "PLAYER": player,
                "STATUS": status or "Unknown",
                "EST_RETURN": est_return or "Unknown",
                "COMMENT": comment,
            })

    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["TEAM","PLAYER","STATUS","EST_RETURN","COMMENT","CHECK_DATE"])
    out["CHECK_DATE"] = datetime.now(tz=timezone.utc)
    return out

def _build_team_lookup(cur) -> dict[str, int]:
    """Load all team names once to avoid N queries per player."""
    cur.execute("SELECT id, name, espn_name, tricode FROM teams")
    lookup: dict[str, int] = {}
    for team_id, name, espn_name, tricode in cur.fetchall():
        for key in {name, espn_name, tricode}:
            if key:
                lookup[_normalize_team_name(str(key)).lower()] = team_id
    return lookup


def _map_team_name_to_id(cur, team_name: str, lookup: dict[str, int], fallback_cache: dict[str, int | None]) -> int | None:
    norm = _normalize_team_name(team_name).lower()
    if norm in lookup:
        return lookup[norm]
    if norm in fallback_cache:
        return fallback_cache[norm]

    cur.execute("SELECT id FROM teams WHERE espn_name ILIKE %s LIMIT 1", (f"%{team_name}%",))
    row = cur.fetchone()
    team_id = row[0] if row else None
    if team_id:
        lookup[norm] = team_id
    fallback_cache[norm] = team_id
    return team_id

def sync_injuries_once():
    df = fetch_espn_injuries_df()
    if df.empty:
        print("⚠️ Aucune donnée ESPN trouvée.")
        return

    inserted, updated, unchanged = 0, 0, 0

    with psycopg.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            # Charger état actuel en dict pour comparaison rapide
            cur.execute("SELECT team_id, player, status, est_return FROM injuries_current")
            current = {(t, p.lower()): (s, e) for t, p, s, e in cur.fetchall()}
            team_lookup = _build_team_lookup(cur)
            fallback_cache: dict[str, int | None] = {}

            for _, row in df.iterrows():
                team_name = row["TEAM"]
                team_id = _map_team_name_to_id(cur, team_name, team_lookup, fallback_cache)
                if not team_id:
                    # On ignore si équipe non mappée
                    continue

                player = row["PLAYER"].strip()
                status = row["STATUS"].strip() or "Unknown"
                est_return = row["EST_RETURN"].strip() or "Unknown"
                # Respecte NOT NULL de ton schéma
                status = status or "Unknown"
                est_return = est_return or "Unknown"

                key = (team_id, player.lower())
                prev = current.get(key)

                if prev is None:
                    # Nouveau joueur blessé -> insert current + snapshot history
                    cur.execute("""
                        INSERT INTO injuries_current (team_id, player, status, est_return, source, updated_at)
                        VALUES (%s,%s,%s,%s,'ESPN', now())
                        ON CONFLICT (team_id, player) DO NOTHING
                    """, (team_id, player, status, est_return))
                    cur.execute("""
                        INSERT INTO injuries_history (check_date, team_id, player, status, est_return, source)
                        VALUES (%s,%s,%s,%s,%s,'ESPN')
                    """, (row["CHECK_DATE"], team_id, player, status, est_return))
                    inserted += 1
                    current[key] = (status, est_return)  # maj cache
                else:
                    old_status, old_return = prev
                    if old_status != status or old_return != est_return:
                        # Changement détecté -> history + update current
                        cur.execute("""
                            INSERT INTO injuries_history (check_date, team_id, player, status, est_return, source)
                            VALUES (%s,%s,%s,%s,%s,'ESPN')
                        """, (row["CHECK_DATE"], team_id, player, status, est_return))
                        cur.execute("""
                            UPDATE injuries_current
                               SET status=%s, est_return=%s, source='ESPN', updated_at=now()
                             WHERE team_id=%s AND player=%s
                        """, (status, est_return, team_id, player))
                        updated += 1
                        current[key] = (status, est_return)
                    else:
                        unchanged += 1

        conn.commit()

    print(f"✅ ESPN injuries sync — nouveaux: {inserted} · maj: {updated} · inchangés: {unchanged}")

if __name__ == "__main__":
    sync_injuries_once()
