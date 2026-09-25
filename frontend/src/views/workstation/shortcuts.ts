import { useEffect } from 'react'
import { engine } from '../../audio/engine'
import { fitAll, fitRange, zoomAround } from '../../components/timeline/viewport'
import { segmentAt } from '../../lib/analysis'
import type { ViewMode } from '../../state/prefs'
import { useUi } from '../../state/ui'
import { select, useWorkspace } from '../../state/workspace'
import { addBookmark, applyFocus, toggleLoop } from './actions'
import { openWhy } from './coach/whyStore'
import { openRecorder } from './recordStore'
import type { WorkstationData } from './useWorkstation'

export function isTyping(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null
  if (!element) return false
  if (element.isContentEditable) return true
  const tag = element.tagName
  if (tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (tag === 'INPUT') {
    const type = (element as HTMLInputElement).type
    return !['checkbox', 'radio', 'range', 'button'].includes(type)
  }
  return false
}

function stepSegment(data: WorkstationData, level: 'note' | 'phrase', direction: 1 | -1): void {
  const list = data.refIndex?.byLevel[level] ?? []
  if (!list.length) return
  const t = engine.position()
  const index =
    direction > 0
      ? list.findIndex((s) => s.start_s > t + 0.02)
      : [...list].reverse().findIndex((s) => s.start_s < t - 0.05)
  const target = direction > 0 ? list[index] : index >= 0 ? list[list.length - 1 - index] : undefined
  if (!target) return
  engine.seek(target.start_s)
  select({
    kind: 'segment',
    level,
    refId: target.id,
    takeId: data.cindex?.refToUser.get(target.id) ?? null,
    start: target.start_s,
    end: target.end_s,
    label: target.label,
  })
  const view = useWorkspace.getState().view
  if (target.start_s < view.start || target.end_s > view.end)
    fitRange(target.start_s, target.end_s, level === 'note' ? 2 : 0.1)
}

export function useWorkstationShortcuts(data: WorkstationData, mode: ViewMode, enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || isTyping(event.target)) return
      if (event.ctrlKey || event.metaKey || event.altKey) return
      if (document.querySelector('.dialog-layer')) return
      if (useUi.getState().paletteOpen) return
      const key = event.key
      const workspace = useWorkspace.getState()
      switch (key) {
        case ' ':
          event.preventDefault()
          engine.toggle()
          break
        case 'r':
        case 'R':
          event.preventDefault()
          openRecorder(workspace.loopEnabled ? workspace.loop : workspace.region)
          break
        case 'l':
        case 'L':
          event.preventDefault()
          toggleLoop()
          break
        case 'a':
        case 'A':
          event.preventDefault()
          engine.toggleAB()
          break
        case 'f':
          event.preventDefault()
          if (workspace.region) fitRange(workspace.region.start, workspace.region.end)
          else if (workspace.selection) fitRange(workspace.selection.start, workspace.selection.end, 0.5)
          else fitAll()
          break
        case 'F':
          event.preventDefault()
          fitAll()
          break
        case '+':
        case '=':
          event.preventDefault()
          zoomAround(1 / 1.6, engine.position(), true)
          break
        case '-':
        case '_':
          event.preventDefault()
          zoomAround(1.6, engine.position(), true)
          break
        case 'ArrowLeft':
          event.preventDefault()
          engine.seek(engine.position() - (event.shiftKey ? 0.1 : 1))
          break
        case 'ArrowRight':
          event.preventDefault()
          engine.seek(engine.position() + (event.shiftKey ? 0.1 : 1))
          break
        case 'Home':
          event.preventDefault()
          engine.seek(0)
          break
        case 'End':
          event.preventDefault()
          engine.seek(engine.timelineDuration())
          break
        case 'Escape':
          useWorkspace.setState({ region: null, selection: null, ruler: null, rulerActive: false })
          break
        case 'b':
        case 'B':
          if (data.reference) {
            event.preventDefault()
            void addBookmark(
              data.reference.id,
              workspace.region?.start ?? engine.position(),
              workspace.region?.end ?? null,
              'Bookmark',
            )
          }
          break
        case 'w':
        case 'W': {
          const target =
            workspace.region ??
            (workspace.selection ? { start: workspace.selection.start, end: workspace.selection.end } : null)
          if (target && data.comparison) {
            event.preventDefault()
            openWhy(target)
          }
          break
        }
        case 'n':
        case 'N':
          if (data.comparison?.coaching.next_focus) {
            event.preventDefault()
            applyFocus(data.comparison.coaching.next_focus, mode)
          }
          break
        case '.':
          event.preventDefault()
          stepSegment(data, 'note', 1)
          break
        case ',':
          event.preventDefault()
          stepSegment(data, 'note', -1)
          break
        case ']':
          event.preventDefault()
          stepSegment(data, 'phrase', 1)
          break
        case '[':
          event.preventDefault()
          stepSegment(data, 'phrase', -1)
          break
        case 'p':
        case 'P': {
          const phrase = data.refIndex ? segmentAt(data.refIndex.byLevel.phrase, engine.position()) : null
          if (phrase) {
            event.preventDefault()
            useWorkspace.setState({ region: { start: phrase.start_s, end: phrase.end_s } })
            fitRange(phrase.start_s, phrase.end_s, 0.1)
          }
          break
        }
        default:
          break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [data, mode, enabled])
}
