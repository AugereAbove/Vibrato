import type { FeatureBundle } from '../../../api/binary'
import { takeTime, takeToTimeline, type TimelineModel } from '../model'
import { xOf, type Viewport } from '../viewport'
import type { CanvasSize } from '../useCanvas'
import { withAlpha } from '../useCanvas'
import type { Palette } from './palette'

interface CurveSpec {
  track: string
  low: number
  high: number
  label: string
  unit: string
  gridValues: number[]
}

function curvePath(
  ctx: CanvasRenderingContext2D,
  features: FeatureBundle,
  name: string,
  view: Viewport,
  y: (v: number) => number,
  toTimeline: (u: number) => number,
  fromTimeline: (t: number) => number,
  requireVoiced: boolean,
): { first: number; last: number } | null {
  const values = features.tracks[name]
  if (!values) return null
  const voiced = features.tracks.voiced
  const hop = features.hopS
  const i0 = Math.max(0, Math.floor(fromTimeline(view.start) / hop) - 1)
  const i1 = Math.min(values.length - 1, Math.ceil(fromTimeline(view.end) / hop) + 1)
  const stride = Math.max(1, Math.floor((i1 - i0) / (view.width * 2)))
  let open = false
  let first = -1
  let last = -1
  for (let i = i0; i <= i1; i += stride) {
    const v = values[i]
    if (!Number.isFinite(v) || (requireVoiced && voiced && voiced[i] < 0.5)) {
      open = false
      continue
    }
    const x = xOf(view, toTimeline(i * hop))
    const yy = y(v)
    if (!open) {
      ctx.moveTo(x, yy)
      open = true
      if (first < 0) first = x
    } else {
      ctx.lineTo(x, yy)
    }
    last = x
  }
  return first < 0 ? null : { first, last }
}

export function drawCurves(
  ctx: CanvasRenderingContext2D,
  size: CanvasSize,
  view: Viewport,
  model: TimelineModel,
  p: Palette,
  spec: CurveSpec,
  requireVoiced: boolean,
): void {
  const { width, height } = size
  const y = (v: number) =>
    height -
    4 -
    ((Math.max(spec.low, Math.min(spec.high, v)) - spec.low) / (spec.high - spec.low)) * (height - 8)
  ctx.font = `500 9px ${p.mono}`
  ctx.textBaseline = 'middle'
  for (const value of spec.gridValues) {
    const yy = Math.round(y(value)) + 0.5
    ctx.strokeStyle = p.grid
    ctx.beginPath()
    ctx.moveTo(0, yy)
    ctx.lineTo(width, yy)
    ctx.stroke()
    ctx.fillStyle = p.text3
    ctx.fillText(`${value}`, 4, yy - 6)
  }
  const ref = model.ref?.features
  const take = model.take?.features
  if (ref) {
    ctx.beginPath()
    const span = curvePath(
      ctx,
      ref,
      spec.track,
      view,
      y,
      (u) => u,
      (t) => t,
      requireVoiced,
    )
    if (span && !requireVoiced) {
      ctx.lineTo(span.last, height)
      ctx.lineTo(span.first, height)
      ctx.closePath()
      ctx.fillStyle = withAlpha(p.ref, 0.12)
      ctx.fill()
      ctx.beginPath()
      curvePath(
        ctx,
        ref,
        spec.track,
        view,
        y,
        (u) => u,
        (t) => t,
        requireVoiced,
      )
    }
    ctx.strokeStyle = withAlpha(p.ref, 0.95)
    ctx.lineWidth = 1.4
    ctx.stroke()
  }
  if (take) {
    ctx.beginPath()
    curvePath(
      ctx,
      take,
      spec.track,
      view,
      y,
      (u) => takeToTimeline(model, u),
      (t) => takeTime(model, t),
      requireVoiced,
    )
    ctx.strokeStyle = withAlpha(p.take, 0.95)
    ctx.lineWidth = 1.4
    ctx.stroke()
  }
  ctx.font = `600 9px ${p.font}`
  ctx.fillStyle = p.text3
  ctx.fillText(
    `${spec.label} (${spec.unit})`,
    width - 8 - ctx.measureText(`${spec.label} (${spec.unit})`).width,
    9,
  )
}

export const LOUDNESS_SPEC: CurveSpec = {
  track: 'level_rel_db',
  low: -48,
  high: 8,
  label: 'Level relative to singing level',
  unit: 'dB',
  gridValues: [0, -12, -24, -36],
}

export const VOICE_SPEC: CurveSpec = {
  track: 'cpps_db',
  low: 0,
  high: 30,
  label: 'Cepstral peak prominence',
  unit: 'dB',
  gridValues: [10, 20],
}

export function sampleTrack(
  features: FeatureBundle | null | undefined,
  name: string,
  time: number,
): number | null {
  if (!features) return null
  const values = features.tracks[name]
  if (!values) return null
  const index = Math.round(time / features.hopS)
  if (index < 0 || index >= values.length) return null
  const value = values[index]
  return Number.isFinite(value) ? value : null
}
