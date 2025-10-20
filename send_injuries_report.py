#!/usr/bin/env python3
"""Email the nightly injury report for teams playing in the Paris window."""
from __future__ import annotations

import argparse
import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable

import pandas as pd

from common import PARIS, load_injuries_for_window, paris_today

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "ton.email@gmail.com")
SMTP_PASS = os.getenv("SMTP_PASS", "mot_de_passe_ou_app_password")
EMAIL_TO = os.getenv("EMAIL_TO", "destinataire@example.com")

logger = logging.getLogger(__name__)


def injuries_to_html(dataframe: pd.DataFrame, date_str: str) -> str:
    """Render the injury dataframe into a styled HTML snippet."""
    if dataframe.empty:
        return f"""
        <div style="font-family:Arial,sans-serif; background-color:#f9fbff; padding:20px; border-radius:8px;">
          <h2 style="color:#1a237e;">😷 Blessés — équipes jouant la nuit du {date_str}</h2>
          <p style="color:#555;">Aucun joueur blessé signalé.</p>
        </div>
        """

    grouped = dataframe.groupby("TEAM")
    team_count = len(grouped)
    player_count = len(dataframe)

    sections: list[str] = []
    for team, subdf in grouped:
        rows = []
        for _, row in subdf.iterrows():
            background = "#ffffff"
            status_value = str(row["STATUS"])
            if "Out" in status_value:
                background = "#ffebeb"
            elif "Day-To-Day" in status_value:
                background = "#fff8e1"
            rows.append(
                f"""
                <tr style="background-color:{background};">
                  <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">{row['PLAYER']}</td>
                  <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">{row['STATUS']}</td>
                  <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">{row['EST_RETURN']}</td>
                </tr>
                """
            )

        sections.append(
            f"""
            <h3 style="color:#0d1b2a;margin-top:20px;">🏀 {team}</h3>
            <table style="width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;margin-bottom:10px;">
              <thead>
                <tr style="background:#1a237e;color:#fff;text-align:left;">
                  <th style="padding:10px 12px;">PLAYER</th>
                  <th style="padding:10px 12px;">STATUS</th>
                  <th style="padding:10px 12px;">EST RETURN</th>
                </tr>
              </thead>
              <tbody>
                {''.join(rows)}
              </tbody>
            </table>
            """
        )

    return f"""
    <div style="font-family:Arial, sans-serif; background-color:#f3f6ff; padding:20px;">
      <h2 style="margin:0 0 8px;color:#0d1b2a;">😷 Blessés — équipes jouant la nuit du {date_str}</h2>
      <p style="color:#444;margin-bottom:20px;">
        <strong>{team_count}</strong> équipes jouent — <strong>{player_count}</strong> blessé(s) signalé(s)
      </p>
      {''.join(sections)}
      <p style="font-size:12px;color:#7a7a7a;margin-top:20px;">
        Dernière mise à jour : {datetime.now(PARIS).strftime("%d/%m/%Y %H:%M")}
      </p>
    </div>
    """


def injuries_to_text(dataframe: pd.DataFrame, date_str: str) -> str:
    """Return a plain-text summary of the injuries for email clients."""
    if dataframe.empty:
        return f"Blessés — nuit du {date_str}\nAucun joueur blessé signalé."
    lines = [f"Blessés — nuit du {date_str}"]
    grouped = dataframe.groupby("TEAM")
    lines.append(f"{len(grouped)} équipes — {len(dataframe)} blessés\n")
    for team, subdf in grouped:
        lines.append(f"🏀 {team}")
        for _, row in subdf.iterrows():
            lines.append(f"  - {row['PLAYER']} — {row['STATUS']} (retour: {row['EST_RETURN']})")
        lines.append("")
    return "\n".join(lines)


def _parse_recipients(value: str) -> list[str]:
    """Split the EMAIL_TO environment variable into a clean list."""
    return [address.strip() for address in value.split(",") if address.strip()]


def send_email(subject: str, html_body: str, text_body: str, recipients: Iterable[str]) -> None:
    """Send a multipart email containing both HTML and plain text versions."""
    recipients_list = list(recipients)
    if not recipients_list:
        raise ValueError("No recipients provided for injuries report email")

    message = MIMEMultipart("alternative")
    message["From"] = SMTP_USER
    message["To"] = ", ".join(recipients_list)
    message["Subject"] = subject
    message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, recipients_list, message.as_string())

    logger.info("Injury report sent to %s", ", ".join(recipients_list))


def build_subject(date_str: str) -> str:
    """Return the default subject for the injury report email."""
    return f"NBA — Blessés (fenêtre Paris 18h→8h) — {date_str}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Envoie le rapport des blessés NBA pour une date donnée.")
    parser.add_argument("--date", type=str, help="Date au format YYYY-MM-DD (par défaut : aujourd'hui)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Entry point for the CLI script."""
    args = parse_args(argv)
    date_str = args.date or paris_today()
    dataframe = load_injuries_for_window(date_str)

    html_body = injuries_to_html(dataframe, date_str)
    text_body = injuries_to_text(dataframe, date_str)
    subject = build_subject(date_str)

    recipients = _parse_recipients(EMAIL_TO)
    send_email(subject, html_body, text_body, recipients)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
