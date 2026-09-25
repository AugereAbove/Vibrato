import { http, query } from './client'
import type {
  AlignmentPath,
  AnalysisResponse,
  AnalyzerInfo,
  Anchor,
  Bookmark,
  CalibrationProfile,
  CalibrationStep,
  Comparison,
  Health,
  Methods,
  ModelStatus,
  PreferenceValue,
  PreferencesResponse,
  Progress,
  Project,
  ProjectDetail,
  Recording,
  ReferenceProfile,
  ReferenceProfileDetail,
  Render,
  Scores,
  Session,
  SongSection,
  SystemInfo,
  Task,
  Transform,
  WhyResponse,
} from './types'

export interface ProjectInput {
  name: string
  song_title?: string
  song_artist?: string
  singer_label?: string
  notes?: string
}

export type ProjectPatch = Partial<ProjectInput> & {
  favorite?: boolean
  archived?: boolean
  reference_profile_id?: string | null
}

export type RecordingPatch = Partial<{
  name: string
  notes: string
  favorite: boolean
  lyrics: string
  singer_label: string
  is_primary: boolean
  excluded_from_profile: boolean
  reference_profile_id: string | null
  reference_recording_id: string | null
}>

export interface UploadOptions {
  kind: 'reference' | 'take'
  name?: string
  referenceId?: string | null
  synced?: boolean
  latencyMs?: number
  regionStart?: number | null
  regionEnd?: number | null
  allowDuplicate?: boolean
  lyrics?: string
  source?: 'import' | 'record'
  autoAnalyze?: boolean
}

export const projectsApi = {
  list: (params: { search?: string; sort?: string; archived?: boolean; favorites?: boolean } = {}) =>
    http.get<{ projects: Project[] }>(`/projects${query(params)}`),
  create: (body: ProjectInput) => http.post<{ project: Project }>('/projects', body),
  get: (id: string) => http.get<ProjectDetail>(`/projects/${id}`),
  update: (id: string, body: ProjectPatch) => http.patch<{ project: Project }>(`/projects/${id}`, body),
  remove: (id: string) => http.del<{ deleted: boolean }>(`/projects/${id}`),
  duplicate: (id: string) => http.post<{ project: Project }>(`/projects/${id}/duplicate`),
  progress: (id: string, referenceId?: string | null) =>
    http.get<Progress>(`/projects/${id}/progress${query({ reference_id: referenceId })}`),
  progressCsvUrl: (id: string) => http.url(`/projects/${id}/progress.csv`),
  reportUrl: (id: string, comparisonId?: string | null, download = false) =>
    http.url(
      `/projects/${id}/report.html${query({ comparison_id: comparisonId, download: download || undefined })}`,
    ),
  backup: (id: string) => http.blob(`/projects/${id}/backup`, 'POST'),
  restore: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return http.form<{ project: Project }>('/projects/restore', form)
  },
  sessions: (id: string) => http.get<{ sessions: Session[] }>(`/projects/${id}/sessions`),
  activeSession: (id: string) => http.post<{ session: Session }>(`/projects/${id}/sessions/active`),
  updateSession: (id: string, body: { notes?: string; end?: boolean }) =>
    http.patch<{ session: Session }>(`/sessions/${id}`, body),
  overrides: (id: string) =>
    http.get<{ overrides: { finding_type: string; action: string }[] }>(`/projects/${id}/coaching-overrides`),
  addOverride: (id: string, findingType: string, action: 'ignore' | 'boost' | 'dismiss') =>
    http.post<{ overrides: { finding_type: string; action: string }[] }>(
      `/projects/${id}/coaching-overrides`,
      {
        finding_type: findingType,
        action,
      },
    ),
  clearOverrides: (id: string, findingType?: string) =>
    http.del<{ overrides: { finding_type: string; action: string }[] }>(
      `/projects/${id}/coaching-overrides${query({ finding_type: findingType })}`,
    ),
  createDemo: () => http.post<{ task: Task }>('/demo'),
}

export const recordingsApi = {
  upload: (projectId: string, file: Blob, filename: string, options: UploadOptions) => {
    const form = new FormData()
    form.append('file', file, filename)
    form.append('kind', options.kind)
    if (options.name) form.append('name', options.name)
    if (options.referenceId) form.append('reference_id', options.referenceId)
    form.append('synced', String(Boolean(options.synced)))
    form.append('latency_ms', String(options.latencyMs ?? 0))
    if (options.regionStart != null && options.regionEnd != null) {
      form.append('region_start_s', String(options.regionStart))
      form.append('region_end_s', String(options.regionEnd))
    }
    form.append('allow_duplicate', String(Boolean(options.allowDuplicate)))
    form.append('lyrics', options.lyrics ?? '')
    form.append('source', options.source ?? 'import')
    form.append('auto_analyze', String(options.autoAnalyze ?? true))
    return http.form<{ recording: Recording; task: Task | null }>(`/projects/${projectId}/recordings`, form)
  },
  list: (projectId: string, kind?: string) =>
    http.get<{ recordings: Recording[] }>(`/projects/${projectId}/recordings${query({ kind })}`),
  get: (id: string) => http.get<{ recording: Recording }>(`/recordings/${id}`),
  update: (id: string, body: RecordingPatch) =>
    http.patch<{ recording: Recording }>(`/recordings/${id}`, body),
  remove: (id: string) => http.del<{ deleted: boolean }>(`/recordings/${id}`),
  setLyrics: (id: string, lyrics: string) =>
    http.put<{ recording: Recording }>(`/recordings/${id}/lyrics`, { lyrics }),
  pronunciations: (id: string) =>
    http.get<{ overrides: Record<string, string> }>(`/recordings/${id}/pronunciations`),
  setPronunciation: (id: string, wordIndex: number, word: string, pronunciation: string | null) =>
    http.put<{ overrides: Record<string, string> }>(`/recordings/${id}/pronunciations`, {
      word_index: wordIndex,
      word,
      pronunciation,
    }),
  sections: (id: string) => http.get<{ sections: SongSection[] }>(`/recordings/${id}/sections`),
  setSections: (id: string, sections: { label: string; start_s: number; end_s: number }[]) =>
    http.put<{ sections: SongSection[] }>(`/recordings/${id}/sections`, { sections }),
  bookmarks: (id: string) => http.get<{ bookmarks: Bookmark[] }>(`/recordings/${id}/bookmarks`),
  addBookmark: (
    id: string,
    body: { start_s: number; end_s?: number | null; label?: string; color?: string },
  ) => http.post<{ bookmark: Bookmark }>(`/recordings/${id}/bookmarks`, body),
  updateBookmark: (id: string, body: Partial<Pick<Bookmark, 'start_s' | 'end_s' | 'label' | 'color'>>) =>
    http.patch<{ bookmark: Bookmark }>(`/bookmarks/${id}`, body),
  removeBookmark: (id: string) => http.del<{ deleted: boolean }>(`/bookmarks/${id}`),
  audioUrl: (id: string) => http.url(`/recordings/${id}/audio`),
  originalUrl: (id: string) => http.url(`/recordings/${id}/original`),
  stretchedUrl: (id: string, speed: number) => http.url(`/recordings/${id}/stretched${query({ speed })}`),
  segmentUrl: (id: string, start: number, end: number) =>
    http.url(`/recordings/${id}/segment.wav${query({ start: start.toFixed(3), end: end.toFixed(3) })}`),
  peaks: (id: string, signal?: AbortSignal) => http.buffer(`/recordings/${id}/peaks`, signal),
  analyze: (id: string, force = false) => http.post<{ task: Task }>(`/recordings/${id}/analyze`, { force }),
  analysis: (id: string, signal?: AbortSignal) =>
    http.get<AnalysisResponse>(`/recordings/${id}/analysis`, signal),
  features: (id: string, signal?: AbortSignal) => http.buffer(`/recordings/${id}/features`, signal),
  spectrogram: (id: string, resolution: string, maxHz: number, signal?: AbortSignal) =>
    http.buffer(`/recordings/${id}/spectrogram${query({ resolution, max_hz: maxHz })}`, signal),
}

export const comparisonsApi = {
  create: (takeId: string, referenceId?: string | null, forceAlign = false) =>
    http.post<{ task: Task }>('/comparisons', {
      take_id: takeId,
      reference_id: referenceId ?? null,
      force_align: forceAlign,
    }),
  forTake: (takeId: string) => http.get<{ comparison_id: string | null }>(`/takes/${takeId}/comparison`),
  get: (id: string, signal?: AbortSignal) => http.get<Comparison>(`/comparisons/${id}`, signal),
  why: (id: string, start: number, end: number) =>
    http.post<WhyResponse>(`/comparisons/${id}/why`, { start_s: start, end_s: end }),
  rescore: (id: string, enabled: Record<string, boolean>, weights: Record<string, number>) =>
    http.post<Scores>(`/comparisons/${id}/rescore`, { enabled, weights }),
  realign: (id: string, start: number, end: number) =>
    http.post<{ task: Task }>(`/comparisons/${id}/realign`, { start_s: start, end_s: end }),
  alignment: (id: string, signal?: AbortSignal) =>
    http.get<AlignmentPath>(`/comparisons/${id}/alignment`, signal),
  addAnchor: (body: {
    reference_id: string
    take_id: string
    ref_time_s: number
    user_time_s: number
    label?: string
  }) => http.post<{ anchor: Anchor }>('/anchors', { locked: true, ...body }),
  updateAnchor: (
    id: string,
    body: Partial<{ ref_time_s: number; user_time_s: number; locked: boolean; label: string }>,
  ) => http.patch<{ anchor: Anchor }>(`/anchors/${id}`, body),
  removeAnchor: (id: string) => http.del<{ deleted: boolean }>(`/anchors/${id}`),
  csvUrl: (id: string) => http.url(`/comparisons/${id}/export.csv`),
  jsonUrl: (id: string) => http.url(`/comparisons/${id}/export.json`),
  abUrl: (id: string, start: number, end: number) =>
    http.url(`/comparisons/${id}/ab.wav${query({ start: start.toFixed(3), end: end.toFixed(3) })}`),
}

export const counterfactualApi = {
  transforms: () => http.get<{ transforms: Transform[] }>('/counterfactual/transforms'),
  render: (takeId: string, transform: string) =>
    http.post<{ task: Task }>(`/takes/${takeId}/counterfactuals`, { transform }),
  list: (takeId: string) => http.get<{ renders: Render[] }>(`/takes/${takeId}/counterfactuals`),
  audioUrl: (renderId: string, download = false) =>
    http.url(`/renders/${renderId}/audio${query({ download: download || undefined })}`),
}

export const calibrationApi = {
  steps: () => http.get<{ steps: CalibrationStep[] }>('/calibration/steps'),
  list: () =>
    http.get<{ calibrations: CalibrationProfile[]; active: CalibrationProfile | null }>('/calibrations'),
  create: (name: string) => http.post<{ calibration: CalibrationProfile }>('/calibrations', { name }),
  get: (id: string) => http.get<{ calibration: CalibrationProfile }>(`/calibrations/${id}`),
  addSample: (id: string, step: string, file: Blob) => {
    const form = new FormData()
    form.append('step', step)
    form.append('file', file, `calibration-${step}.wav`)
    return http.form<{ step: string; recording_id: string; results: Record<string, unknown> }>(
      `/calibrations/${id}/samples`,
      form,
    )
  },
  finalize: (id: string) => http.post<{ calibration: CalibrationProfile }>(`/calibrations/${id}/finalize`),
  activate: (id: string) => http.post<{ active: CalibrationProfile | null }>(`/calibrations/${id}/activate`),
  deactivate: () => http.post<{ active: null }>('/calibrations/deactivate'),
  remove: (id: string) => http.del<{ deleted: boolean }>(`/calibrations/${id}`),
  compare: (ids: string[]) =>
    http.get<{ profiles: Record<string, unknown>[] }>(
      `/calibrations/compare${query({ ids: ids.join(',') })}`,
    ),
}

export const profilesApi = {
  list: () => http.get<{ profiles: ReferenceProfile[] }>('/reference-profiles'),
  create: (name: string, notes = '') =>
    http.post<{ profile: ReferenceProfile }>('/reference-profiles', { name, notes }),
  get: (id: string) => http.get<ReferenceProfileDetail>(`/reference-profiles/${id}`),
  update: (id: string, body: { name?: string; notes?: string }) =>
    http.patch<{ profile: ReferenceProfile }>(`/reference-profiles/${id}`, body),
  remove: (id: string) => http.del<{ deleted: boolean }>(`/reference-profiles/${id}`),
}

export const preferencesApi = {
  get: () => http.get<PreferencesResponse>('/preferences'),
  update: (values: Record<string, PreferenceValue>) =>
    http.put<{ values: Record<string, PreferenceValue> }>('/preferences', { values }),
  reset: (section?: string) =>
    http.post<{ values: Record<string, PreferenceValue> }>(`/preferences/reset${query({ section })}`),
}

export const tasksApi = {
  list: (active = false, projectId?: string | null) =>
    http.get<{ tasks: Task[] }>(`/tasks${query({ active: active || undefined, project_id: projectId })}`),
  get: (id: string) => http.get<{ task: Task }>(`/tasks/${id}`),
  cancel: (id: string) => http.post<{ task: Task }>(`/tasks/${id}/cancel`),
}

export const systemApi = {
  health: (signal?: AbortSignal) => http.get<Health>('/health', signal),
  info: () => http.get<SystemInfo>('/system'),
  models: () => http.get<{ models: ModelStatus[] }>('/system/models'),
  analyzers: () => http.get<{ analyzers: AnalyzerInfo[]; pipeline_version: string }>('/system/analyzers'),
  methods: () => http.get<Methods>('/system/methods'),
  cache: () => http.get<Record<string, number>>('/system/cache'),
  clearCache: () => http.post<{ freed_bytes: number; note: string }>('/system/cache/clear'),
  timing: () =>
    http.get<{
      analyzers: {
        analyzer_id: string
        analyzer_version: string
        runs: number
        mean_ms: number
        max_ms: number
        failures: number
      }[]
    }>('/system/timing'),
  outdated: () => http.get<{ recordings: string[]; current_version: string }>('/system/outdated'),
  reanalyze: (onlyOutdated: boolean) =>
    http.post<{ task: Task }>(`/system/reanalyze${query({ only_outdated: onlyOutdated })}`),
  logs: (lines = 300) => http.get<{ lines: string[] }>(`/system/logs${query({ lines })}`),
  debugBundleUrl: () => http.url('/system/debug-bundle'),
}
