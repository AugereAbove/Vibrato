import { pickPeakLevel, type PeakPyramid } from '../../../api/binary'
import { takeTime, type TimelineModel } from '../model'
import { tOf, type Viewport } from '../viewport'
import type { CanvasSize } from '../useCanvas'
import { withAlpha } from '../useCanvas'
import type { Palette } from './palette'

function columns(
  peaks: PeakPyramid,
  view: Viewport,
  width: number,
  mapTime: (t: number) => number,
): { min: Float32Array; max: Float32Array } {
  const count = Math.max(1, Math.ceil(width))
  const min = new Float32Array(count)
  const max = new Float32Array(count)
  const secondsPerPixel = (view.end - view.start) / Math.max(1, width)
  const level = pickPeakLevel(peaks, secondsPerPixel * peaks.sampleRate)
  const factor = peaks.sampleRate / level.samplesPerPeak
  const data = level.data
  for (let px = 0; px < count; px += 1) {
    const t0 = mapTime(tOf(view, px))
    const t1 = mapTime(tOf(view, px + 1))
    let i0 = Math.floor(Math.min(t0, t1) * factor)
    let i1 = Math.ceil(Math.max(t0, t1) * factor)
    if (i1 <= 0 || i0 >= level.count) continue
    i0 = Math.max(0, i0)
    i1 = Math.min(level.count, Math.max(i0 + 1, i1))
    let lo = 32767
    let hi = -32768
    for (let i = i0; i < i1; i += 1) {
      const a = data[2 * i]
      const b = data[2 * i + 1]
      if (a < lo) lo = a
      if (b > hi) hi = b
    }
    min[px] = lo / 32767
    max[px] = hi / 32767
  }
  return { min, max }
}

function fillBand(
  ctx: CanvasRenderingContext2D,
  min: Float32Array,
  max: Float32Array,
  mid: number,
  half: number,
  color: string,
  alpha: number,
): void {
  ctx.beginPath()
  ctx.moveTo(0, mid - max[0] * half)
  for (let x = 1; x < max.length; x += 1) ctx.lineTo(x, mid - max[x] * half)
  for (let x = min.length - 1; x >= 0; x -= 1) ctx.lineTo(x, mid - min[x] * half)
  ctx.closePath()
  ctx.fillStyle = withAlpha(color, alpha)
  ctx.fill()
}

export function drawWaveform(
  ctx: CanvasRenderingContext2D,
  size: CanvasSize,
  view: Viewport,
  model: TimelineModel,
  p: Palette,
  mode: 'stacked' | 'overlay',
): void {
  const { width, height } = size
  const identity = (t: number) => t
  const takeMap = (t: number) => takeTime(model, t)
  const refPeaks = model.ref?.peaks ?? null
  const takePeaks = model.take?.peaks ?? null
  ctx.strokeStyle = p.grid
  ctx.lineWidth = 1
  if (mode === 'stacked' && takePeaks) {
    const half = height / 4 - 3
    ctx.beginPath()
    ctx.moveTo(0, height / 4 + 0.5)
    ctx.lineTo(width, height / 4 + 0.5)
    ctx.moveTo(0, (3 * height) / 4 + 0.5)
    ctx.lineTo(width, (3 * height) / 4 + 0.5)
    ctx.stroke()
    ctx.fillStyle = p.border
    ctx.fillRect(0, height / 2, width, 1)
    if (refPeaks) {
      const { min, max } = columns(refPeaks, view, width, identity)
      fillBand(ctx, min, max, height / 4, half, p.ref, 0.85)
    }
    const { min, max } = columns(takePeaks, view, width, takeMap)
    fillBand(ctx, min, max, (3 * height) / 4, half, p.take, 0.85)
    ctx.font = `600 9px ${p.font}`
    ctx.fillStyle = withAlpha(p.ref, 0.9)
    ctx.fillText('REF', 6, 12)
    ctx.fillStyle = withAlpha(p.take, 0.9)
    ctx.fillText('TAKE', 6, height / 2 + 12)
    return
  }
  const half = height / 2 - 4
  ctx.beginPath()
  ctx.moveTo(0, height / 2 + 0.5)
  ctx.lineTo(width, height / 2 + 0.5)
  ctx.stroke()
  if (refPeaks) {
    const { min, max } = columns(refPeaks, view, width, identity)
    fillBand(ctx, min, max, height / 2, half, p.ref, takePeaks ? 0.55 : 0.85)
  }
  if (takePeaks) {
    const { min, max } = columns(takePeaks, view, width, takeMap)
    fillBand(ctx, min, max, height / 2, half, p.take, 0.55)
  }
}

export function drawMiniWave(
  ctx: CanvasRenderingContext2D,
  size: CanvasSize,
  peaks: PeakPyramid,
  duration: number,
  color: string,
): void {
  const view = { start: 0, end: duration, width: size.width }
  const { min, max } = columns(peaks, view, size.width, (t) => t)
  fillBand(ctx, min, max, size.height / 2, size.height / 2 - 2, color, 0.55)
}
