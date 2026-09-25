import type { Anchor } from '../../../api/types'
import type { TimeMap } from '../../../lib/timemap'
import { ticks, xOf, type Viewport } from '../viewport'
import type { CanvasSize } from '../useCanvas'
import { withAlpha } from '../useCanvas'
import type { Palette } from './palette'

export function drawAlignment(
  ctx: CanvasRenderingContext2D,
  size: CanvasSize,
  view: Viewport,
  map: TimeMap,
  anchors: Anchor[],
  p: Palette,
  dragging: { id: string; userTime: number } | null,
): void {
  const { width, height } = size
  const { ref, confidence } = map.pairs()
  if (ref.length > 1) {
    ctx.beginPath()
    let started = false
    for (let i = 0; i < ref.length; i += 1) {
      const x = xOf(view, ref[i])
      if (x < -2 || x > width + 2) continue
      const yy = height - 2 - confidence[i] * (height * 0.45)
      if (!started) {
        ctx.moveTo(x, yy)
        started = true
      } else ctx.lineTo(x, yy)
    }
    ctx.strokeStyle = withAlpha(p.text2, 0.6)
    ctx.lineWidth = 1
    ctx.stroke()
  }
  const { major, minor } = ticks(view, 40)
  const lines = minor.length < 200 ? minor : major
  ctx.lineWidth = 1
  for (const t of lines) {
    const x0 = xOf(view, t)
    if (x0 < -50 || x0 > width + 50) continue
    const u = map.refToUser(t)
    const x1 = xOf(view, u)
    const drift = Math.abs(x1 - x0)
    ctx.strokeStyle = drift > 3 ? withAlpha(p.warn, 0.55) : withAlpha(p.text3, 0.35)
    ctx.beginPath()
    ctx.moveTo(x0, 0)
    ctx.lineTo(x1, height * 0.5)
    ctx.stroke()
  }
  for (const anchor of anchors) {
    const userTime = dragging?.id === anchor.id ? dragging.userTime : anchor.user_time_s
    const x0 = xOf(view, anchor.ref_time_s)
    const x1 = xOf(view, userTime)
    ctx.strokeStyle = p.accent
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(x0, 0)
    ctx.lineTo(x1, height * 0.5)
    ctx.stroke()
    ctx.fillStyle = anchor.locked ? p.accent : p.surface3
    ctx.strokeStyle = p.accent
    ctx.beginPath()
    ctx.arc(x1, height * 0.5, 5, 0, Math.PI * 2)
    ctx.fill()
    ctx.stroke()
  }
  ctx.font = `600 9px ${p.font}`
  ctx.fillStyle = p.text3
  ctx.textBaseline = 'top'
  ctx.fillText('REF TIME', 4, 2)
  ctx.textBaseline = 'bottom'
  ctx.fillText('TAKE TIME · CONFIDENCE', 4, height - 1)
}

export function hitAnchor(
  anchors: Anchor[],
  view: Viewport,
  x: number,
  y: number,
  height: number,
): Anchor | null {
  for (const anchor of anchors) {
    const ax = xOf(view, anchor.user_time_s)
    if (Math.abs(ax - x) <= 7 && Math.abs(y - height * 0.5) <= 9) return anchor
  }
  return null
}
