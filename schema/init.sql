-- init.sql: Phase 1 minimal schema for discord-component-v2
BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id TEXT UNIQUE,
  channel_id TEXT,
  guild_id TEXT,
  content TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS components (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id TEXT,
  custom_id TEXT,
  component_type TEXT,
  label TEXT,
  semantic_action TEXT,
  payload_json TEXT,
  single_use INTEGER DEFAULT 0,
  expires_at TEXT,
  status TEXT DEFAULT 'active',
  UNIQUE(message_id, custom_id)
);

CREATE TABLE IF NOT EXISTS actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  semantic_action TEXT UNIQUE,
  inject_mode TEXT DEFAULT 'cli',
  inject_template TEXT,
  enabled INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS interaction_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  interaction_id TEXT UNIQUE,
  message_id TEXT,
  custom_id TEXT,
  user_id TEXT,
  raw_json TEXT,
  acked_at TEXT,
  normalized_text TEXT,
  process_state TEXT DEFAULT 'queued',
  error_text TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS delivery_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  interaction_id TEXT,
  adapter TEXT,
  attempt_no INTEGER,
  request_payload TEXT,
  response_payload TEXT,
  result TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Strong single_use enforcement: one claim per (message_id, semantic_action)
CREATE TABLE IF NOT EXISTS single_use_claims (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id TEXT NOT NULL,
  custom_id TEXT NOT NULL,
  first_interaction_id TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(message_id, custom_id)
);

COMMIT;
