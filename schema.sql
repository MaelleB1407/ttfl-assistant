-- === TEAMS =====================================================
CREATE TABLE IF NOT EXISTS teams (
  id            serial PRIMARY KEY,
  tricode       text UNIQUE NOT NULL,     -- 'GSW'
  nba_team_id   integer UNIQUE,           -- 1610612744
  name          text NOT NULL,            -- 'Warriors'
  city          text,                     -- 'Golden State'
  espn_name     text,                     -- 'Golden State Warriors'
  conference    text,
  division      text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_teams_espn_name ON teams (espn_name);

-- === GAMES =====================================================
CREATE TABLE IF NOT EXISTS games (
  game_id            text PRIMARY KEY,               -- '0022500006'
  season             integer NOT NULL,
  tipoff_utc         timestamptz NOT NULL,           -- toujours UTC
  home_team_id       integer NOT NULL REFERENCES teams(id) ON DELETE RESTRICT,
  away_team_id       integer NOT NULL REFERENCES teams(id) ON DELETE RESTRICT,
  arena_name         text,
  arena_city         text,
  arena_state        text,
  game_status        smallint,
  game_status_text   text,
  postponed          boolean DEFAULT false,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_games_tipoff_utc ON games (tipoff_utc);
CREATE INDEX IF NOT EXISTS idx_games_home ON games (home_team_id);
CREATE INDEX IF NOT EXISTS idx_games_away ON games (away_team_id);

-- === PLAYERS ===================================================
CREATE TABLE IF NOT EXISTS players (
  id              serial PRIMARY KEY,
  nba_player_id   integer UNIQUE NOT NULL,
  team_id         integer REFERENCES teams(id) ON DELETE SET NULL,
  first_name      text NOT NULL,
  last_name       text NOT NULL,
  display_name    text,
  jersey_number   text,
  position        text,
  height_cm       integer,
  weight_kg       integer,
  birth_date      date,
  country         text,
  active          boolean DEFAULT true,
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_players_team ON players (team_id);
CREATE INDEX IF NOT EXISTS idx_players_name ON players (last_name, first_name);

-- === INJURIES (courant + historique, pour l’étape suivante) ====
CREATE TABLE IF NOT EXISTS injuries_current (
  team_id    integer NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  player     text    NOT NULL,
  status     text    NOT NULL,
  est_return text    NOT NULL,
  source     text    NOT NULL DEFAULT 'ESPN',
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (team_id, player)
);
CREATE INDEX IF NOT EXISTS idx_inj_cur_team ON injuries_current (team_id);
CREATE INDEX IF NOT EXISTS idx_inj_cur_status ON injuries_current (status);

CREATE TABLE IF NOT EXISTS injuries_history (
  id         bigserial PRIMARY KEY,
  check_date timestamptz NOT NULL,
  team_id    integer NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  player     text    NOT NULL,
  status     text    NOT NULL,
  est_return text    NOT NULL,
  source     text    NOT NULL DEFAULT 'ESPN'
);
CREATE INDEX IF NOT EXISTS idx_inj_hist_date ON injuries_history (check_date);
CREATE INDEX IF NOT EXISTS idx_inj_hist_team ON injuries_history (team_id);

-- NOTIFY (prêt pour le temps-réel / Dash plus tard)
CREATE OR REPLACE FUNCTION notify_injury_current_change()
RETURNS trigger AS $$
DECLARE payload jsonb;
BEGIN
  payload := jsonb_build_object(
    'check_date', now(),
    'team_id',    NEW.team_id,
    'player',     NEW.player,
    'status',     NEW.status,
    'est_return', NEW.est_return,
    'op',         TG_OP
  );
  PERFORM pg_notify('injury_changes', payload::text);
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_inj_cur_notify ON injuries_current;
CREATE TRIGGER trg_inj_cur_notify
AFTER INSERT OR UPDATE ON injuries_current
FOR EACH ROW EXECUTE FUNCTION notify_injury_current_change();
