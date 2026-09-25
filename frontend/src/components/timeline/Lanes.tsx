import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Anchor, Bookmark, HeatmapView, Segment, SongSection } from '../../api/types'
import { engine } from '../../audio/engine'
import { reducedMotionNow } from '../../state/prefs'
import { select, type Selection } from '../../state/workspace'
import { takeToTimeline, type TimelineModel } from './model'
import { drawAlignment } from './lanes/alignment'
import { drawCurves, LOUDNESS_SPEC, VOICE_SPEC } from './lanes/curves'
import { drawEvents, drawPhonemes } from './lanes/events'
import { drawHeatmapLane } from './lanes/heatmap'
import { palette } from './lanes/palette'
import { drawPitch, type PitchOptions, type PitchRange } from './lanes/pitch'
import { drawRuler } from './lanes/ruler'
import { drawSpectrogram } from './lanes/spectrogram'
import { drawWaveform } from './lanes/waveform'
import { useCanvasDraw, type CanvasSize } from './useCanvas'
import { xOf, type Viewport } from './viewport'
import type { Region } from '../../state/workspace'

interface BaseLaneProps {
  view: Viewport
  height: number
  theme: string
}

function Canvas({
  width,
  height,
  draw,
  label,
}: {
  width: number
  height: number
  draw: (ctx: CanvasRenderingContext2D, size: CanvasSize) => void
  label: string
}) {
  const canvas = useCanvasDraw(width, height, draw)
  return (
    <canvas ref={canvas} className="lane-canvas" style={{ width, height }} role="img" aria-label={label} />
  )
}

export function RulerLane({
  view,
  height,
  theme,
  sections,
  bookmarks,
  loop,
  loopEnabled,
  region,
}: BaseLaneProps & {
  sections: (SongSection | Segment)[]
  bookmarks: Bookmark[]
  loop: Region | null
  loopEnabled: boolean
  region: Region | null
}) {
  const draw = useCallback(
    (ctx: CanvasRenderingContext2D, size: CanvasSize) =>
      drawRuler(ctx, size, view, palette(theme), { sections, bookmarks, loop, loopEnabled, region }),
    [view, theme, sections, bookmarks, loop, loopEnabled, region],
  )
  return (
    <Canvas
      width={view.width}
      height={height}
      draw={draw}
      label="Time ruler with sections, bookmarks and loop region"
    />
  )
}

export function WaveformLane({
  view,
  height,
  theme,
  model,
  mode,
}: BaseLaneProps & { model: TimelineModel; mode: 'stacked' | 'overlay' }) {
  const draw = useCallback(
    (ctx: CanvasRenderingContext2D, size: CanvasSize) =>
      drawWaveform(ctx, size, view, model, palette(theme), mode),
    [view, theme, model, mode],
  )
  return <Canvas width={view.width} height={height} draw={draw} label="Reference and take waveforms" />
}

export function PitchLane({
  view,
  height,
  theme,
  model,
  range,
  options,
}: BaseLaneProps & { model: TimelineModel; range: PitchRange; options: Omit<PitchOptions, 'reveal'> }) {
  const [reveal, setReveal] = useState(() => (reducedMotionNow() ? 1 : 0))
  const started = useRef(false)
  useEffect(() => {
    if (started.current || !model.take?.features) return
    started.current = true
    if (reducedMotionNow()) return
    const begin = performance.now()
    let frame = 0
    const step = (now: number) => {
      const t = Math.min(1, (now - begin) / 900)
      setReveal(1 - (1 - t) ** 2)
      if (t < 1) frame = window.requestAnimationFrame(step)
    }
    frame = window.requestAnimationFrame(step)
    return () => window.cancelAnimationFrame(frame)
  }, [model.take?.features])
  const effectiveReveal = model.take?.features ? reveal : 1
  const draw = useCallback(
    (ctx: CanvasRenderingContext2D, size: CanvasSize) =>
      drawPitch(ctx, size, view, model, palette(theme), range, { ...options, reveal: effectiveReveal }),
    [view, theme, model, range, options, effectiveReveal],
  )
  return <Canvas width={view.width} height={height} draw={draw} label="Pitch contours on a piano roll" />
}

export function SpectrogramLane({
  view,
  height,
  theme,
  model,
  showFormants,
  showImage,
}: BaseLaneProps & { model: TimelineModel; showFormants: boolean; showImage: boolean }) {
  const draw = useCallback(
    (ctx: CanvasRenderingContext2D, size: CanvasSize) =>
      drawSpectrogram(ctx, size, view, model, palette(theme), showFormants, showImage),
    [view, theme, model, showFormants, showImage],
  )
  return <Canvas width={view.width} height={height} draw={draw} label="Spectrogram with formant tracks" />
}

export function CurveLane({
  view,
  height,
  theme,
  model,
  kind,
}: BaseLaneProps & { model: TimelineModel; kind: 'loudness' | 'voice' }) {
  const draw = useCallback(
    (ctx: CanvasRenderingContext2D, size: CanvasSize) =>
      drawCurves(
        ctx,
        size,
        view,
        model,
        palette(theme),
        kind === 'loudness' ? LOUDNESS_SPEC : VOICE_SPEC,
        kind === 'voice',
      ),
    [view, theme, model, kind],
  )
  return (
    <Canvas
      width={view.width}
      height={height}
      draw={draw}
      label={kind === 'loudness' ? 'Loudness envelopes' : 'Voice quality tracks'}
    />
  )
}

export function EventsLane({
  view,
  height,
  theme,
  model,
  selected,
}: BaseLaneProps & { model: TimelineModel; selected: { side: 'ref' | 'take'; id: string } | null }) {
  const draw = useCallback(
    (ctx: CanvasRenderingContext2D, size: CanvasSize) =>
      drawEvents(ctx, size, view, model, palette(theme), selected),
    [view, theme, model, selected],
  )
  return (
    <Canvas width={view.width} height={height} draw={draw} label="Breath, vibrato, scoop and onset events" />
  )
}

export function PhonemeLane({
  view,
  height,
  theme,
  model,
  selected,
}: BaseLaneProps & { model: TimelineModel; selected: { ref: string | null; take: string | null } }) {
  const draw = useCallback(
    (ctx: CanvasRenderingContext2D, size: CanvasSize) =>
      drawPhonemes(ctx, size, view, model, palette(theme), selected),
    [view, theme, model, selected],
  )
  return <Canvas width={view.width} height={height} draw={draw} label="Phoneme lane" />
}

export function HeatmapLane({
  view,
  height,
  theme,
  heatmap,
  rows,
  mask,
  selected,
}: BaseLaneProps & {
  heatmap: HeatmapView | null
  rows: string[]
  mask: boolean
  selected: { row: string; column: number } | null
}) {
  const draw = useCallback(
    (ctx: CanvasRenderingContext2D, size: CanvasSize) =>
      drawHeatmapLane(ctx, size, view, heatmap, rows, palette(theme), mask, selected),
    [view, theme, heatmap, rows, mask, selected],
  )
  return <Canvas width={view.width} height={height} draw={draw} label="Difference heatmap by category" />
}

export function AlignmentLane({
  view,
  height,
  theme,
  model,
  anchors,
  dragging,
}: BaseLaneProps & {
  model: TimelineModel
  anchors: Anchor[]
  dragging: { id: string; userTime: number } | null
}) {
  const draw = useCallback(
    (ctx: CanvasRenderingContext2D, size: CanvasSize) =>
      drawAlignment(ctx, size, view, model.map, anchors, palette(theme), dragging),
    [view, theme, model, anchors, dragging],
  )
  return (
    <Canvas width={view.width} height={height} draw={draw} label="Alignment warp, confidence and anchors" />
  )
}

interface WordBox {
  segment: Segment
  side: 'ref' | 'take'
  start: number
  end: number
}

export function LyricsLane({
  view,
  height,
  model,
  selection,
}: {
  view: Viewport
  height: number
  model: TimelineModel
  selection: Selection | null
}) {
  const container = useRef<HTMLDivElement>(null)
  const words = useMemo(() => {
    const out: WordBox[] = []
    for (const segment of model.ref?.analysis?.byLevel.word ?? []) {
      out.push({ segment, side: 'ref', start: segment.start_s, end: segment.end_s })
    }
    for (const segment of model.take?.analysis?.byLevel.word ?? []) {
      out.push({
        segment,
        side: 'take',
        start: takeToTimeline(model, segment.start_s),
        end: takeToTimeline(model, segment.end_s),
      })
    }
    return out
  }, [model])
  const phrases = model.ref?.analysis?.byLevel.phrase ?? []

  useEffect(() => {
    let frame = 0
    let last = -1
    const tick = () => {
      const t = engine.position()
      if (Math.abs(t - last) > 0.005 && container.current) {
        last = t
        const nodes = container.current.querySelectorAll<HTMLElement>('[data-start]')
        nodes.forEach((node) => {
          const start = Number(node.dataset.start)
          const end = Number(node.dataset.end)
          node.classList.toggle('is-current', t >= start && t < end)
        })
      }
      frame = window.requestAnimationFrame(tick)
    }
    frame = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(frame)
  }, [words])

  const rows = model.take ? 2 : 1
  const rowHeight = height / rows
  const selectedIds = new Set<string>()
  if (selection?.kind === 'segment') {
    if (selection.refId) selectedIds.add(selection.refId)
    if (selection.takeId) selectedIds.add(selection.takeId)
  }

  const choose = (box: WordBox) => {
    const cindex = model.cindex
    const counterpart =
      box.side === 'ref'
        ? (cindex?.refToUser.get(box.segment.id) ?? null)
        : (cindex?.userToRef.get(box.segment.id) ?? null)
    const refId = box.side === 'ref' ? box.segment.id : counterpart
    const refSegment = refId ? model.ref?.analysis?.segments.get(refId) : null
    select({
      kind: 'segment',
      level: 'word',
      refId,
      takeId: box.side === 'take' ? box.segment.id : counterpart,
      start: refSegment ? refSegment.start_s : box.start,
      end: refSegment ? refSegment.end_s : box.end,
      label: box.segment.label,
    })
    engine.seek(refSegment ? refSegment.start_s : box.start)
  }

  return (
    <div ref={container} className="lyrics-lane" style={{ width: view.width, height }}>
      {phrases.map((phrase) => {
        const x = xOf(view, phrase.start_s)
        if (x < -2 || x > view.width + 2) return null
        return (
          <span key={phrase.id} className="lyrics-phrase-mark" style={{ transform: `translateX(${x}px)` }} />
        )
      })}
      {words.map((box) => {
        const x0 = xOf(view, box.start)
        const x1 = xOf(view, box.end)
        if (x1 < 0 || x0 > view.width) return null
        const widthPx = Math.max(6, x1 - x0 - 2)
        const top = box.side === 'ref' || rows === 1 ? 0 : rowHeight
        return (
          <button
            key={`${box.side}:${box.segment.id}`}
            type="button"
            className={`lyric-word lyric-${box.side}${selectedIds.has(box.segment.id) ? ' is-selected' : ''}`}
            data-start={box.start}
            data-end={box.end}
            style={{ left: x0 + 1, top: top + 3, width: widthPx, height: rowHeight - 6 }}
            title={`${box.segment.label} · ${box.side === 'ref' ? 'reference' : 'take'}`}
            onPointerDown={(event) => event.stopPropagation()}
            onClick={() => choose(box)}
          >
            {widthPx > 18 ? box.segment.label : ''}
          </button>
        )
      })}
    </div>
  )
}
