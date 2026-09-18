-- ============================================================
--  MacroTrack Supabase & PostgreSQL Schema
--  Run this in: Supabase Dashboard > SQL Editor
-- ============================================================

-- ── 1. user_profiles ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_profiles (
  user_id            TEXT PRIMARY KEY,
  name               TEXT NOT NULL DEFAULT 'User',
  age                INTEGER NOT NULL DEFAULT 28,
  gender             TEXT NOT NULL DEFAULT 'male',
  weight_kg          NUMERIC(5,2) NOT NULL DEFAULT 75.0,
  height_cm          NUMERIC(5,2) NOT NULL DEFAULT 178.0,
  activity_level     TEXT NOT NULL DEFAULT 'moderate',
  dietary_preference TEXT NOT NULL DEFAULT 'veg',
  goal_archetype     TEXT NOT NULL DEFAULT 'general',
  meals_per_day      INTEGER NOT NULL DEFAULT 3,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 2. user_goals ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_goals (
  user_id       TEXT PRIMARY KEY REFERENCES user_profiles(user_id) ON DELETE CASCADE,
  calories_goal INTEGER NOT NULL DEFAULT 2200,
  protein_goal  NUMERIC(6,1) NOT NULL DEFAULT 150.0,
  carbs_goal    NUMERIC(6,1) NOT NULL DEFAULT 250.0,
  fat_goal      NUMERIC(6,1) NOT NULL DEFAULT 70.0,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 3. meal_logs ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS meal_logs (
  id               TEXT PRIMARY KEY,
  user_id          TEXT NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
  date             DATE NOT NULL DEFAULT CURRENT_DATE,
  meal_type        TEXT NOT NULL DEFAULT 'lunch',
  raw_input        TEXT NOT NULL,
  input_modality   TEXT NOT NULL DEFAULT 'text',
  items            JSONB NOT NULL DEFAULT '[]',
  calories         NUMERIC(7,1) NOT NULL DEFAULT 0,
  protein          NUMERIC(6,1) NOT NULL DEFAULT 0,
  carbs            NUMERIC(6,1) NOT NULL DEFAULT 0,
  fat              NUMERIC(6,1) NOT NULL DEFAULT 0,
  logged_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_macrotrack_user_date ON meal_logs (user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_macrotrack_logged_at ON meal_logs (logged_at DESC);

-- ── 4. meal_reminders ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS meal_reminders (
  id                 TEXT PRIMARY KEY,
  user_id            TEXT NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
  meal_type          TEXT NOT NULL,
  scheduled_time     TEXT NOT NULL,
  actual_logged_time TEXT,
  slippage_minutes   INTEGER NOT NULL DEFAULT 0,
  status             TEXT NOT NULL DEFAULT 'scheduled',
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── 5. Seed Default User ──────────────────────────────────────
INSERT INTO user_profiles (user_id, name, age, gender, weight_kg, height_cm, activity_level, dietary_preference, goal_archetype, meals_per_day)
VALUES ('default_user', 'Chirag', 28, 'male', 75.0, 178.0, 'moderate', 'veg', 'general', 3)
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO user_goals (user_id, calories_goal, protein_goal, carbs_goal, fat_goal)
VALUES ('default_user', 2200, 150.0, 250.0, 70.0)
ON CONFLICT (user_id) DO NOTHING;
