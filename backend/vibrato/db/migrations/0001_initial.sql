CREATE TABLE reference_profiles (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  song_title TEXT NOT NULL DEFAULT '',
  song_artist TEXT NOT NULL DEFAULT '',
  singer_label TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  reference_profile_id TEXT REFERENCES reference_profiles(id) ON DELETE SET NULL,
  favorite INTEGER NOT NULL DEFAULT 0,
  archived INTEGER NOT NULL DEFAULT 0,
  is_demo INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_opened_at TEXT
);

CREATE TABLE audio_assets (
  content_hash TEXT PRIMARY KEY,
  original_path TEXT NOT NULL,
  canonical_path TEXT NOT NULL,
  playback_path TEXT NOT NULL,
  original_extension TEXT NOT NULL,
  source_format TEXT,
  source_subtype TEXT,
  source_sample_rate INTEGER,
  source_bit_depth INTEGER,
  source_channels INTEGER,
  decoder TEXT NOT NULL,
  lossy INTEGER NOT NULL DEFAULT 0,
  duration_s REAL NOT NULL,
  canonical_sample_rate INTEGER NOT NULL,
  canonical_version INTEGER NOT NULL,
  qc_json TEXT NOT NULL DEFAULT '{}',
  size_bytes INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'practice',
  started_at TEXT NOT NULL,
  last_activity_at TEXT NOT NULL,
  ended_at TEXT,
  active_seconds REAL NOT NULL DEFAULT 0,
  notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE recordings (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('reference', 'take', 'calibration')),
  source TEXT NOT NULL DEFAULT 'import' CHECK (source IN ('import', 'record', 'demo', 'calibration')),
  name TEXT NOT NULL,
  original_filename TEXT NOT NULL,
  content_hash TEXT NOT NULL REFERENCES audio_assets(content_hash),
  favorite INTEGER NOT NULL DEFAULT 0,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_recordings_project ON recordings(project_id, kind);
CREATE INDEX idx_recordings_hash ON recordings(content_hash);

CREATE TABLE reference_recordings (
  recording_id TEXT PRIMARY KEY REFERENCES recordings(id) ON DELETE CASCADE,
  reference_profile_id TEXT REFERENCES reference_profiles(id) ON DELETE SET NULL,
  singer_label TEXT NOT NULL DEFAULT '',
  lyrics TEXT NOT NULL DEFAULT '',
  is_primary INTEGER NOT NULL DEFAULT 0,
  excluded_from_profile INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE user_takes (
  recording_id TEXT PRIMARY KEY REFERENCES recordings(id) ON DELETE CASCADE,
  reference_recording_id TEXT REFERENCES recordings(id) ON DELETE SET NULL,
  session_id TEXT REFERENCES sessions(id) ON DELETE SET NULL,
  take_number INTEGER NOT NULL,
  synced_to_reference INTEGER NOT NULL DEFAULT 0,
  latency_ms REAL NOT NULL DEFAULT 0,
  region_start_s REAL,
  region_end_s REAL
);

CREATE INDEX idx_user_takes_reference ON user_takes(reference_recording_id);

CREATE TABLE song_sections (
  id TEXT PRIMARY KEY,
  recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  start_s REAL NOT NULL,
  end_s REAL NOT NULL,
  ordinal INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE pronunciation_overrides (
  id TEXT PRIMARY KEY,
  recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  word_index INTEGER NOT NULL,
  word TEXT NOT NULL,
  pronunciation TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (recording_id, word_index)
);

CREATE TABLE recording_analyses (
  id TEXT PRIMARY KEY,
  recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  content_hash TEXT NOT NULL,
  pipeline_version TEXT NOT NULL,
  params_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  features_path TEXT,
  analysis_path TEXT,
  summary_json TEXT NOT NULL DEFAULT '{}',
  duration_ms REAL,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_recording_analyses_recording ON recording_analyses(recording_id, created_at);

CREATE TABLE analyzer_runs (
  id TEXT PRIMARY KEY,
  analysis_id TEXT NOT NULL REFERENCES recording_analyses(id) ON DELETE CASCADE,
  analyzer_id TEXT NOT NULL,
  analyzer_version TEXT NOT NULL,
  status TEXT NOT NULL,
  validity TEXT,
  confidence REAL,
  result_count INTEGER NOT NULL DEFAULT 0,
  duration_ms REAL,
  error TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_analyzer_runs_analysis ON analyzer_runs(analysis_id);

CREATE TABLE segments (
  id TEXT PRIMARY KEY,
  analysis_id TEXT NOT NULL REFERENCES recording_analyses(id) ON DELETE CASCADE,
  recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  level TEXT NOT NULL CHECK (level IN ('section', 'phrase', 'word', 'syllable', 'note', 'phoneme')),
  parent_id TEXT,
  ordinal INTEGER NOT NULL,
  start_s REAL NOT NULL,
  end_s REAL NOT NULL,
  label TEXT NOT NULL DEFAULT '',
  confidence REAL NOT NULL DEFAULT 0,
  props_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_segments_analysis ON segments(analysis_id, level, start_s);

CREATE TABLE acoustic_events (
  id TEXT PRIMARY KEY,
  analysis_id TEXT NOT NULL REFERENCES recording_analyses(id) ON DELETE CASCADE,
  recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  start_s REAL NOT NULL,
  end_s REAL NOT NULL,
  segment_id TEXT,
  confidence REAL NOT NULL DEFAULT 0,
  props_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_events_analysis ON acoustic_events(analysis_id, type, start_s);

CREATE TABLE alignment_anchors (
  id TEXT PRIMARY KEY,
  reference_recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  take_recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  ref_time_s REAL NOT NULL,
  user_time_s REAL NOT NULL,
  locked INTEGER NOT NULL DEFAULT 1,
  source TEXT NOT NULL DEFAULT 'manual',
  label TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE INDEX idx_anchors_pair ON alignment_anchors(reference_recording_id, take_recording_id);

CREATE TABLE alignments (
  id TEXT PRIMARY KEY,
  reference_recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  take_recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  version TEXT NOT NULL,
  method TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence REAL,
  global_offset_s REAL,
  tempo_ratio REAL,
  transposition_semitones REAL,
  anchors_hash TEXT NOT NULL,
  path_file TEXT,
  summary_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE (reference_recording_id, take_recording_id)
);

CREATE TABLE comparisons (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  reference_recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  take_recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  alignment_id TEXT REFERENCES alignments(id) ON DELETE SET NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL,
  overall_score REAL,
  overall_confidence REAL,
  category_scores_json TEXT NOT NULL DEFAULT '{}',
  summary_json TEXT NOT NULL DEFAULT '{}',
  result_path TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (reference_recording_id, take_recording_id)
);

CREATE INDEX idx_comparisons_project ON comparisons(project_id, created_at);

CREATE TABLE metric_definitions (
  id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  name TEXT NOT NULL,
  unit TEXT NOT NULL,
  tolerance REAL NOT NULL,
  weight REAL NOT NULL,
  basis TEXT NOT NULL,
  description TEXT NOT NULL,
  version TEXT NOT NULL
);

CREATE TABLE metric_values (
  id TEXT PRIMARY KEY,
  comparison_id TEXT NOT NULL REFERENCES comparisons(id) ON DELETE CASCADE,
  metric_id TEXT NOT NULL,
  category TEXT NOT NULL,
  segment_level TEXT NOT NULL,
  ref_segment_id TEXT,
  user_segment_id TEXT,
  label TEXT NOT NULL DEFAULT '',
  ref_start_s REAL,
  ref_end_s REAL,
  user_start_s REAL,
  user_end_s REAL,
  ref_value REAL,
  user_value REAL,
  difference REAL,
  normalized_difference REAL,
  unit TEXT NOT NULL,
  confidence REAL NOT NULL,
  validity TEXT NOT NULL,
  score REAL,
  weight REAL,
  props_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_metric_values_comparison ON metric_values(comparison_id, category);
CREATE INDEX idx_metric_values_metric ON metric_values(metric_id);

CREATE TABLE coaching_suggestions (
  id TEXT PRIMARY KEY,
  comparison_id TEXT NOT NULL REFERENCES comparisons(id) ON DELETE CASCADE,
  finding_key TEXT NOT NULL,
  finding_type TEXT NOT NULL,
  rank INTEGER NOT NULL,
  tier TEXT NOT NULL,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  priority REAL NOT NULL,
  confidence REAL NOT NULL,
  importance REAL NOT NULL,
  persistence REAL NOT NULL,
  trainability REAL NOT NULL,
  magnitude REAL NOT NULL,
  direction TEXT,
  ref_start_s REAL,
  ref_end_s REAL,
  payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_coaching_comparison ON coaching_suggestions(comparison_id, rank);
CREATE INDEX idx_coaching_type ON coaching_suggestions(finding_type);

CREATE TABLE interpretations (
  id TEXT PRIMARY KEY,
  comparison_id TEXT NOT NULL REFERENCES comparisons(id) ON DELETE CASCADE,
  suggestion_id TEXT REFERENCES coaching_suggestions(id) ON DELETE CASCADE,
  basis TEXT NOT NULL CHECK (basis IN ('measured', 'derived', 'inferred', 'experimental')),
  text TEXT NOT NULL,
  confidence REAL NOT NULL,
  evidence_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE coaching_overrides (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
  finding_type TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('ignore', 'boost', 'dismiss')),
  created_at TEXT NOT NULL
);

CREATE INDEX idx_overrides_type ON coaching_overrides(finding_type);

CREATE TABLE bookmarks (
  id TEXT PRIMARY KEY,
  recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  start_s REAL NOT NULL,
  end_s REAL,
  label TEXT NOT NULL DEFAULT '',
  color TEXT NOT NULL DEFAULT 'amber',
  created_at TEXT NOT NULL
);

CREATE TABLE calibration_profiles (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 0,
  results_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  finalized_at TEXT
);

CREATE TABLE calibration_samples (
  id TEXT PRIMARY KEY,
  calibration_id TEXT NOT NULL REFERENCES calibration_profiles(id) ON DELETE CASCADE,
  step TEXT NOT NULL,
  recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  results_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  UNIQUE (calibration_id, step)
);

CREATE TABLE counterfactual_renders (
  id TEXT PRIMARY KEY,
  take_recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  reference_recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  transform TEXT NOT NULL,
  params_json TEXT NOT NULL,
  params_hash TEXT NOT NULL,
  version TEXT NOT NULL,
  path TEXT NOT NULL,
  approximate INTEGER NOT NULL DEFAULT 1,
  warnings_json TEXT NOT NULL DEFAULT '[]',
  description_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  UNIQUE (take_recording_id, reference_recording_id, params_hash, version)
);

CREATE TABLE milestones (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  take_recording_id TEXT REFERENCES recordings(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE user_preferences (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE tasks (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  progress REAL NOT NULL DEFAULT 0,
  stage TEXT NOT NULL DEFAULT '',
  message TEXT NOT NULL DEFAULT '',
  project_id TEXT,
  params_json TEXT NOT NULL DEFAULT '{}',
  result_json TEXT,
  error_json TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);

CREATE INDEX idx_tasks_status ON tasks(status, created_at);
