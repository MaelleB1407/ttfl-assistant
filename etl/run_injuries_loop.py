import os, time, traceback
from datetime import datetime
from zoneinfo import ZoneInfo

from etl_injuries import run_once  # tu l’implémentes dessous

PARIS = ZoneInfo("Europe/Paris")

if __name__ == "__main__":
    while True:
        print(f"[{datetime.now(PARIS)}] ETL injuries: start")
        try:
            run_once()
            print(f"[{datetime.now(PARIS)}] ETL injuries: OK")
        except Exception:
            traceback.print_exc()
        # dormir 2h
        time.sleep(2 * 60 * 60)
