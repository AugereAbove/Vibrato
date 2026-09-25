-- Multi-tenant auth: users, sessions, invites, and ownership scoping.

CREATE TABLE users (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  is_owner INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE sessions (
  token TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);

CREATE TABLE invites (
  code TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  used_at TEXT
);

CREATE INDEX idx_invites_user ON invites(user_id);

-- Direct ownership columns.
ALTER TABLE projects ADD COLUMN owner_id TEXT;
ALTER TABLE calibration_profiles ADD COLUMN owner_id TEXT;
ALTER TABLE reference_profiles ADD COLUMN owner_id TEXT;

CREATE INDEX idx_projects_owner ON projects(owner_id);
CREATE INDEX idx_calibration_owner ON calibration_profiles(owner_id);
CREATE INDEX idx_reference_profiles_owner ON reference_profiles(owner_id);

-- user_preferences was a single global key/value store; scope it per-owner.
-- SQLite can't change a table's PRIMARY KEY in place, so rebuild it.
ALTER TABLE user_preferences RENAME TO user_preferences_old;

CREATE TABLE user_preferences (
  owner_id TEXT NOT NULL,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (owner_id, key)
);

-- Bootstrap a single owner user so nothing already on disk becomes orphaned.
INSERT INTO users (id, display_name, is_owner, created_at)
VALUES ('usr_owner_bootstrap', 'Owner', 1, strftime('%Y-%m-%dT%H:%M:%f', 'now') || '+00:00');

INSERT INTO user_preferences (owner_id, key, value_json, updated_at)
SELECT 'usr_owner_bootstrap', key, value_json, updated_at FROM user_preferences_old;

DROP TABLE user_preferences_old;

UPDATE projects SET owner_id = 'usr_owner_bootstrap' WHERE owner_id IS NULL;
UPDATE calibration_profiles SET owner_id = 'usr_owner_bootstrap' WHERE owner_id IS NULL;
UPDATE reference_profiles SET owner_id = 'usr_owner_bootstrap' WHERE owner_id IS NULL;
