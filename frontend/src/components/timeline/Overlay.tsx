import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import { engine } from '../../audio/engine'
import { formatSeconds, formatTime } from '../../lib/format'
import { useWorkspace } from '../../state/workspace'
import type { TimelineModel } from './model'
import { setView, xOf, type Viewport } from './viewport'

function lowConfidenceBands(model: TimelineModel): { start: number; end: number }[] {
  if (model.map.identity) return []
  const { ref, confidence } = model.map.pairs()
  const bands: { start: number; end: number }[] = []
  let open: number | null = null
  for (let i = 0; i < ref.length; i += 1) {
    const low = confidence[i] < 0.35
    if (low && open === null) open = ref[i]
    if (!low && open !== null) {
      if (ref[i] - open > 0.12) bands.push({ start: open, end: ref[i] })
      open = null
    }
  }
  if (open !== null && ref.length) bands.push({ start: open, end: ref[ref.length - 1] })
  return bands
}

export function Overlay({
  view,
  model,
  showConfidence,
  follow,
}: {
  view: Viewport
  model: TimelineModel
  showConfidence: boolean
  follow: boolean
}) {
  const region = useWorkspace((s) => s.region)
  const loop = useWorkspace((s) => s.loop)
  const loopEnabled = useWorkspace((s) => s.loopEnabled)
  const hover = useWorkspace((s) => s.hover)
  const ruler = useWorkspace((s) => s.ruler)
  const pins = useWorkspace((s) => s.pins)
  const playhead = useRef<HTMLDivElement>(null)
  const viewRef = useRef(view)
  const followRef = useRef(follow)
  useLayoutEffect(() => {
    viewRef.current = view
    followRef.current = follow
  })
  const bands = useMemo(() => (showConfidence ? lowConfidenceBands(model) : []), [model, showConfidence])

  useEffect(() => {
    let frame = 0
    let lastX = NaN
    const tick = () => {
      const current = viewRef.current
      const t = engine.position()
      const x = xOf(current, t)
      if (playhead.current && Math.abs(x - lastX) > 0.1) {
        lastX = x
        playhead.current.style.transform = `translateX(${x}px)`
        playhead.current.style.opacity = x < -2 || x > current.width + 2 ? '0' : '1'
      }
      if (engine.state.playing && followRef.current && current.width > 0) {
        const span = current.end - current.start
        if (t > current.end - span * 0.04 || t < current.start)
          setView({ start: t - span * 0.06, end: t - span * 0.06 + span })
      }
      frame = window.requestAnimationFrame(tick)
    }
    frame = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(frame)
  }, [])

  const span = (start: number, end: number) => {
    const left = xOf(view, start)
    const right = xOf(view, end)
    return { left, width: Math.max(1, right - left) }
  }

  return (
    <div className="timeline-overlay" aria-hidden>
      {bands.map((band) => {
        const box = span(band.start, band.end)
        if (box.left > view.width || box.left + box.width < 0) return null
        return (
          <div
            key={`${band.start}`}
            className="overlay-lowconf"
            style={{ left: box.left, width: box.width }}
            title="Alignment is uncertain here"
          />
        )
      })}
      {loop ? (
        <div className={`overlay-loop${loopEnabled ? ' is-on' : ''}`} style={span(loop.start, loop.end)} />
      ) : null}
      {region ? (
        <div className="overlay-region" style={span(region.start, region.end)}>
          <span className="overlay-region-label">{formatSeconds(region.end - region.start)}</span>
        </div>
      ) : null}
      {ruler ? (
        <>
          <div className="overlay-ruler-mark" style={{ left: xOf(view, ruler.a) }} />
          {ruler.b !== null ? (
            <>
              <div className="overlay-ruler-mark" style={{ left: xOf(view, ruler.b) }} />
              <div
                className="overlay-ruler-span"
                style={span(Math.min(ruler.a, ruler.b), Math.max(ruler.a, ruler.b))}
              >
                <span>Δ {formatSeconds(Math.abs(ruler.b - ruler.a), 3)}</span>
              </div>
            </>
          ) : null}
        </>
      ) : null}
      {pins.map((pin) => (
        <div
          key={pin.id}
          className="overlay-pin"
          style={{ left: xOf(view, pin.time) }}
          title={`${pin.label} at ${formatTime(pin.time)}`}
        />
      ))}
      {hover !== null ? (
        <div className="overlay-hover" style={{ transform: `translateX(${xOf(view, hover)}px)` }} />
      ) : null}
      <div ref={playhead} className="overlay-playhead">
        <span className="overlay-playhead-head" />
      </div>
    </div>
  )
}
