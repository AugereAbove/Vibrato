import { useWorkspace, type Region } from '../../state/workspace'
import { reducedMotionNow } from '../../state/prefs'

export const MIN_SPAN_S = 0.08
export const LABEL_GUTTER = 0

export interface Viewport {
  start: number
  end: number
  width: number
}

export function xOf(view: Viewport, t: number): number {
  return ((t - view.start) / (view.end - view.start)) * view.width
}

export function tOf(view: Viewport, x: number): number {
  return view.start + (x / Math.max(1, view.width)) * (view.end - view.start)
}

export function pxPerSecond(view: Viewport): number {
  return view.width / Math.max(1e-6, view.end - view.start)
}

const STEPS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300]

export function tickStep(view: Viewport, minPx = 72): number {
  const pps = pxPerSecond(view)
  for (const step of STEPS) if (step * pps >= minPx) return step
  return STEPS[STEPS.length - 1]
}

export function ticks(view: Viewport, minPx = 72): { major: number[]; minor: number[]; step: number } {
  const step = tickStep(view, minPx)
  const minorStep = step / (step >= 1 && step % 5 === 0 ? 5 : step === 0.25 ? 5 : 4)
  const major: number[] = []
  const minor: number[] = []
  const first = Math.floor(view.start / step) * step
  for (let t = first; t <= view.end + step; t += step) major.push(Number(t.toFixed(4)))
  const firstMinor = Math.floor(view.start / minorStep) * minorStep
  for (let t = firstMinor; t <= view.end; t += minorStep) minor.push(Number(t.toFixed(5)))
  return { major, minor, step }
}

export function clampView(view: Region, duration: number): Region {
  const total = Math.max(duration, MIN_SPAN_S)
  let span = Math.max(MIN_SPAN_S, Math.min(view.end - view.start, total * 1.05))
  if (!Number.isFinite(span)) span = total
  let start = view.start
  const padding = span * 0.02
  start = Math.max(-padding, Math.min(start, total - span + padding))
  return { start, end: start + span }
}

let animation = 0

export function setView(view: Region, animate = false): void {
  const { duration, view: current } = useWorkspace.getState()
  const target = clampView(view, duration)
  window.cancelAnimationFrame(animation)
  if (!animate || reducedMotionNow()) {
    useWorkspace.setState({ view: target })
    return
  }
  const from = { ...current }
  const started = performance.now()
  const durationMs = 280
  const step = (now: number) => {
    const t = Math.min(1, (now - started) / durationMs)
    const eased = 1 - (1 - t) ** 3
    useWorkspace.setState({
      view: {
        start: from.start + (target.start - from.start) * eased,
        end: from.end + (target.end - from.end) * eased,
      },
    })
    if (t < 1) animation = window.requestAnimationFrame(step)
  }
  animation = window.requestAnimationFrame(step)
}

export function zoomAround(factor: number, center?: number, animate = false): void {
  const { view } = useWorkspace.getState()
  const anchor = center ?? (view.start + view.end) / 2
  const span = (view.end - view.start) * factor
  const ratio = (anchor - view.start) / Math.max(1e-6, view.end - view.start)
  setView({ start: anchor - ratio * span, end: anchor - ratio * span + span }, animate)
}

export function panBy(seconds: number): void {
  const { view } = useWorkspace.getState()
  setView({ start: view.start + seconds, end: view.end + seconds })
}

export function fitRange(start: number, end: number, padding = 0.08): void {
  const span = Math.max(MIN_SPAN_S, end - start)
  setView({ start: start - span * padding, end: end + span * padding }, true)
}

export function fitAll(): void {
  const { duration } = useWorkspace.getState()
  setView({ start: 0, end: duration }, true)
}

export function ensureVisible(t: number): void {
  const { view } = useWorkspace.getState()
  const span = view.end - view.start
  if (t < view.start || t > view.end) setView({ start: t - span * 0.1, end: t - span * 0.1 + span })
}
