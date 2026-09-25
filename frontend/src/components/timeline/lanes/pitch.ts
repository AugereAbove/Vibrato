import type { Finding, Segment } from '../../../api/types'
import { resultFor, numberValue } from '../../../lib/analysis'
import { isBlackKey, noteName } from '../../../lib/music'
import type { Selection } from '../../../state/workspace'
import { takeTime, takeToTimeline, type TimelineModel, type TrackData } from '../model'
import { xOf, type Viewport } from '../viewport'
import type { CanvasSize } from '../useCanvas'
import { withAlpha } from '../useCanvas'
import { roundRect, type Palette } from './palette'

export interface PitchRange {
  low: number
  high: number
}

function hzToMidi(hz: number): number {
  return 69 + 12 * Math.log2(hz / 440)
}

function voicedMidis(track: TrackData | null, shift: number, out: number[]): void {
  const f0 = track?.features?.tracks.f0_hz
  if (!f0) return
  for (let i = 0; i < f0.length; i += 3) {
    const hz = f0[i]
    if (Number.isFinite(hz) && hz > 30) out.push(hzToMidi(hz) - shift)
  }
}

export function autoPitchRange(model: TimelineModel): PitchRange {
  const values: number[] = []
  voicedMidis(model.ref, 0, values)
  voicedMidis(model.take, model.transposition, values)
  if (values.length < 10) return { low: 48, high: 72 }
  values.sort((a, b) => a - b)
  const low = values[Math.floor(values.length * 0.02)]
  const high = values[Math.floor(values.length * 0.98)]
  const center = (low + high) / 2
  const span = Math.max(12, high - low + 5)
  return { low: Math.floor(center - span / 2), high: Math.ceil(center + span / 2) }
}

export function noteCenter(track: TrackData, note: Segment): number | null {
  const result = resultFor(track.analysis, 'pitch', note.id)
  const value = numberValue(result, 'center_midi')
  if (value !== null) return value
  const prop = note.props.center_midi
  return typeof prop === 'number' ? prop : null
}

export interface PitchOptions {
  selectedRef: string | null
  selectedTake: string | null
  showNoteNames: boolean
  reveal: number
  focus: Finding | null
  showArrows: boolean
  showVibrato: boolean
}

function drawContour(
  ctx: CanvasRenderingContext2D,
  track: TrackData,
  view: Viewport,
  y: (midi: number) => number,
  toTimeline: (u: number) => number,
  fromTimeline: (t: number) => number,
  color: string,
  shift: number,
  limitX: number,
  lineWidth: number,
): void {
  const features = track.features
  if (!features) return
  const f0 = features.tracks.f0_hz
  const conf = features.tracks.f0_conf
  if (!f0) return
  const hop = features.hopS
  const i0 = Math.max(0, Math.floor(fromTimeline(view.start) / hop) - 2)
  const i1 = Math.min(f0.length - 1, Math.ceil(fromTimeline(view.end) / hop) + 2)
  const buckets = [0.2, 0.45, 0.7, 1]
  ctx.lineWidth = lineWidth
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'
  for (let b = 0; b < buckets.length; b += 1) {
    const lower = b === 0 ? -1 : buckets[b - 1]
    const upper = buckets[b]
    ctx.strokeStyle = withAlpha(color, 0.22 + 0.78 * upper)
    ctx.beginPath()
    let open = false
    for (let i = i0 + 1; i <= i1; i += 1) {
      const a = f0[i - 1]
      const hz = f0[i]
      if (!(a > 30) || !(hz > 30)) {
        open = false
        continue
      }
      const x = xOf(view, toTimeline(i * hop))
      if (x > limitX) break
      const c = conf ? Math.min(conf[i - 1], conf[i]) : 1
      const yy = y(hzToMidi(hz) - shift)
      if (c > lower && c <= upper) {
        if (!open) {
          const x0 = xOf(view, toTimeline((i - 1) * hop))
          ctx.moveTo(x0, y(hzToMidi(a) - shift))
          open = true
        }
        ctx.lineTo(x, yy)
      } else {
        open = false
      }
    }
    ctx.stroke()
  }
}

export function drawPitch(
  ctx: CanvasRenderingContext2D,
  size: CanvasSize,
  view: Viewport,
  model: TimelineModel,
  p: Palette,
  range: PitchRange,
  options: PitchOptions,
): void {
  const { width, height } = size
  const span = Math.max(1, range.high - range.low)
  const y = (midi: number) => height - ((midi - range.low) / span) * height
  const semitone = height / span
  for (let midi = Math.floor(range.low); midi <= Math.ceil(range.high); midi += 1) {
    const top = y(midi + 0.5)
    if (isBlackKey(midi)) {
      ctx.fillStyle = p.pianoBlack
      ctx.fillRect(0, top, width, semitone)
    }
    if (((midi % 12) + 12) % 12 === 0) {
      ctx.fillStyle = p.gridStrong
      ctx.fillRect(0, Math.round(y(midi - 0.5)), width, 1)
    }
  }
  if (semitone >= 9) {
    ctx.font = `500 9px ${p.mono}`
    ctx.fillStyle = p.text3
    ctx.textBaseline = 'middle'
    for (let midi = Math.ceil(range.low); midi <= Math.floor(range.high); midi += 1) {
      const pc = ((midi % 12) + 12) % 12
      if (semitone < 14 && pc !== 0 && pc !== 7) continue
      ctx.fillText(noteName(midi), 4, y(midi))
    }
  }
  const limit = options.reveal >= 1 ? Infinity : options.reveal * width
  const ref = model.ref
  const take = model.take
  const toTakeTimeline = (u: number) => takeToTimeline(model, u)
  const fromTakeTimeline = (t: number) => takeTime(model, t)
  const noteHeight = Math.max(4, semitone * 0.8)
  const drawNotes = (
    track: TrackData,
    map: (u: number) => number,
    color: string,
    shift: number,
    filled: boolean,
    selected: string | null,
  ) => {
    const notes = track.analysis?.byLevel.note ?? []
    for (const note of notes) {
      const center = noteCenter(track, note)
      if (center === null) continue
      const x0 = xOf(view, map(note.start_s))
      const x1 = xOf(view, map(note.end_s))
      if (x1 < 0 || x0 > width) continue
      const yy = y(center - shift)
      roundRect(ctx, x0, yy - noteHeight / 2, Math.max(2, x1 - x0), noteHeight, Math.min(4, noteHeight / 2))
      if (filled) {
        ctx.fillStyle = withAlpha(color, 0.14)
        ctx.fill()
      }
      const isSelected = selected === note.id
      ctx.strokeStyle = withAlpha(color, isSelected ? 1 : filled ? 0.45 : 0.6)
      ctx.lineWidth = isSelected ? 2 : 1
      if (!filled) ctx.setLineDash([3, 2])
      ctx.stroke()
      ctx.setLineDash([])
      if (isSelected) {
        ctx.save()
        ctx.shadowColor = p.accent
        ctx.shadowBlur = 12
        ctx.strokeStyle = withAlpha(p.accent, 0.8)
        ctx.stroke()
        ctx.restore()
      }
      if (options.showNoteNames && filled && x1 - x0 > 26 && semitone >= 6) {
        ctx.font = `600 9px ${p.mono}`
        ctx.fillStyle = withAlpha(p.text2, 0.9)
        ctx.textBaseline = 'bottom'
        ctx.fillText(noteName(center), x0 + 3, yy - noteHeight / 2 - 2)
      }
    }
  }
  if (options.showVibrato) {
    for (const [track, color, map] of [
      [ref, p.ref, (u: number) => u],
      [take, p.take, toTakeTimeline],
    ] as const) {
      if (!track?.analysis) continue
      for (const event of track.analysis.events) {
        if (event.type !== 'vibrato') continue
        const x0 = xOf(view, map(event.start_s))
        const x1 = xOf(view, map(event.end_s))
        if (x1 < 0 || x0 > width) continue
        ctx.fillStyle = withAlpha(color, 0.07)
        ctx.fillRect(x0, 0, x1 - x0, height)
      }
    }
  }
  if (ref) drawNotes(ref, (u) => u, p.ref, 0, true, options.selectedRef)
  if (take) drawNotes(take, toTakeTimeline, p.take, model.transposition, false, options.selectedTake)
  if (ref)
    drawContour(
      ctx,
      ref,
      view,
      y,
      (u) => u,
      (t) => t,
      p.ref,
      0,
      limit,
      take ? 3 : 2,
    )
  if (take)
    drawContour(ctx, take, view, y, toTakeTimeline, fromTakeTimeline, p.take, model.transposition, limit, 1.4)
  if (options.showArrows && model.comparison && ref && take) {
    ctx.font = `600 10px ${p.mono}`
    for (const metric of model.comparison.metrics) {
      if (metric.metric_id !== 'pitch.center') continue
      const z = Math.abs(metric.normalized ?? 0)
      if (
        z < 1 ||
        metric.confidence < 0.45 ||
        typeof metric.ref_value !== 'number' ||
        typeof metric.user_value !== 'number'
      )
        continue
      const x = xOf(view, (metric.ref_start + metric.ref_end) / 2)
      if (x < 0 || x > width || x > limit) continue
      const yRef = y(metric.ref_value / 100)
      const yTake = y(metric.user_value / 100 - model.transposition)
      const color = z >= 2 ? p.bad : p.warn
      ctx.strokeStyle = color
      ctx.fillStyle = color
      ctx.lineWidth = 1.6
      ctx.beginPath()
      ctx.moveTo(x, yTake)
      ctx.lineTo(x, yRef)
      ctx.stroke()
      const dir = yRef < yTake ? -1 : 1
      ctx.beginPath()
      ctx.moveTo(x, yRef)
      ctx.lineTo(x - 4, yRef - dir * 6)
      ctx.lineTo(x + 4, yRef - dir * 6)
      ctx.closePath()
      ctx.fill()
      const cents = metric.difference ?? 0
      ctx.textBaseline = 'middle'
      ctx.fillText(`${cents > 0 ? '+' : '−'}${Math.abs(cents).toFixed(0)}¢`, x + 6, (yRef + yTake) / 2)
    }
  }
  if (options.focus?.practice) {
    const region = options.focus.practice
    const x0 = xOf(view, region.focus_start)
    const x1 = xOf(view, region.focus_end)
    ctx.strokeStyle = withAlpha(p.accent, 0.8)
    ctx.setLineDash([5, 4])
    ctx.lineWidth = 1.2
    roundRect(ctx, x0, 2, Math.max(4, x1 - x0), height - 4, 6)
    ctx.stroke()
    ctx.setLineDash([])
  }
}

export function hitPitch(
  model: TimelineModel,
  view: Viewport,
  range: PitchRange,
  x: number,
  yPos: number,
  height: number,
): Selection | null {
  const span = Math.max(1, range.high - range.low)
  const midiAt = range.low + ((height - yPos) / height) * span
  const pick = (track: TrackData | null, map: (u: number) => number, shift: number) => {
    if (!track?.analysis) return null
    for (const note of track.analysis.byLevel.note) {
      const x0 = xOf(view, map(note.start_s))
      const x1 = xOf(view, map(note.end_s))
      if (x < x0 - 2 || x > x1 + 2) continue
      const center = noteCenter(track, note)
      if (center === null || Math.abs(center - shift - midiAt) > 1.2) continue
      return note
    }
    return null
  }
  const refNote = pick(model.ref, (u) => u, 0)
  const takeNote = refNote ? null : pick(model.take, (u) => takeToTimeline(model, u), model.transposition)
  const cindex = model.cindex
  if (refNote) {
    const takeId = cindex?.refToUser.get(refNote.id) ?? null
    return {
      kind: 'segment',
      level: 'note',
      refId: refNote.id,
      takeId,
      start: refNote.start_s,
      end: refNote.end_s,
      label: refNote.label,
    }
  }
  if (takeNote) {
    const refId = cindex?.userToRef.get(takeNote.id) ?? null
    const refSegment = refId ? model.ref?.analysis?.segments.get(refId) : null
    return {
      kind: 'segment',
      level: 'note',
      refId,
      takeId: takeNote.id,
      start: refSegment ? refSegment.start_s : takeToTimeline(model, takeNote.start_s),
      end: refSegment ? refSegment.end_s : takeToTimeline(model, takeNote.end_s),
      label: takeNote.label,
    }
  }
  return null
}
