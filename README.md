# TTFL Assistant

Assistant open-source pour préparer ses choix de joueurs dans la **TrashTalk Fantasy League (TTFL)**.  
La première brique fournit un tableau de bord et un e-mail quotidien recensant les joueurs blessés pour la nuit NBA.

---

## Fonctionnalités actuelles
- **Dashboard Dash** (http://localhost:8050) affichant les matchs de la nuit et les blessés par équipe.
- **E-mail quotidien** listant les blessés des équipes qui jouent.
- **ETL**:
  - `etl_teams_games.py` : synchronise le calendrier NBA + équipes.
  - `etl_players.py` : importe les rosters actuels (nba_api).
  - `etl_injuries.py` : scrappe ESPN injuries et alimente la base.

La base Postgres est initialisée avec `schema.sql`. Toutes les données transitent par la base `ttfl_database`.

---

## Pré-requis
- Python 3.11+
- Docker + Docker Compose (pour la stack complète)
- (Optionnel) venv : `python3 -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt`

---

## Démarrer la stack
```bash
docker compose up -d --build
```
Cette commande construit et lance Postgres, le dashboard Dash et l'ETL d'initialisation (`etl_teams_games.py` puis `etl_players.py`).  

Pour rejouer uniquement l’ETL blessures :
```bash
docker compose up -d etl-injuries
```
Pour relancer uniquement l’ETL joueurs :
```bash
docker compose run --rm etl-init bash -lc "python etl/etl_players.py"
```

### Envoi d’e-mail (local)
```bash
export DB_DSN=postgresql://ttfl:ttfl@127.0.0.1:5432/ttfl_database
export SMTP_USER=...
export SMTP_PASS=...
export EMAIL_TO=destinataire@example.com
python scripts/send_injuries_report.py --date 2025-10-21  # date optionnelle
```

---

## Tests
```bash
# Tests unitaires (helpers ETL, time windows, etc.)
python -m pytest tests/unit -vv

# Tests d’intégration (nécessitent Postgres en marche)
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  DB_DSN=postgresql://ttfl:ttfl@127.0.0.1:5432/ttfl_database \
  python -m pytest tests/integration -vv
```

---

## Workflows GitHub Actions
- `.github/workflows/tests_unit.yml` : exécute les tests unitaires sur chaque push/PR.
- `.github/workflows/test_dashboard.yml` : déploie un Postgres éphémère, seed les données et vérifie que les tables du dashboard ne sont pas vides.
- `.github/workflows/send_injuries.yml` : déclenche chaque jour l’ETL complet et envoie un e-mail de blessés via secrets `SMTP_*`, `EMAIL_TO`.

---

## Prochaines pistes
- Ajouter les stats par joueurs et le calcul des points ttfl sur les précédentes saisons
- Avoir un historique des blessures
