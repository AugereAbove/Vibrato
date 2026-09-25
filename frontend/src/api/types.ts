export type Validity =
  'VALID' | 'LOW_CONFIDENCE' | 'UNAVAILABLE' | 'NOT_APPLICABLE' | 'CONTAMINATED' | 'MODEL_UNAVAILABLE'

export type Basis = 'measured' | 'derived' | 'inferred' | 'experimental'

export type CategoryId =
  'pitch' | 'timing' | 'vowel' | 'vibrato' | 'dynamics' | 'phonation' | 'articulation' | 'breath' | 'timbre'

export type SegmentLevel = 'section' | 'phrase' | 'word' | 'syllable' | 'note' | 'phoneme'

export type TaskStatus = 'queued' | 'running' | 'complete' | 'failed' | 'cancelled' | 'interrupted'

export interface Task {
  id: string
  kind: string
  status: TaskStatus
  progress: number
  stage: string
  message: string
  project_id: string | null
  params: Record<string, unknown>
  result: unknown
  error: { what: string; why: string; action: string; code?: string; details?: string[] } | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface Project {
  id: string
  name: string
  song_title: string
  song_artist: string
  singer_label: string
  notes: string
  reference_profile_id: string | null
  favorite: number
  archived: number
  is_demo: number
  created_at: string
  updated_at: string
  last_opened_at: string | null
  reference_count: number
  take_count: number
  best_score: number | null
  latest_score: number | null
}

export interface QcIssue {
  code: string
  severity: 'info' | 'warning' | 'critical'
  title: string
  what: string
  why: string
  action: string
  value: number | null
  confidence: number
  affects: string[]
}

export interface QualityReport {
  duration_s: number
  source_sample_rate: number
  source_channels: number
  lossy: boolean
  peak_dbfs: number
  true_peak_dbfs: number
  rms_dbfs: number
  lufs_integrated: number | null
  dc_offset: number
  clipped_samples: number
  clipped_fraction: number
  clipped_regions: [number, number][]
  noise_floor_dbfs: number
  active_level_dbfs: number
  snr_db: number | null
  snr_reliable: boolean
  silence_regions: [number, number][]
  leading_silence_s: number
  trailing_silence_s: number
  trim_suggestion: [number, number] | null
  bandwidth_hz: number | null
  bandwidth_limited: boolean
  reverb_rt_estimate_s: number | null
  reverb_confidence: number | null
  stereo_coherence: number | null
  mixdown: string
  notes: string[]
  issues: QcIssue[]
  factors: Partial<Record<CategoryId, number>>
  factor_reasons: Partial<Record<CategoryId, string[]>>
  overall_quality: number
}

export type RecordingKind = 'reference' | 'take' | 'calibration'

export interface Recording {
  id: string
  project_id: string | null
  kind: RecordingKind
  source: string
  name: string
  original_filename: string
  content_hash: string
  favorite: number
  notes: string
  created_at: string
  updated_at: string
  duration_s: number
  source_format: string | null
  source_subtype: string | null
  source_sample_rate: number | null
  source_bit_depth: number | null
  source_channels: number | null
  decoder: string | null
  lossy: number
  canonical_sample_rate: number
  qc: QualityReport | null
  size_bytes: number
  original_extension: string
  reference_profile_id: string | null
  singer_label: string | null
  lyrics: string | null
  is_primary: number | null
  excluded_from_profile: number | null
  reference_recording_id: string | null
  session_id: string | null
  take_number: number | null
  synced_to_reference: number | null
  latency_ms: number | null
  region_start_s: number | null
  region_end_s: number | null
  overall_score: number | null
  comparison_id: string | null
  analysis_version: string | null
}

export interface Session {
  id: string
  project_id: string
  kind: string
  started_at: string
  last_activity_at: string
  ended_at: string | null
  active_seconds: number
  notes: string
  takes: number
}

export interface ProjectDetail {
  project: Project
  recordings: Recording[]
  sessions: Session[]
}

export interface Segment {
  id: string
  level: SegmentLevel
  ordinal: number
  start_s: number
  end_s: number
  label: string
  confidence: number
  parent_id: string | null
  props: Record<string, unknown>
}

export interface AnalysisEvent {
  id: string
  type: string
  start_s: number
  end_s: number
  confidence: number
  segment_id: string | null
  props: Record<string, unknown>
}

export type ResultValue = number | string | boolean | null | number[] | Record<string, unknown> | unknown[]

export interface AnalysisResult {
  analyzer_id: string
  analyzer_version: string
  segment_id: string | null
  segment_level: string | null
  values: Record<string, ResultValue>
  units: Record<string, string>
  basis: Record<string, Basis>
  confidence: number
  confidence_reasons: string[]
  validity: Validity
  warning_flags: string[]
  timestamp_start: number
  timestamp_end: number
  raw_supporting_data: Record<string, unknown>
  derived_interpretation: { label: string; text: string; basis: Basis; confidence: number } | null
}

export interface AnalyzerRun {
  id: string
  analysis_id: string
  analyzer_id: string
  analyzer_version: string
  status: 'ok' | 'failed' | 'unavailable' | 'disabled'
  validity: Validity
  confidence: number | null
  result_count: number
  duration_ms: number
  error: string | null
  created_at: string
}

export interface PhoneticClassSpan {
  class: string
  label: string
  start_s: number
  end_s: number
  confidence: number
}

export interface LyricsStatus {
  provided: boolean
  lines?: number
  words_expected?: number
  words_aligned?: number
  syllables_expected?: number
  syllables_detected?: number
  method?: string
}

export interface AnalysisSummary {
  duration_s: number
  voiced_s: number
  phrases: number
  words: number
  syllables: number
  notes: number
  phonemes: number
  events: number
  breaths: number
  median_confidence: number | null
  too_little_voice: boolean
  pitch_estimators: { id: string; label: string; version: string }[] | null
  noise_floor_db: number | null
  active_level_db: number | null
}

export interface AnalysisPayload {
  status: 'complete'
  recording_id: string
  analysis: { id: string; version: string; outdated: boolean; created_at: string; duration_ms: number }
  segments: Segment[]
  events: AnalysisEvent[]
  results: AnalysisResult[]
  summary: AnalysisSummary
  lyrics: LyricsStatus | null
  phonetic_classes: PhoneticClassSpan[] | null
  contamination: { score: number; evidence: string[] } | null
  runs: AnalyzerRun[]
  qc: QualityReport | null
}

export type AnalysisResponse = AnalysisPayload | { status: 'none'; recording_id: string }

export interface MetricComparison {
  metric_id: string
  category: CategoryId
  level: string
  label: string
  ref_segment_id: string | null
  user_segment_id: string | null
  ref_start: number
  ref_end: number
  user_start: number | null
  user_end: number | null
  ref_value: number | string | boolean | null
  user_value: number | string | boolean | null
  difference: number | null
  normalized: number | null
  direction: string
  confidence: number
  validity: Validity
  score: number | null
  weight: number
  importance: number
  evidence: Record<string, unknown>
  notes: string[]
  unit?: string
}

export interface MetricSummary {
  name: string
  unit: string
  tolerance: number
  weight: number
  instances: number
  scored_instances: number
  mean_score: number | null
  mean_confidence: number | null
  median_difference: number | null
  basis: Basis
  normalisation: string
  evidence_only: boolean
}

export interface CategoryScore {
  label: string
  score: number | null
  confidence: number
  status: string
  enabled: boolean
  weight: number
  metrics: Record<string, MetricSummary>
  count: number
  reason?: string
}

export interface Scores {
  categories: Record<CategoryId, CategoryScore>
  overall: {
    score: number | null
    confidence: number
    contributions: { category: CategoryId; score: number; effective_weight: number }[]
    disclaimer: string
  }
  method: Record<string, string>
}

export interface HeatCell {
  value: number
  z?: number
  confidence: number
  metric_id?: string
  label?: string
  direction?: string
  ref_start: number
  ref_end: number
  segment_id?: string
  count?: number
}

export interface HeatColumn {
  id: string
  label: string
  start_s: number
  end_s: number
}

export interface HeatmapView {
  columns: HeatColumn[]
  rows: Record<string, (HeatCell | null)[]>
}

export interface Heatmap {
  rows: string[]
  views: Record<'phrase' | 'word' | 'fine', HeatmapView>
}

export interface PracticeRegion {
  ref_start: number
  ref_end: number
  focus_start: number
  focus_end: number
  segment_id: string | null
  user_segment_id: string | null
  user_start: number | null
  user_end: number | null
  label: string
  phrase_id: string | null
  phrase_label: string | null
}

export interface FindingEvidence {
  label: string
  ref_start: number
  ref_end: number
  reference: string
  take: string
  difference: string
  z: number
  confidence: number
  segment_id: string | null
  basis: Basis
}

export interface Finding {
  key: string
  metric_id: string
  category: CategoryId
  direction: string
  title: string
  instances: string[]
  magnitude: number
  max_z: number
  confidence: number
  importance: number
  persistence: number
  trainability: number
  override: number
  priority: number
  systematic: boolean
  eligible: number
  tier: string
  practice: PracticeRegion | null
  texts: {
    beginner: string
    expert: string
    adjust: string
    adjust_basis: string
    exercise: string
    why: string
    layers: string[]
    confidence_label: string
    importance_label: string
    pattern: string
  }
  evidence: FindingEvidence[]
  ranking: {
    magnitude_term: number
    magnitude_basis: string
    confidence: number
    perceptual_importance: number
    persistence_multiplier: number
    trainability_factor: number
    systematic_bonus: number
    user_override: number
    formula: string
    user_action: string | null
  }
  history_takes: number
  corroborating: { key: string; title: string; metric_id: string }[]
}

export interface AlreadyGood {
  metric_id: string
  category: CategoryId
  name: string
  text: string
  confidence: number
  count: number
  importance: number
}

export interface DontWorry {
  key: string
  title: string
  category: CategoryId
  reason: string
  magnitude: number
  confidence: number
}

export interface NextFocus {
  finding_key: string
  title: string
  category: CategoryId
  headline: string
  why: string
  adjust: string
  adjust_basis: string
  exercise: string
  loop: PracticeRegion | null
  show_layers: string[]
  hide_layers: string[]
  confidence: number
  priority: number
  reasoning: string
}

export interface Coaching {
  version: string
  summary: string
  primary: Finding[]
  secondary: Finding[]
  minor: Finding[]
  uncertain: Finding[]
  already_good: AlreadyGood[]
  dont_worry: DontWorry[]
  next_focus: NextFocus | null
  findings: Finding[]
}

export interface AlignmentSummary {
  version: string
  method: string
  overall_confidence: number
  global_offset_s: number
  tempo_ratio: number
  transposition_semitones: number
  pitch_offset_cents: number
  warnings: string[]
  ref_range: [number, number]
  user_range: [number, number]
  anchors: { ref_time_s: number; user_time_s: number; locked: boolean }[]
}

export interface ScoreSnapshot {
  comparison_id: string
  take_id: string
  take_number: number | null
  overall: number | null
  categories: Record<string, { score: number | null; confidence: number }> | null
}

export interface Comparison {
  id: string
  version: string
  metrics: MetricComparison[]
  scores: Scores
  heatmap: Heatmap
  observations: { title: string; text: string }[]
  extras: {
    timing_model?: { slope: number; intercept_s: number; description: string; phrases_used: number }
    vowel_scaling?: { log_scale: number; factor: number; pairs: number; description: string }
    dynamic_envelopes?: { phrase: string; correlation: number }[]
    embedding_similarity?: { kind: string; cosine_similarity: number; note: string }
  }
  alignment: AlignmentSummary
  coverage: {
    reference_notes: number
    matched_notes: number
    reference_phrases: number
    matched_phrases: number
    unmatched_reference_notes: string[]
  }
  warnings: string[]
  coaching: Coaching
  reference_id: string
  take_id: string
  reference_analysis: { id: string; version: string }
  take_analysis: { id: string; version: string }
  take: Recording
  previous: ScoreSnapshot | null
  personal_best: ScoreSnapshot | null
  created_at: string
  is_outdated: boolean
}

export interface WhyResponse {
  region: { start_s: number; end_s: number }
  primary: Finding[]
  secondary: Finding[]
  minor: Finding[]
  already_close: { category: CategoryId; label: string; text: string }[]
  insufficient_confidence: { name: string; text: string }[]
  measurements_considered: number
}

export interface Anchor {
  id: string
  reference_recording_id: string
  take_recording_id: string
  ref_time_s: number
  user_time_s: number
  locked: number
  source: string
  label: string
  created_at: string
}

export interface AlignmentPath {
  summary: AlignmentSummary
  ref_times: number[]
  user_times: number[]
  confidence: number[]
  anchors: Anchor[]
  reference_id: string
  take_id: string
}

export interface TakeHistoryEntry {
  comparison_id: string
  take_id: string
  take_number: number | null
  take_name: string
  created_at: string
  session_id: string | null
  overall: number | null
  confidence: number
  categories: Partial<Record<CategoryId, number | null>>
  category_confidence: Partial<Record<CategoryId, number>>
  favorite: boolean
  notes: string
  region: [number, number] | null
  primary_focus: string | null
}

export interface Trend {
  label: string
  series: (number | null)[]
  rolling: (number | null)[]
  best: number | null
  latest: number | null
  delta: number | null
  slope_per_take: number | null
}

export interface Weakness {
  key: string
  title: string
  category: CategoryId
  metric: string
  occurrences: number
  takes: number
  sessions: number
  median_magnitude: number
  latest_magnitude: number | null
  trend: string
  trend_slope: number | null
  confidence: number
  persistent: boolean
  recent_hits: number
  recent_window: number
  last_seen_take: string | null
  first_seen_take: string | null
  summary: string
  label: string
}

export interface Milestone {
  id: string
  project_id: string
  take_recording_id: string | null
  kind: string
  title: string
  payload: Record<string, unknown>
  created_at: string
}

export interface Progress {
  reference_id: string | null
  takes: TakeHistoryEntry[]
  trends: Record<string, Trend>
  regressions: { category: string; label: string; text: string; latest: number; average: number }[]
  best_take: TakeHistoryEntry | null
  latest_take: TakeHistoryEntry | null
  phrases: {
    label: string
    history: { take_id: string; score: number | null }[]
    latest: number | null
    best: number | null
  }[]
  practice_frequency: { date: string; takes: number; minutes: number }[]
  sessions: Session[]
  milestones: Milestone[]
  weaknesses: Weakness[]
  strengths: {
    metric_id: string
    name: string
    category: CategoryId
    median_score: number
    takes: number
    text: string
  }[]
  personal_bests: {
    metric_id: string
    name: string
    score: number
    take_id: string
    take_number: number | null
  }[]
}

export interface Bookmark {
  id: string
  recording_id: string
  start_s: number
  end_s: number | null
  label: string
  color: string
  created_at: string
}

export interface SongSection {
  id: string
  recording_id: string
  label: string
  start_s: number
  end_s: number
  ordinal: number
  created_at: string
}

export interface Transform {
  id: string
  label: string
  description: string
  method: string
  experimental: boolean
  available: boolean
  unavailable_reason: string | null
}

export interface Render {
  id: string
  take_recording_id: string
  reference_recording_id: string
  transform: string
  params: Record<string, unknown>
  params_hash: string
  version: string
  path: string
  approximate: number
  warnings: string[]
  description: {
    label: string
    description: string
    method: string
    experimental: boolean
    output_timeline: string
    parameters: Record<string, unknown>
    disclaimer: string
  }
  created_at: string
}

export interface CalibrationStep {
  id: string
  title: string
  instruction: string
  seconds: number
  optional: boolean
  group: string
  vowel?: string
}

export interface CalibrationSample {
  id: string
  calibration_id: string
  step: string
  recording_id: string
  results: Record<string, unknown> | null
  created_at: string
}

export interface CalibrationResults {
  baseline?: { formant_log_mean?: number; formant_frames?: number }
  vowel_map?: Record<string, { f1: number; f2: number; f3: number }>
  range?: { low_hz: number | null; high_hz: number | null; semitones: number | null }
  vibrato?: { rate_hz: number | null; extent_cents: number | null; present: boolean | null }
  straight_tone?: { pitch_std_cents: number | null; vibrato_leak: boolean | null }
  phonation?: Record<'breathy' | 'modal', Record<string, number | null>>
  spectral?: { tilt_db_oct: number | null }
  noise_floor_dbfs?: number | null
  missing_steps?: string[]
  note?: string
}

export interface CalibrationProfile {
  id: string
  name: string
  status: 'in_progress' | 'complete'
  is_active: number
  results: CalibrationResults | null
  created_at: string
  finalized_at: string | null
  samples?: CalibrationSample[]
}

export interface ReferenceProfile {
  id: string
  name: string
  notes: string
  created_at: string
  updated_at: string
  recordings?: number
}

export interface ProfileTrait {
  key: string
  label: string
  unit: string
  median: number | null
  spread: number | null
  range?: [number, number]
  consistency: string
  n: number
}

export interface ReferenceProfileDetail {
  profile: ReferenceProfile
  recordings: {
    id: string
    name: string
    excluded: boolean
    project_id: string | null
    duration_s: number
    quality: number | null
  }[]
  traits: ProfileTrait[]
  per_recording: Record<string, Record<string, number | null>>
  confidence: number
  note: string
}

export type PreferenceValue = string | number | boolean | null | string[]

export interface PreferenceSchemaItem {
  key: string
  section: string
  label: string
  type: 'number' | 'boolean' | 'slider' | 'select' | 'multiselect' | 'text'
  help?: string
  min?: number
  max?: number
  step?: number
  options?: string[]
}

export interface PreferencesResponse {
  values: Record<string, PreferenceValue>
  defaults: Record<string, PreferenceValue>
  schema: PreferenceSchemaItem[]
}

export interface SystemInfo {
  app_version: string
  python: string
  platform: string
  cpu: { logical_cores: number; physical_cores: number; processor: string; load_percent: number }
  memory: { total_gb: number; available_gb: number; process_rss_mb: number }
  gpu: {
    torch: string | null
    cuda_available: boolean
    device: string
    name: string | null
    memory_gb: number | null
    note: string
  }
  libraries: Record<string, string | null>
  data_dir: string
  cache: Record<string, number>
  schema_version: number
  latest_schema_version: number
  pipeline_version: string
  comparison_version: string
  coaching_version: string
  recovery: { recovered: boolean; message: string }
  workers: number
  privacy: { telemetry: boolean; network_uploads: boolean; accounts: boolean; note: string }
}

export interface ModelStatus {
  id: string
  name: string
  kind: string
  available: boolean
  version: string | null
  used_for: string
  install: string | null
}

export interface AnalyzerInfo {
  id: string
  version: string
  category: string
  label: string
  description: string
  method: string
  assumptions: string[]
  limitations: string[]
  parameters: Record<string, unknown>
  dependencies: string[]
  supported_segment_types: string[]
  experimental: boolean
  requires: string[]
  available: boolean
  unavailable_reason: string
}

export interface MetricDefinition {
  id: string
  category: CategoryId
  name: string
  unit: string
  tolerance: number
  weight: number
  importance: number
  trainability: number
  basis: Basis
  description: string
  why: string
  tolerance_basis: string
  higher: string
  lower: string
  anatomy_dependent: boolean
  kind: string
}

export interface Methods {
  global: Record<string, string>
  analyzers: AnalyzerInfo[]
  metrics: MetricDefinition[]
  categories: Record<string, string>
  glossary: Record<string, string>
  versions: Record<string, string>
}

export interface Health {
  status: string
  version: string
  schema_version: number
  pipeline_version: string
  active_tasks: number
}
