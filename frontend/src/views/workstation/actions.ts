import { ApiError } from '../../api/client'
import { comparisonsApi, recordingsApi, type RecordingPatch, type UploadOptions } from '../../api/endpoints'
import type { Bookmark, NextFocus, Recording, Task } from '../../api/types'
import { engine } from '../../audio/engine'
import { fitRange } from '../../components/timeline/viewport'
import { confirmAction } from '../../components/ui/confirm'
import { BACKEND_LAYER_MAP, LAYERS, type LayerId } from '../../lib/categories'
import { keys, refreshProject, refreshRecording, refreshTake } from '../../state/data'
import { attempt, reportError } from '../../state/errors'
import { pushUndo } from '../../state/history'
import type { ViewMode } from '../../state/prefs'
import { invalidate, setResourceData } from '../../state/resource'
import { navigate } from '../../state/router'
import { beginSave, trackTask, waitForTask } from '../../state/tasks'
import { pushToast } from '../../state/toasts'
import { setLayers, setUi } from '../../state/ui'
import { select, setLoop, useWorkspace, type Region } from '../../state/workspace'
import type { ProjectDetail } from '../../api/types'

export const AUDIO_ACCEPT = '.wav,.wave,.flac,.mp3,.m4a,.aac,.ogg,.oga,.opus,.aif,.aiff,.webm,audio/*'

function patchRecordingInCache(projectId: string, recording: Recording): void {
  setResourceData<ProjectDetail>(keys.project(projectId), (previous) =>
    previous
      ? {
          ...previous,
          recordings: previous.recordings.map((r) => (r.id === recording.id ? { ...r, ...recording } : r)),
        }
      : (previous as unknown as ProjectDetail),
  )
}

export function onAnalysisTask(
  task: Task | null,
  projectId: string,
  recordingId: string,
  then?: (task: Task) => void,
): void {
  if (!task) return
  trackTask(task, {
    onComplete: (finished) => {
      refreshRecording(recordingId)
      refreshTake(recordingId)
      refreshProject(projectId)
      then?.(finished)
    },
    onFailed: () => {
      refreshProject(projectId)
    },
  })
}

export async function importFile(
  projectId: string,
  file: Blob,
  filename: string,
  options: UploadOptions,
  onDone?: (recording: Recording, task: Task | null) => void,
): Promise<Recording | null> {
  const end = beginSave()
  try {
    const { recording, task } = await recordingsApi.upload(projectId, file, filename, options)
    refreshProject(projectId)
    onAnalysisTask(task, projectId, recording.id, () => onDone?.(recording, task))
    if (!task) onDone?.(recording, null)
    return recording
  } catch (error) {
    if (error instanceof ApiError && error.code === 'duplicate' && error.existingId) {
      const again = await confirmAction({
        title: 'This file is already in the project',
        body: `${error.what} Import it again anyway?`,
        confirmLabel: 'Import a second copy',
      })
      if (again) return importFile(projectId, file, filename, { ...options, allowDuplicate: true }, onDone)
      return null
    }
    reportError(error, `Could not import ${filename}`)
    return null
  } finally {
    end()
  }
}

export async function analyzeRecording(
  projectId: string,
  recording: Recording,
  force = false,
): Promise<void> {
  const result = await attempt(() => recordingsApi.analyze(recording.id, force), 'Analysis could not start')
  if (!result) return
  onAnalysisTask(result.task, projectId, recording.id)
}

export async function compareTake(
  projectId: string,
  take: Recording,
  referenceId: string | null,
  forceAlign = false,
): Promise<Task | null> {
  const result = await attempt(
    () => comparisonsApi.create(take.id, referenceId, forceAlign),
    'Comparison could not start',
  )
  if (!result) return null
  onAnalysisTask(result.task, projectId, take.id)
  return result.task
}

export async function updateRecording(
  projectId: string,
  recording: Recording,
  patch: RecordingPatch,
  label: string,
): Promise<void> {
  const before: RecordingPatch = {}
  for (const key of Object.keys(patch) as (keyof RecordingPatch)[]) {
    const value = recording[key as keyof Recording]
    ;(before as Record<string, unknown>)[key] =
      typeof value === 'number' &&
      (key === 'favorite' || key === 'is_primary' || key === 'excluded_from_profile')
        ? Boolean(value)
        : value
  }
  const apply = async (values: RecordingPatch) => {
    const end = beginSave()
    try {
      const { recording: updated } = await recordingsApi.update(recording.id, values)
      patchRecordingInCache(projectId, updated)
      refreshProject(projectId)
    } finally {
      end()
    }
  }
  try {
    await apply(patch)
    pushUndo({ label, undo: () => apply(before), redo: () => apply(patch) })
  } catch (error) {
    reportError(error, `${label} failed`)
  }
}

export async function deleteRecording(projectId: string, recording: Recording): Promise<boolean> {
  const ok = await confirmAction({
    title: `Delete “${recording.name}”?`,
    body:
      recording.kind === 'reference'
        ? 'The reference, its analysis and all comparisons against it are removed. Takes stay in the project. This cannot be undone.'
        : 'The take, its analysis and its comparison history are removed. This cannot be undone.',
    confirmLabel: 'Delete',
    danger: true,
  })
  if (!ok) return false
  const end = beginSave()
  try {
    await recordingsApi.remove(recording.id)
    refreshProject(projectId)
    return true
  } catch (error) {
    reportError(error, 'Delete failed')
    return false
  } finally {
    end()
  }
}

export async function addBookmark(
  recordingId: string,
  start: number,
  end: number | null,
  label: string,
  color = 'amber',
): Promise<void> {
  let current: Bookmark | null = null
  const create = async () => {
    const done = beginSave()
    try {
      const { bookmark } = await recordingsApi.addBookmark(recordingId, {
        start_s: start,
        end_s: end,
        label,
        color,
      })
      current = bookmark
      invalidate(keys.bookmarks(recordingId))
    } finally {
      done()
    }
  }
  const remove = async () => {
    if (!current) return
    const done = beginSave()
    try {
      await recordingsApi.removeBookmark(current.id)
      invalidate(keys.bookmarks(recordingId))
    } finally {
      done()
    }
  }
  try {
    await create()
    pushUndo({ label: 'Add bookmark', undo: remove, redo: create })
  } catch (error) {
    reportError(error, 'Bookmark was not saved')
  }
}

export async function removeBookmark(bookmark: Bookmark): Promise<void> {
  let current = bookmark
  const remove = async () => {
    const done = beginSave()
    try {
      await recordingsApi.removeBookmark(current.id)
      invalidate(keys.bookmarks(bookmark.recording_id))
    } finally {
      done()
    }
  }
  const restore = async () => {
    const done = beginSave()
    try {
      const { bookmark: created } = await recordingsApi.addBookmark(bookmark.recording_id, {
        start_s: bookmark.start_s,
        end_s: bookmark.end_s,
        label: bookmark.label,
        color: bookmark.color,
      })
      current = created
      invalidate(keys.bookmarks(bookmark.recording_id))
    } finally {
      done()
    }
  }
  try {
    await remove()
    pushUndo({ label: 'Delete bookmark', undo: restore, redo: remove })
  } catch (error) {
    reportError(error, 'Bookmark was not deleted')
  }
}

export async function renameBookmark(bookmark: Bookmark, label: string): Promise<void> {
  const apply = async (value: string) => {
    const done = beginSave()
    try {
      await recordingsApi.updateBookmark(bookmark.id, { label: value })
      invalidate(keys.bookmarks(bookmark.recording_id))
    } finally {
      done()
    }
  }
  try {
    await apply(label)
    pushUndo({ label: 'Rename bookmark', undo: () => apply(bookmark.label), redo: () => apply(label) })
  } catch (error) {
    reportError(error, 'Bookmark was not renamed')
  }
}

export function loopRegion(region: Region | null): void {
  setLoop(region, region !== null)
  engine.setLoop(region)
}

export function toggleLoop(): void {
  const { loop, loopEnabled, region, selection } = useWorkspace.getState()
  const target = region ?? (selection ? { start: selection.start, end: selection.end } : null)
  if (
    target &&
    (!loop || Math.abs(loop.start - target.start) > 1e-3 || Math.abs(loop.end - target.end) > 1e-3)
  ) {
    loopRegion(target)
    return
  }
  if (loop) {
    const enabled = !loopEnabled
    useWorkspace.setState({ loopEnabled: enabled })
    engine.setLoop(enabled ? loop : null)
  }
}

export function layersFor(names: string[]): LayerId[] {
  const out = new Set<LayerId>()
  for (const name of names) for (const layer of BACKEND_LAYER_MAP[name] ?? []) out.add(layer)
  return [...out]
}

export function applyFocus(focus: NextFocus, mode: ViewMode): void {
  const loop = focus.loop
  if (loop) {
    const region = { start: loop.ref_start, end: loop.ref_end }
    useWorkspace.setState({ region, focusKey: focus.finding_key })
    loopRegion(region)
    if (loop.segment_id) {
      select({
        kind: 'segment',
        level: loop.segment_id.startsWith('nt')
          ? 'note'
          : loop.segment_id.startsWith('sy')
            ? 'syllable'
            : loop.segment_id.startsWith('wd')
              ? 'word'
              : 'phrase',
        refId: loop.segment_id,
        takeId: loop.user_segment_id,
        start: loop.focus_start,
        end: loop.focus_end,
        label: loop.label,
      })
    }
    fitRange(region.start, region.end, 0.15)
    engine.seek(region.start)
  }
  const show = layersFor(focus.show_layers)
  const hide = layersFor(focus.hide_layers).filter((layer) => !show.includes(layer))
  const patch: Partial<Record<LayerId, boolean>> = {}
  for (const layer of LAYERS) {
    if (layer.id === 'lyrics' || layer.id === 'heatmap') continue
    if (show.includes(layer.id)) patch[layer.id] = true
    else if (hide.includes(layer.id)) patch[layer.id] = false
  }
  patch.lyrics = true
  setLayers(mode, patch)
  setUi({ coachOpen: true, inspectorOpen: true })
  useWorkspace.setState({ focusKey: focus.finding_key })
}

export async function realignRegion(
  projectId: string,
  comparisonId: string,
  takeId: string,
  region: Region,
): Promise<void> {
  const result = await attempt(
    () => comparisonsApi.realign(comparisonId, region.start, region.end),
    'Realignment could not start',
  )
  if (!result) return
  try {
    await waitForTask(result.task)
    refreshTake(takeId)
    refreshProject(projectId)
    invalidate((key) => key.startsWith('alignment:') || key.startsWith('comparison:'))
    pushToast({
      kind: 'success',
      title: 'Region realigned',
      body: 'The comparison was updated with the new alignment anchors.',
    })
  } catch {
    return
  }
}

export function openProject(projectId: string, take?: string, ref?: string): void {
  navigate({ name: 'project', projectId, tab: 'compare', take, ref })
}
