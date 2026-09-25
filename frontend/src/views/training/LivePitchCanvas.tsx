import { useEffect, useRef } from 'react'
import type { FeatureBundle } from '../../api/binary'
import type { Segment } from '../../api/types'
import { engine } from '../../audio/engine'
import { PitchTracker } from '../../audio/pitch'
import type { Recorder } from '../../audio/recorder'
import { palette } from '../../components/timeline/lanes/palette'
import { withAlpha } from '../../components/timeline/useCanvas'
import { hzToMidi, noteName } from '../../lib/music'

export interface LiveReading {
  midi: number | null
  target: number | null
  cents: number | null
  level: number
}

export function LivePitchCanvas({
  features,
  notes,
  start,
  end,
  recorder,
  theme,
  onReading,
}: {
  features: FeatureBundle | null
  notes: { segment: Segment; center: number }[]
  start: number
  end: number
  recorder: Recorder | null
  theme: string
  onReading: (reading: LiveReading) => void
}) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const trail = useRef<{ t: number; midi: number }[]>([])
  const onReadingRef = useRef(onReading)
  useEffect(() => {
    onReadingRef.current = onReading
  })
  useEffect(() => {
    const element = canvas.current
    if (!element) return
    const tracker = recorder?.analyser ? new PitchTracker(recorder.analyser) : null
    const f0 = features?.tracks.f0_hz
    const hop = features?.hopS ?? 0.01
    const midis: number[] = []
    if (f0) {
      for (let i = Math.floor(start / hop); i < Math.min(f0.length, Math.ceil(end / hop)); i += 1) {
        if (f0[i] > 30) midis.push(hzToMidi(f0[i]))
      }
    }
    for (const note of notes) midis.push(note.center)
    const low = midis.length ? Math.floor(Math.min(...midis)) - 3 : 48
    const high = midis.length ? Math.ceil(Math.max(...midis)) + 3 : 72
    let frame = 0
    let lastLocal = performance.now()
    let localTime = start
    let lastReport = 0
    const draw = () => {
      const width = element.clientWidth
      const height = element.clientHeight
      const dpr = window.devicePixelRatio || 1
      if (element.width !== Math.round(width * dpr)) element.width = Math.round(width * dpr)
      if (element.height !== Math.round(height * dpr)) element.height = Math.round(height * dpr)
      const ctx = element.getContext('2d')
      if (!ctx) return
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)
      const p = palette(theme)
      const x = (t: number) => ((t - start) / Math.max(0.1, end - start)) * width
      const y = (m: number) => height - ((m - low) / Math.max(1, high - low)) * height
      for (let m = low; m <= high; m += 1) {
        const pc = ((m % 12) + 12) % 12
        if ([1, 3, 6, 8, 10].includes(pc)) {
          ctx.fillStyle = p.pianoBlack
          ctx.fillRect(0, y(m + 0.5), width, height / (high - low))
        }
        if (pc === 0) {
          ctx.fillStyle = p.text3
          ctx.font = `500 10px ${p.mono}`
          ctx.fillText(noteName(m), 4, y(m) + 3)
        }
      }
      for (const note of notes) {
        const x0 = x(note.segment.start_s)
        const x1 = x(note.segment.end_s)
        ctx.fillStyle = withAlpha(p.ref, 0.16)
        ctx.strokeStyle = withAlpha(p.ref, 0.5)
        ctx.fillRect(x0, y(note.center) - 5, x1 - x0, 10)
        ctx.strokeRect(x0, y(note.center) - 5, x1 - x0, 10)
        ctx.fillStyle = withAlpha(p.ref, 0.12)
        ctx.fillRect(x0, y(note.center + 0.25), x1 - x0, y(note.center - 0.25) - y(note.center + 0.25))
      }
      if (f0) {
        ctx.strokeStyle = p.ref
        ctx.lineWidth = 1.6
        ctx.beginPath()
        let open = false
        for (let i = Math.floor(start / hop); i < Math.min(f0.length, Math.ceil(end / hop)); i += 1) {
          if (!(f0[i] > 30)) {
            open = false
            continue
          }
          const px = x(i * hop)
          const py = y(hzToMidi(f0[i]))
          if (open) ctx.lineTo(px, py)
          else ctx.moveTo(px, py)
          open = true
        }
        ctx.stroke()
      }
      const now = performance.now()
      if (engine.state.playing) localTime = engine.position()
      else {
        localTime += (now - lastLocal) / 1000
        if (localTime > end) localTime = start
      }
      lastLocal = now
      let reading: LiveReading = { midi: null, target: null, cents: null, level: 0 }
      if (tracker) {
        const result = tracker.read()
        const target =
          notes.find((n) => localTime >= n.segment.start_s && localTime <= n.segment.end_s)?.center ?? null
        if (result.f0) {
          const midi = hzToMidi(result.f0)
          trail.current.push({ t: localTime, midi })
          reading = {
            midi,
            target,
            cents: target !== null ? (midi - target) * 100 : null,
            level: result.level,
          }
        } else {
          reading = { midi: null, target, cents: null, level: result.level }
        }
      }
      trail.current = trail.current.filter(
        (point) =>
          point.t <= localTime + 0.05 && point.t >= localTime - (end - start) * 0.98 && point.t >= start,
      )
      ctx.strokeStyle = p.take
      ctx.lineWidth = 2.4
      ctx.beginPath()
      let previous: { t: number; midi: number } | null = null
      for (const point of trail.current) {
        if (previous && point.t - previous.t < 0.12 && point.t >= previous.t)
          ctx.lineTo(x(point.t), y(point.midi))
        else ctx.moveTo(x(point.t), y(point.midi))
        previous = point
      }
      ctx.stroke()
      if (reading.midi !== null) {
        ctx.fillStyle = p.take
        ctx.beginPath()
        ctx.arc(x(localTime), y(reading.midi), 5, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.fillStyle = withAlpha(p.accent, 0.8)
      ctx.fillRect(x(localTime), 0, 1.5, height)
      if (now - lastReport > 90) {
        lastReport = now
        onReadingRef.current(reading)
      }
      frame = window.requestAnimationFrame(draw)
    }
    frame = window.requestAnimationFrame(draw)
    return () => window.cancelAnimationFrame(frame)
  }, [features, notes, start, end, recorder, theme])
  return (
    <canvas
      ref={canvas}
      className="live-canvas"
      role="img"
      aria-label="Your live pitch drawn over the reference pitch for this phrase"
    />
  )
}
