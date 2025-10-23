#!/usr/bin/env python3
import os
import smtplib
import argparse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd

from common import PARIS, load_injuries_for_window, paris_today

# --- CONFIGURATION ---
# 📧 Email settings
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "ton.email@gmail.com")
SMTP_PASS = os.getenv("SMTP_PASS", "mot_de_passe_ou_app_password")
EMAIL_TO   = os.getenv("EMAIL_TO", "destinataire@example.com")

# --- Génération HTML joliment groupée par équipe ---
def injuries_to_html(df: pd.DataFrame, date_str: str) -> str:
    if df.empty:
        return f"""
        <div style="font-family:Arial,sans-serif; background-color:#f9fbff; padding:20px; border-radius:8px;">
          <h2 style="color:#1a237e;">😷 Blessés — équipes jouant la nuit du {date_str}</h2>
          <p style="color:#555;">Aucun joueur blessé signalé.</p>
        </div>
        """

    grouped = df.groupby("TEAM")
    nb_teams = len(grouped)
    nb_players = len(df)

    html_sections = []
    for team, subdf in grouped:
        rows = []
        for _, r in subdf.iterrows():
            bg = "#ffffff"
            if "Out" in str(r["STATUS"]):
                bg = "#ffebeb"
            elif "Day-To-Day" in str(r["STATUS"]):
                bg = "#fff8e1"
            rows.append(f"""
              <tr style="background-color:{bg};">
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">{r['PLAYER']}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">{r['STATUS']}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">{r['EST_RETURN']}</td>
              </tr>
            """)

        section_html = f"""
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
        html_sections.append(section_html)

    return f"""
    <div style="font-family:Arial, sans-serif; background-color:#f3f6ff; padding:20px;">
      <h2 style="margin:0 0 8px;color:#0d1b2a;">😷 Blessés — équipes jouant la nuit du {date_str}</h2>
      <p style="color:#444;margin-bottom:20px;">
        <strong>{nb_teams}</strong> équipes jouent — <strong>{nb_players}</strong> blessé(s) signalé(s)
      </p>
      {''.join(html_sections)}
      <p style="font-size:12px;color:#7a7a7a;margin-top:20px;">
        Dernière mise à jour : {datetime.now(PARIS).strftime("%d/%m/%Y %H:%M")}
      </p>
    </div>
    """

# --- Version texte brut ---
def injuries_to_text(df: pd.DataFrame, date_str: str) -> str:
    if df.empty:
        return f"Blessés — nuit du {date_str}\nAucun joueur blessé signalé."
    lines = [f"Blessés — nuit du {date_str}"]
    grouped = df.groupby("TEAM")
    lines.append(f"{len(grouped)} équipes — {len(df)} blessés\n")
    for team, subdf in grouped:
        lines.append(f"🏀 {team}")
        for _, r in subdf.iterrows():
            lines.append(f"  - {r['PLAYER']} — {r['STATUS']} (retour: {r['EST_RETURN']})")
        lines.append("")
    return "\n".join(lines)

# --- Envoi email ---
def send_email(subject: str, html_body: str, text_body: str):
    recipients = [a.strip() for a in EMAIL_TO.split(",") if a.strip()]
    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, recipients, msg.as_string())

    print(f"✅ Email envoyé à {', '.join(recipients)}")

# --- Main ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Envoie le rapport des blessés NBA pour une date donnée.")
    parser.add_argument("--date", type=str, help="Date au format YYYY-MM-DD (par défaut : aujourd'hui)")
    args = parser.parse_args()

    date_str = args.date or paris_today()
    df = load_injuries_for_window(date_str)

    html_body = injuries_to_html(df, date_str)
    text_body = injuries_to_text(df, date_str)
    subject = f"NBA — Blessés — {date_str}"

    send_email(subject, html_body, text_body)
