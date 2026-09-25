import { useEffect, useMemo } from 'react'
import { recordingsApi } from '../../api/endpoints'
import type { AnalysisPayload, Comparison, ProjectDetail, Recording, Task } from '../../api/types'
import { engine } from '../../audio/engine'
import type { TimelineModel } from '../../components/timeline/model'
import { indexAnalysis, indexComparison, type AnalysisIndex, type ComparisonIndex } from '../../lib/analysis'
import { IDENTITY_MAP } from '../../lib/timemap'
import {
  completeAnalysis,
  useAlignmentPath,
  useAnalysis,
  useComparison,
  useComparisonId,
  useFeatures,
  usePeaks,
  useProject,
  useSpectrogram,
} from '../../state/data'
import { usePref } from '../../state/prefs'
import type { ProjectTab } from '../../state/router'
import { isFinished, useTaskStore } from '../../state/tasks'
import { useUi } from '../../state/ui'
import { resetWorkspace } from '../../state/workspace'

export interface WorkstationData {
  projectId: string
  tab: ProjectTab
  detail: ProjectDetail | undefined
  projectError: unknown
  projectLoading: boolean
  references: Recording[]
  takes: Recording[]
  reference: Recording | null
  take: Recording | null
  refAnalysis: AnalysisPayload | null
  takeAnalysis: AnalysisPayload | null
  refIndex: AnalysisIndex | null
  takeIndex: AnalysisIndex | null
  refAnalysisStatus: 'loading' | 'none' | 'ready' | 'error'
  takeAnalysisStatus: 'loading' | 'none' | 'ready' | 'error'
  comparisonId: string | null | undefined
  comparison: Comparison | null
  cindex: ComparisonIndex | null
  comparisonLoading: boolean
  comparisonError: unknown
  model: TimelineModel
  tasks: Task[]
  recordingTasks: Map<string, Task>
  refreshComparison: () => void
}

function pickReference(references: Recording[], preferred?: string): Recording | null {
  if (preferred) {
    const match = references.find((r) => r.id === preferred)
    if (match) return match
  }
  return references.find((r) => r.is_primary) ?? references[0] ?? null
}

function pickTake(takes: Recording[], reference: Recording | null, preferred?: string): Recording | null {
  if (preferred) {
    const match = takes.find((t) => t.id === preferred)
    if (match) return match
  }
  const own = takes.filter((t) => !reference || t.reference_recording_id === reference.id)
  const pool = own.length ? own : takes
  return (
    [...pool].sort(
      (a, b) => (b.take_number ?? 0) - (a.take_number ?? 0) || b.created_at.localeCompare(a.created_at),
    )[0] ?? null
  )
}

function status(
  response: { data: unknown; error: unknown; status: string },
  payload: AnalysisPayload | null,
) {
  if (payload) return 'ready' as const
  if (response.error) return 'error' as const
  if (response.data && (response.data as { status: string }).status === 'none') return 'none' as const
  return 'loading' as const
}

export function useWorkstation(
  projectId: string,
  tab: ProjectTab,
  preferredTake?: string,
  preferredRef?: string,
): WorkstationData {
  const project = useProject(projectId)
  const detail = project.data
  const recordings = useMemo(() => detail?.recordings ?? [], [detail])
  const references = useMemo(() => recordings.filter((r) => r.kind === 'reference'), [recordings])
  const takes = useMemo(
    () =>
      recordings
        .filter((r) => r.kind === 'take')
        .sort(
          (a, b) => (a.take_number ?? 0) - (b.take_number ?? 0) || a.created_at.localeCompare(b.created_at),
        ),
    [recordings],
  )
  const reference = pickReference(references, preferredRef)
  const take = pickTake(takes, reference, preferredTake)
  const refAnalysisResource = useAnalysis(reference?.id ?? null)
  const takeAnalysisResource = useAnalysis(take?.id ?? null)
  const refAnalysis = completeAnalysis(refAnalysisResource.data)
  const takeAnalysis = completeAnalysis(takeAnalysisResource.data)
  const refFeatures = useFeatures(reference?.id ?? null, refAnalysis?.analysis.id)
  const takeFeatures = useFeatures(take?.id ?? null, takeAnalysis?.analysis.id)
  const refPeaks = usePeaks(reference)
  const takePeaks = usePeaks(take)
  const mode = usePref<string>('display.view_mode', 'coach')
  const layers = useUi((s) => s.layersByMode[mode === 'analyst' || mode === 'research' ? mode : 'coach'])
  const spectrogramSource = useUi((s) => s.spectrogramSource)
  const timeMode = useUi((s) => s.timeMode)
  const resolution = usePref<string>('display.spectrogram_resolution', 'medium')
  const maxHz = usePref<number>('display.spectrogram_max_hz', 8000)
  const wantSpectrogram = Boolean(layers?.spectrogram || layers?.formants)
  const refSpectrogram = useSpectrogram(
    reference?.id ?? null,
    refAnalysis?.analysis.id,
    resolution,
    maxHz,
    wantSpectrogram && (spectrogramSource === 'reference' || !take),
  )
  const takeSpectrogram = useSpectrogram(
    take?.id ?? null,
    takeAnalysis?.analysis.id,
    resolution,
    maxHz,
    wantSpectrogram && spectrogramSource === 'take' && Boolean(take),
  )
  const comparisonIdResource = useComparisonId(take && reference ? take.id : null)
  const comparisonId = comparisonIdResource.data
  const comparisonResource = useComparison(comparisonId)
  const comparison =
    comparisonResource.data && comparisonResource.data.reference_id === reference?.id
      ? comparisonResource.data
      : null
  const alignment = useAlignmentPath(comparison ? comparison.id : null)
  const refIndex = useMemo(() => (refAnalysis ? indexAnalysis(refAnalysis) : null), [refAnalysis])
  const takeIndex = useMemo(() => (takeAnalysis ? indexAnalysis(takeAnalysis) : null), [takeAnalysis])
  const cindex = useMemo(() => (comparison ? indexComparison(comparison) : null), [comparison])
  const taskMap = useTaskStore((s) => s.tasks)
  const tasks = useMemo(
    () => Object.values(taskMap).filter((t) => t.project_id === projectId && !isFinished(t)),
    [taskMap, projectId],
  )
  const recordingTasks = useMemo(() => {
    const map = new Map<string, Task>()
    for (const task of tasks) {
      const id = (task.params.take_id ?? task.params.recording_id) as string | undefined
      if (id) map.set(id, task)
    }
    return map
  }, [tasks])

  const aligned = timeMode === 'aligned'
  const map = alignment.map ?? IDENTITY_MAP
  const duration = reference
    ? aligned || !take
      ? reference.duration_s
      : Math.max(reference.duration_s, take.duration_s)
    : (take?.duration_s ?? 10)

  const model: TimelineModel = useMemo(
    () => ({
      ref: reference
        ? {
            recording: reference,
            analysis: refIndex,
            features: refFeatures.data ?? null,
            peaks: refPeaks.data ?? null,
            spectrogram: refSpectrogram.data ?? null,
          }
        : null,
      take: take
        ? {
            recording: take,
            analysis: takeIndex,
            features: takeFeatures.data ?? null,
            peaks: takePeaks.data ?? null,
            spectrogram: takeSpectrogram.data ?? null,
          }
        : null,
      map: comparison ? map : IDENTITY_MAP,
      aligned: aligned && Boolean(comparison),
      comparison,
      cindex,
      transposition: comparison?.alignment.transposition_semitones ?? 0,
      duration,
      spectrogramSide: spectrogramSource === 'take' && take ? 'take' : 'ref',
    }),
    [
      reference,
      take,
      refIndex,
      takeIndex,
      refFeatures.data,
      takeFeatures.data,
      refPeaks.data,
      takePeaks.data,
      refSpectrogram.data,
      takeSpectrogram.data,
      comparison,
      cindex,
      map,
      aligned,
      duration,
      spectrogramSource,
    ],
  )

  const refId = reference?.id ?? null
  const takeId = take?.id ?? null
  const refDuration = reference?.duration_s ?? 0
  const takeDuration = take?.duration_s ?? 0
  useEffect(() => {
    resetWorkspace(Math.max(refDuration, refId ? 0 : takeDuration) || takeDuration || 10)
  }, [refId, takeId, refDuration, takeDuration])

  const refLufs = reference?.qc?.lufs_integrated ?? null
  const takeLufs = take?.qc?.lufs_integrated ?? null
  useEffect(() => {
    engine.setTracks({
      ref: refId
        ? {
            id: refId,
            url: recordingsApi.audioUrl(refId),
            stretchUrl: (speed) => recordingsApi.stretchedUrl(refId, speed),
            lufs: refLufs,
          }
        : null,
      take: takeId
        ? {
            id: takeId,
            url: recordingsApi.audioUrl(takeId),
            stretchUrl: (speed) => recordingsApi.stretchedUrl(takeId, speed),
            lufs: takeLufs,
          }
        : null,
      synthetic: null,
    })
  }, [refId, takeId, refLufs, takeLufs])

  useEffect(() => {
    engine.setTimeMap(model.map, model.aligned)
  }, [model.map, model.aligned])

  return {
    projectId,
    tab,
    detail,
    projectError: project.error,
    projectLoading: project.loading,
    references,
    takes,
    reference,
    take,
    refAnalysis,
    takeAnalysis,
    refIndex,
    takeIndex,
    refAnalysisStatus: status(refAnalysisResource, refAnalysis),
    takeAnalysisStatus: status(takeAnalysisResource, takeAnalysis),
    comparisonId,
    comparison,
    cindex,
    comparisonLoading: comparisonIdResource.loading || comparisonResource.loading,
    comparisonError: comparisonResource.error ?? comparisonIdResource.error,
    model,
    tasks,
    recordingTasks,
    refreshComparison: () => {
      void comparisonIdResource.refresh()
    },
  }
}
