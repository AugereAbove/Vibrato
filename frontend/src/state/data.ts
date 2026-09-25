import { useMemo } from 'react'
import { parseFeatureBundle, parsePeaks, parseSpectrogram } from '../api/binary'
import {
  calibrationApi,
  comparisonsApi,
  counterfactualApi,
  preferencesApi,
  profilesApi,
  projectsApi,
  recordingsApi,
  systemApi,
} from '../api/endpoints'
import type { AnalysisPayload, AnalysisResponse, Recording } from '../api/types'
import { TimeMap } from '../lib/timemap'
import { invalidate, useResource } from './resource'

export const keys = {
  projects: (search: string, sort: string, archived: boolean, favorites: boolean) =>
    `projects:${search}|${sort}|${archived}|${favorites}`,
  project: (id: string) => `project:${id}`,
  analysis: (id: string) => `analysis:${id}`,
  features: (id: string, version: string) => `features:${id}:${version}`,
  peaks: (id: string, hash: string) => `peaks:${id}:${hash}`,
  spectrogram: (id: string, version: string, resolution: string, maxHz: number) =>
    `spectrogram:${id}:${version}:${resolution}:${maxHz}`,
  comparisonFor: (takeId: string) => `comparisonFor:${takeId}`,
  comparison: (id: string) => `comparison:${id}`,
  alignment: (id: string) => `alignment:${id}`,
  progress: (projectId: string, referenceId: string | null) => `progress:${projectId}:${referenceId ?? ''}`,
  bookmarks: (id: string) => `bookmarks:${id}`,
  sections: (id: string) => `sections:${id}`,
  renders: (takeId: string) => `renders:${takeId}`,
  transforms: 'transforms',
  system: 'system',
  models: 'models',
  methods: 'methods',
  analyzers: 'analyzers',
  cache: 'cache',
  timing: 'timing',
  outdated: 'outdated',
  calibrations: 'calibrations',
  calibrationSteps: 'calibrationSteps',
  profiles: 'profiles',
  profile: (id: string) => `profile:${id}`,
  preferences: 'preferences',
  sessions: (projectId: string) => `sessions:${projectId}`,
  overrides: (projectId: string) => `overrides:${projectId}`,
}

export function useProjects(search: string, sort: string, archived: boolean, favorites: boolean) {
  return useResource(keys.projects(search, sort, archived, favorites), () =>
    projectsApi
      .list({ search, sort, archived: archived || undefined, favorites: favorites || undefined })
      .then((r) => r.projects),
  )
}

export function useProject(id: string | null) {
  return useResource(id ? keys.project(id) : null, () => projectsApi.get(id as string))
}

export function useAnalysis(recordingId: string | null) {
  return useResource<AnalysisResponse>(recordingId ? keys.analysis(recordingId) : null, (signal) =>
    recordingsApi.analysis(recordingId as string, signal),
  )
}

export function completeAnalysis(response: AnalysisResponse | undefined): AnalysisPayload | null {
  return response && response.status === 'complete' ? response : null
}

export function useFeatures(recordingId: string | null, analysisId: string | null | undefined) {
  return useResource(
    recordingId && analysisId ? keys.features(recordingId, analysisId) : null,
    async (signal) => parseFeatureBundle(await recordingsApi.features(recordingId as string, signal)),
  )
}

export function usePeaks(recording: Recording | null | undefined) {
  return useResource(recording ? keys.peaks(recording.id, recording.content_hash) : null, async (signal) =>
    parsePeaks(await recordingsApi.peaks((recording as Recording).id, signal)),
  )
}

export function useSpectrogram(
  recordingId: string | null,
  analysisId: string | null | undefined,
  resolution: string,
  maxHz: number,
  enabled: boolean,
) {
  return useResource(
    enabled && recordingId && analysisId
      ? keys.spectrogram(recordingId, analysisId, resolution, maxHz)
      : null,
    async (signal) =>
      parseSpectrogram(await recordingsApi.spectrogram(recordingId as string, resolution, maxHz, signal)),
  )
}

export function useComparisonId(takeId: string | null) {
  return useResource(takeId ? keys.comparisonFor(takeId) : null, () =>
    comparisonsApi.forTake(takeId as string).then((r) => r.comparison_id),
  )
}

export function useComparison(comparisonId: string | null | undefined) {
  return useResource(comparisonId ? keys.comparison(comparisonId) : null, (signal) =>
    comparisonsApi.get(comparisonId as string, signal),
  )
}

export function useAlignmentPath(comparisonId: string | null | undefined) {
  const resource = useResource(comparisonId ? keys.alignment(comparisonId) : null, (signal) =>
    comparisonsApi.alignment(comparisonId as string, signal),
  )
  const map = useMemo(() => (resource.data ? new TimeMap(resource.data) : null), [resource.data])
  return { ...resource, map }
}

export function useProgress(projectId: string | null, referenceId: string | null) {
  return useResource(projectId ? keys.progress(projectId, referenceId) : null, () =>
    projectsApi.progress(projectId as string, referenceId),
  )
}

export function useBookmarks(recordingId: string | null) {
  return useResource(recordingId ? keys.bookmarks(recordingId) : null, () =>
    recordingsApi.bookmarks(recordingId as string).then((r) => r.bookmarks),
  )
}

export function useSections(recordingId: string | null) {
  return useResource(recordingId ? keys.sections(recordingId) : null, () =>
    recordingsApi.sections(recordingId as string).then((r) => r.sections),
  )
}

export function useRenders(takeId: string | null) {
  return useResource(takeId ? keys.renders(takeId) : null, () =>
    counterfactualApi.list(takeId as string).then((r) => r.renders),
  )
}

export function useTransforms() {
  return useResource(keys.transforms, () => counterfactualApi.transforms().then((r) => r.transforms))
}

export function useSystemInfo() {
  return useResource(keys.system, () => systemApi.info())
}

export function useModels() {
  return useResource(keys.models, () => systemApi.models().then((r) => r.models))
}

export function useMethods() {
  return useResource(keys.methods, () => systemApi.methods())
}

export function useCalibrations() {
  return useResource(keys.calibrations, () => calibrationApi.list())
}

export function useCalibrationSteps() {
  return useResource(keys.calibrationSteps, () => calibrationApi.steps().then((r) => r.steps))
}

export function useReferenceProfiles() {
  return useResource(keys.profiles, () => profilesApi.list().then((r) => r.profiles))
}

export function useReferenceProfile(id: string | null) {
  return useResource(id ? keys.profile(id) : null, () => profilesApi.get(id as string))
}

export function usePreferenceSchema() {
  return useResource(keys.preferences, () => preferencesApi.get())
}

export function useOverrides(projectId: string | null) {
  return useResource(projectId ? keys.overrides(projectId) : null, () =>
    projectsApi.overrides(projectId as string).then((r) => r.overrides),
  )
}

export function refreshProject(projectId: string | null | undefined): void {
  if (!projectId) return
  invalidate(keys.project(projectId))
  invalidate((key) => key.startsWith(`progress:${projectId}`))
  invalidate((key) => key.startsWith('projects:'))
}

export function refreshTake(takeId: string): void {
  invalidate(keys.comparisonFor(takeId))
  invalidate(keys.analysis(takeId))
  invalidate(keys.renders(takeId))
}

export function refreshRecording(recordingId: string): void {
  invalidate(keys.analysis(recordingId))
  invalidate(
    (key) => key.startsWith(`features:${recordingId}`) || key.startsWith(`spectrogram:${recordingId}`),
  )
}
