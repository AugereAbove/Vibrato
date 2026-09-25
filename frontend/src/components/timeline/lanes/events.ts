import type { AnalysisEvent, Segment } from '../../../api/types'
import type { Selection } from '../../../state/workspace'
import { takeToTimeline, type TimelineModel, type TrackData } from '../model'
import { xOf, type Viewport } from '../viewport'
import type { CanvasSize } from '../useCanvas'
import { withAlpha } from '../useCanvas'
import { roundRect, type Palette } from './palette'

export const EVENT_LABELS: Record<string, string> = {
  breath: 'Breath',
  vibrato: 'Vibrato',
  scoop_up: 'Scoop up',
  scoop_down: 'Scoop down',
  onset: 'Phrase onset',
  pitch_attack: 'Pitch attack',
  portamento: 'Glide',
  consonant: 'Consonant',
  roughness: 'Roughness',
  fry: 'Vocal fry',
  subharmonic: 'Subharmonics',
  irregular: 'Irregular voicing',
  register_shift: 'Register change',
  sustained_vowel: 'Sustained vowel',
}

const SKIP = new Set(['sustained_vowel'])

function colorFor(type: string, p: Palette): string {
  switch (type) {
    case 'breath':
      return p.categories.breath
    case 'vibrato':
      return p.categories.vibrato
    case 'scoop_up':
    case 'scoop_down':
    case 'pitch_attack':
    case 'portamento':
      return p.categories.pitch
    case 'consonant':
      return p.categories.articulation
    case 'onset':
      return p.text2
    default:
      return p.bad
  }
}

function drawRow(
  ctx: CanvasRenderingContext2D,
  events: AnalysisEvent[],
  map: (u: number) => number,
  view: Viewport,
  top: number,
  rowHeight: number,
  p: Palette,
  selectedId: string | null,
): void {
  const width = view.width
  const pps = view.width / (view.end - view.start)
  const mid = top + rowHeight / 2
  for (const event of events) {
    if (SKIP.has(event.type)) continue
    if (event.type === 'consonant' && pps < 60) continue
    const x0 = xOf(view, map(event.start_s))
    const x1 = xOf(view, map(event.end_s))
    if (x1 < -4 || x0 > width + 4) continue
    const color = colorFor(event.type, p)
    const alpha = 0.35 + 0.65 * Math.max(0, Math.min(1, event.confidence))
    const selected = event.id === selectedId
    ctx.globalAlpha = alpha
    switch (event.type) {
      case 'breath': {
        roundRect(ctx, x0, mid - 6, Math.max(4, x1 - x0), 12, 6)
        ctx.fillStyle = withAlpha(color, 0.35)
        ctx.fill()
        ctx.strokeStyle = color
        ctx.lineWidth = selected ? 2 : 1
        ctx.stroke()
        if (x1 - x0 > 38) {
          ctx.globalAlpha = 1
          ctx.fillStyle = p.text1
          ctx.font = `600 9px ${p.font}`
          ctx.textBaseline = 'middle'
          ctx.fillText('breath', x0 + 6, mid + 0.5)
        }
        break
      }
      case 'vibrato': {
        ctx.strokeStyle = color
        ctx.lineWidth = selected ? 2 : 1.3
        ctx.beginPath()
        const rate = typeof event.props.rate_hz === 'number' ? event.props.rate_hz : 5.5
        const cycles = Math.max(1, (event.end_s - event.start_s) * rate)
        const samples = Math.max(8, Math.min(400, Math.round(x1 - x0)))
        for (let i = 0; i <= samples; i += 1) {
          const f = i / samples
          const x = x0 + (x1 - x0) * f
          const yy = mid + Math.sin(f * cycles * Math.PI * 2) * 4
          if (i === 0) ctx.moveTo(x, yy)
          else ctx.lineTo(x, yy)
        }
        ctx.stroke()
        break
      }
      case 'scoop_up':
      case 'scoop_down': {
        const up = event.type === 'scoop_up'
        ctx.strokeStyle = color
        ctx.fillStyle = color
        ctx.lineWidth = 1.5
        ctx.beginPath()
        ctx.moveTo(x0, up ? mid + 6 : mid - 6)
        ctx.quadraticCurveTo(x0 + 2, mid, Math.max(x0 + 6, x1), up ? mid - 5 : mid + 5)
        ctx.stroke()
        break
      }
      case 'onset':
      case 'pitch_attack': {
        ctx.fillStyle = color
        ctx.fillRect(x0 - 0.75, mid - 7, 1.5, 14)
        ctx.beginPath()
        ctx.moveTo(x0, mid - 7)
        ctx.lineTo(x0 + 5, mid - 4)
        ctx.lineTo(x0, mid - 1)
        ctx.closePath()
        ctx.fill()
        break
      }
      case 'portamento': {
        ctx.strokeStyle = color
        ctx.lineWidth = 1.5
        ctx.beginPath()
        ctx.moveTo(x0, mid + 5)
        ctx.lineTo(Math.max(x0 + 4, x1), mid - 5)
        ctx.stroke()
        break
      }
      case 'consonant': {
        ctx.fillStyle = withAlpha(color, 0.55)
        ctx.fillRect(x0, mid - 3, Math.max(1.5, x1 - x0), 6)
        break
      }
      default: {
        ctx.fillStyle = color
        ctx.beginPath()
        ctx.arc((x0 + x1) / 2, mid, selected ? 5 : 3.5, 0, Math.PI * 2)
        ctx.fill()
      }
    }
    if (selected) {
      ctx.globalAlpha = 1
      ctx.strokeStyle = p.accent
      ctx.lineWidth = 1.5
      roundRect(ctx, x0 - 3, top + 2, Math.max(8, x1 - x0 + 6), rowHeight - 4, 4)
      ctx.stroke()
    }
  }
  ctx.globalAlpha = 1
}

export function drawEvents(
  ctx: CanvasRenderingContext2D,
  size: CanvasSize,
  view: Viewport,
  model: TimelineModel,
  p: Palette,
  selected: { side: 'ref' | 'take'; id: string } | null,
): void {
  const { width, height } = size
  const rows = model.take ? 2 : 1
  const rowHeight = height / rows
  ctx.fillStyle = p.border
  if (rows === 2) ctx.fillRect(0, rowHeight, width, 1)
  if (model.ref?.analysis) {
    drawRow(
      ctx,
      model.ref.analysis.events,
      (u) => u,
      view,
      0,
      rowHeight,
      p,
      selected?.side === 'ref' ? selected.id : null,
    )
  }
  if (model.take?.analysis) {
    drawRow(
      ctx,
      model.take.analysis.events,
      (u) => takeToTimeline(model, u),
      view,
      rowHeight,
      rowHeight,
      p,
      selected?.side === 'take' ? selected.id : null,
    )
  }
}

export function hitEvent(
  model: TimelineModel,
  view: Viewport,
  x: number,
  y: number,
  height: number,
): Selection | null {
  const rows = model.take ? 2 : 1
  const side: 'ref' | 'take' = rows === 2 && y > height / 2 ? 'take' : 'ref'
  const track: TrackData | null = side === 'take' ? model.take : model.ref
  if (!track?.analysis) return null
  const map = side === 'take' ? (u: number) => takeToTimeline(model, u) : (u: number) => u
  const pps = view.width / (view.end - view.start)
  let best: AnalysisEvent | null = null
  let distance = 8
  for (const event of track.analysis.events) {
    if (SKIP.has(event.type) || (event.type === 'consonant' && pps < 60)) continue
    const x0 = xOf(view, map(event.start_s))
    const x1 = xOf(view, map(event.end_s))
    const d = x < x0 ? x0 - x : x > x1 ? x - x1 : 0
    if (d < distance) {
      distance = d
      best = event
    }
  }
  if (!best) return null
  return {
    kind: 'event',
    side,
    eventId: best.id,
    type: best.type,
    start: map(best.start_s),
    end: map(best.end_s),
    label: EVENT_LABELS[best.type] ?? best.type,
  }
}

export function phonemeColor(cls: string | undefined, p: Palette): string {
  switch (cls) {
    case 'vowel':
      return p.categories.vowel
    case 'nasal':
      return p.categories.breath
    case 'fricative':
    case 'sibilant':
      return p.categories.articulation
    case 'stop':
    case 'plosive':
    case 'affricate':
      return p.categories.dynamics
    case 'aspirate':
      return p.categories.timbre
    case 'approximant':
    case 'liquid':
    case 'glide':
      return p.categories.vibrato
    default:
      return p.text3
  }
}

function drawPhonemeRow(
  ctx: CanvasRenderingContext2D,
  segments: Segment[],
  map: (u: number) => number,
  view: Viewport,
  top: number,
  rowHeight: number,
  p: Palette,
  selectedId: string | null,
): void {
  ctx.font = `600 9.5px ${p.mono}`
  ctx.textBaseline = 'middle'
  for (const segment of segments) {
    const x0 = xOf(view, map(segment.start_s))
    const x1 = xOf(view, map(segment.end_s))
    if (x1 < 0 || x0 > view.width) continue
    const cls = typeof segment.props.phoneme_class === 'string' ? segment.props.phoneme_class : undefined
    const color = phonemeColor(cls, p)
    const selected = segment.id === selectedId
    roundRect(ctx, x0 + 0.5, top + 3, Math.max(1.5, x1 - x0 - 1), rowHeight - 6, 3)
    ctx.fillStyle = withAlpha(color, selected ? 0.5 : 0.22 + 0.25 * segment.confidence)
    ctx.fill()
    if (selected) {
      ctx.strokeStyle = p.accent
      ctx.lineWidth = 1.5
      ctx.stroke()
    }
    if (x1 - x0 > 16) {
      ctx.fillStyle = p.text1
      ctx.fillText(segment.label, x0 + 4, top + rowHeight / 2)
    }
  }
}

export function drawPhonemes(
  ctx: CanvasRenderingContext2D,
  size: CanvasSize,
  view: Viewport,
  model: TimelineModel,
  p: Palette,
  selected: { ref: string | null; take: string | null },
): void {
  const rows = model.take ? 2 : 1
  const rowHeight = size.height / rows
  if (model.ref?.analysis) {
    drawPhonemeRow(ctx, model.ref.analysis.byLevel.phoneme, (u) => u, view, 0, rowHeight, p, selected.ref)
  }
  if (model.take?.analysis) {
    drawPhonemeRow(
      ctx,
      model.take.analysis.byLevel.phoneme,
      (u) => takeToTimeline(model, u),
      view,
      rowHeight,
      rowHeight,
      p,
      selected.take,
    )
  }
}

export function hitPhoneme(
  model: TimelineModel,
  view: Viewport,
  x: number,
  y: number,
  height: number,
): Selection | null {
  const rows = model.take ? 2 : 1
  const side: 'ref' | 'take' = rows === 2 && y > height / 2 ? 'take' : 'ref'
  const track = side === 'take' ? model.take : model.ref
  if (!track?.analysis) return null
  const map = side === 'take' ? (u: number) => takeToTimeline(model, u) : (u: number) => u
  for (const segment of track.analysis.byLevel.phoneme) {
    const x0 = xOf(view, map(segment.start_s))
    const x1 = xOf(view, map(segment.end_s))
    if (x >= x0 && x <= x1) {
      return {
        kind: 'segment',
        level: 'phoneme',
        refId: side === 'ref' ? segment.id : null,
        takeId: side === 'take' ? segment.id : null,
        start: map(segment.start_s),
        end: map(segment.end_s),
        label: segment.label,
      }
    }
  }
  return null
}
