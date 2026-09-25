import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { Anchor, Bookmark, Finding, Segment, SongSection } from '../../api/types'
import { engine } from '../../audio/engine'
import { segmentAt } from '../../lib/analysis'
import type { LayerId } from '../../lib/categories'
import { categoryLabel } from '../../lib/categories'
import type { ViewMode } from '../../state/prefs'
import { setLaneHeight, setUi, toggleLayer, useUi, type LaneId } from '../../state/ui'
import { nextPinId, select, useWorkspace, type Selection } from '../../state/workspace'
import { Button, IconButton } from '../ui/Button'
import { Segmented } from '../ui/Controls'
import { Icon } from '../ui/Icon'
import { Tooltip } from '../ui/Tooltip'
import {
  AlignmentLane,
  CurveLane,
  EventsLane,
  HeatmapLane,
  LyricsLane,
  PhonemeLane,
  PitchLane,
  RulerLane,
  SpectrogramLane,
  WaveformLane,
} from './Lanes'
import { hitAnchor } from './lanes/alignment'
import { sampleTrack } from './lanes/curves'
import { hitEvent, hitPhoneme } from './lanes/events'
import { hitHeatmap } from './lanes/heatmap'
import { autoPitchRange, hitPitch, type PitchRange } from './lanes/pitch'
import { hitBookmark } from './lanes/ruler'
import { Minimap } from './Minimap'
import { takeTime, type TimelineModel } from './model'
import { Overlay } from './Overlay'
import { HoverReadout } from './Readout'
import { useElementSize } from './useCanvas'
import { fitAll, fitRange, panBy, tOf, zoomAround, type Viewport } from './viewport'
import { describeHz } from '../../lib/music'
import { formatDb } from '../../lib/format'

const HEADER_WIDTH = 132
const RULER_HEIGHT = 34
const DRAG_THRESHOLD = 4

export interface TimelineProps {
  model: TimelineModel
  mode: ViewMode
  theme: 'dark' | 'light'
  layers: Record<LayerId, boolean>
  bookmarks: Bookmark[]
  sections: (SongSection | Segment)[]
  anchors: Anchor[]
  focus: Finding | null
  onContextMenu: (event: React.MouseEvent, time: number) => void
  onAnchorMove?: (anchor: Anchor, userTime: number) => void
  onBookmarkClick?: (bookmark: Bookmark) => void
  toolbarExtra?: ReactNode
}

interface LaneDef {
  id: LaneId | 'ruler'
  title: string
  help: string
  height: number
  legend?: boolean
  header?: ReactNode
  body: ReactNode
  hit?: (x: number, y: number, height: number) => Selection | null
}

interface DragState {
  laneId: string
  pointerId: number
  startX: number
  startT: number
  moved: boolean
  kind: 'select' | 'scrub' | 'anchor' | 'ruler'
  anchor?: Anchor
  lastSeek: number
}

function snapRegion(model: TimelineModel, start: number, end: number): { start: number; end: number } {
  const syllables = model.ref?.analysis?.byLevel.syllable ?? []
  if (!syllables.length) return { start, end }
  const near = (t: number, edge: 'start_s' | 'end_s') => {
    let best = t
    let distance = 0.12
    for (const s of syllables) {
      const d = Math.abs(s[edge] - t)
      if (d < distance) {
        distance = d
        best = s[edge]
      }
    }
    return best
  }
  return { start: near(start, 'start_s'), end: near(end, 'end_s') }
}

export function Timeline({
  model,
  mode,
  theme,
  layers,
  bookmarks,
  sections,
  anchors,
  focus,
  onContextMenu,
  onAnchorMove,
  onBookmarkClick,
  toolbarExtra,
}: TimelineProps) {
  const viewRange = useWorkspace((s) => s.view)
  const selection = useWorkspace((s) => s.selection)
  const region = useWorkspace((s) => s.region)
  const loop = useWorkspace((s) => s.loop)
  const loopEnabled = useWorkspace((s) => s.loopEnabled)
  const rulerActive = useWorkspace((s) => s.rulerActive)
  const laneHeights = useUi((s) => s.laneHeights)
  const waveformMode = useUi((s) => s.waveformMode)
  const heatmapView = useUi((s) => s.heatmapView)
  const heatmapMask = useUi((s) => s.heatmapMask)
  const timeMode = useUi((s) => s.timeMode)
  const spectrogramSource = useUi((s) => s.spectrogramSource)
  const [bodies, bodySize] = useElementSize<HTMLDivElement>()
  const scroller = useRef<HTMLDivElement>(null)
  const [manualRange, setManualRange] = useState<PitchRange | null>(null)
  const [anchorDrag, setAnchorDrag] = useState<{ id: string; userTime: number } | null>(null)
  const [heatSelection, setHeatSelection] = useState<{ row: string; column: number } | null>(null)
  const [follow, setFollow] = useState(true)
  const drag = useRef<DragState | null>(null)
  const hoverFrame = useRef(0)
  const width = Math.max(0, Math.floor(bodySize.width))
  const view: Viewport = useMemo(() => ({ ...viewRange, width }), [viewRange, width])
  const autoRange = useMemo(() => autoPitchRange(model), [model])
  const pitchRange = manualRange ?? autoRange
  const hasComparison = Boolean(model.comparison)
  const heat = model.comparison?.heatmap.views[heatmapView] ?? null
  const heatRows = model.comparison?.heatmap.rows ?? []

  const selectedRef = selection?.kind === 'segment' ? selection.refId : null
  const selectedTake = selection?.kind === 'segment' ? selection.takeId : null
  const pitchOptions = useMemo(
    () => ({
      selectedRef,
      selectedTake,
      showNoteNames: true,
      focus,
      showArrows: hasComparison,
      showVibrato: true,
    }),
    [selectedRef, selectedTake, focus, hasComparison],
  )
  const eventSelection = useMemo(
    () =>
      selection?.kind === 'event'
        ? { side: selection.side === 'take' ? ('take' as const) : ('ref' as const), id: selection.eventId }
        : null,
    [selection],
  )
  const phonemeSelection = useMemo(
    () => ({ ref: selectedRef, take: selectedTake }),
    [selectedRef, selectedTake],
  )

  const lanes: LaneDef[] = []
  lanes.push({
    id: 'ruler',
    title: 'Time',
    help: 'Click or drag to move the playhead. Sections, bookmarks and the loop region are shown here.',
    height: RULER_HEIGHT,
    body: (
      <RulerLane
        view={view}
        height={RULER_HEIGHT}
        theme={theme}
        sections={sections}
        bookmarks={bookmarks}
        loop={loop}
        loopEnabled={loopEnabled}
        region={region}
      />
    ),
  })
  const hasWords = Boolean(
    model.ref?.analysis?.byLevel.word.length || model.take?.analysis?.byLevel.word.length,
  )
  if (layers.lyrics && hasWords) {
    const height = laneHeights.lyrics
    lanes.push({
      id: 'lyrics',
      title: 'Lyrics',
      help: 'Words of the reference (top) and your take (bottom). Click a word to select and play from it.',
      height,
      legend: Boolean(model.take),
      body: <LyricsLane view={view} height={height} model={model} selection={selection} />,
    })
  }
  const hasPhonemes = Boolean(model.ref?.analysis?.byLevel.phoneme.length)
  if (layers.phonemes && hasPhonemes) {
    const height = laneHeights.phonemes * (model.take ? 1.4 : 1)
    lanes.push({
      id: 'phonemes',
      title: 'Phonemes',
      help: 'Phonemes aligned to the lyrics, coloured by sound class. Lyric-assisted alignment is approximate.',
      height,
      legend: Boolean(model.take),
      body: (
        <PhonemeLane view={view} height={height} theme={theme} model={model} selected={phonemeSelection} />
      ),
      hit: (x, y, h) => hitPhoneme(model, view, x, y, h),
    })
  }
  if (layers.waveform) {
    const height = laneHeights.waveform
    lanes.push({
      id: 'waveform',
      title: 'Waveform',
      help: 'Amplitude of both recordings. Stacked shows them separately; overlay draws them on top of each other.',
      height,
      legend: Boolean(model.take),
      header: model.take ? (
        <Segmented
          size="sm"
          ariaLabel="Waveform layout"
          value={waveformMode}
          onChange={(value) => setUi({ waveformMode: value })}
          options={[
            { value: 'stacked', label: 'Stack' },
            { value: 'overlay', label: 'Overlay' },
          ]}
        />
      ) : null,
      body: <WaveformLane view={view} height={height} theme={theme} model={model} mode={waveformMode} />,
    })
  }
  if (layers.pitch) {
    const height = laneHeights.pitch
    lanes.push({
      id: 'pitch',
      title: 'Pitch',
      help: 'Pitch contours on a piano roll. Filled boxes are reference notes, dashed boxes are your notes. Arrows show notes that land off-centre. Alt+scroll zooms vertically.',
      height,
      legend: Boolean(model.take),
      header: manualRange ? (
        <Button size="xs" variant="ghost" icon="refresh" onClick={() => setManualRange(null)}>
          Auto range
        </Button>
      ) : null,
      body: (
        <PitchLane
          view={view}
          height={height}
          theme={theme}
          model={model}
          range={pitchRange}
          options={pitchOptions}
        />
      ),
      hit: (x, y, h) => hitPitch(model, view, pitchRange, x, y, h),
    })
  }
  if (layers.spectrogram || layers.formants) {
    const height = laneHeights.spectrogram
    lanes.push({
      id: 'spectrogram',
      title: layers.spectrogram ? 'Spectrogram' : 'Formants',
      help: 'Energy over time and frequency (log scale). Coloured dots are formant tracks: F1 red, F2 yellow, F3 cyan.',
      height,
      header: (
        <div className="stack" style={{ gap: 4 }}>
          {model.take ? (
            <Segmented
              size="sm"
              ariaLabel="Spectrogram source"
              value={spectrogramSource}
              onChange={(value) => setUi({ spectrogramSource: value })}
              options={[
                { value: 'reference', label: 'Ref' },
                { value: 'take', label: 'Take' },
              ]}
            />
          ) : null}
          <button
            type="button"
            className={`lane-toggle${layers.formants ? ' is-on' : ''}`}
            onClick={() => toggleLayer(mode, 'formants')}
          >
            Formants
          </button>
        </div>
      ),
      body: (
        <SpectrogramLane
          view={view}
          height={height}
          theme={theme}
          model={model}
          showFormants={layers.formants}
          showImage={layers.spectrogram}
        />
      ),
    })
  }
  if (layers.loudness) {
    const height = laneHeights.loudness
    lanes.push({
      id: 'loudness',
      title: 'Loudness',
      help: 'Level relative to each recording’s own singing level, so microphone gain does not matter.',
      height,
      legend: Boolean(model.take),
      body: <CurveLane view={view} height={height} theme={theme} model={model} kind="loudness" />,
    })
  }
  if (layers.voice) {
    const height = laneHeights.voice
    lanes.push({
      id: 'voice',
      title: 'Voice quality',
      help: 'Cepstral peak prominence (CPPS): higher is clearer and more periodic, lower is breathier or rougher.',
      height,
      legend: Boolean(model.take),
      body: <CurveLane view={view} height={height} theme={theme} model={model} kind="voice" />,
    })
  }
  if (layers.events) {
    const height = laneHeights.events * (model.take ? 1.3 : 1)
    lanes.push({
      id: 'events',
      title: 'Events',
      help: 'Breaths, vibrato, scoops, glides, onsets and irregular voicing. Consonants appear when zoomed in.',
      height,
      legend: Boolean(model.take),
      body: <EventsLane view={view} height={height} theme={theme} model={model} selected={eventSelection} />,
      hit: (x, y, h) => hitEvent(model, view, x, y, h),
    })
  }
  if (layers.heatmap && hasComparison && heat) {
    const height = laneHeights.heatmap
    lanes.push({
      id: 'heatmap',
      title: 'Differences',
      help: 'Where each category differs most from the reference. Hatched cells are low confidence. Click a cell to select that place.',
      height,
      header: (
        <div className="heat-row-labels" style={{ height: height - 4 }}>
          {heatRows.map((row) => (
            <span key={row} className="heat-row-label">
              <span className="cat-dot" style={{ background: `var(--cat-${row})` }} />
              {row === 'confidence' ? 'Confidence' : categoryLabel(row)}
            </span>
          ))}
        </div>
      ),
      body: (
        <HeatmapLane
          view={view}
          height={height}
          theme={theme}
          heatmap={heat}
          rows={heatRows}
          mask={heatmapMask}
          selected={heatSelection}
        />
      ),
    })
  }
  if (layers.alignment && hasComparison && timeMode === 'aligned') {
    const height = laneHeights.alignment
    lanes.push({
      id: 'alignment',
      title: 'Alignment',
      help: 'Lines join each reference moment (top) to the matching moment in your take (middle); slanted lines mean different timing. Drag an anchor dot to correct the alignment.',
      height,
      body: (
        <AlignmentLane
          view={view}
          height={height}
          theme={theme}
          model={model}
          anchors={anchors}
          dragging={anchorDrag}
        />
      ),
    })
  }

  const layoutRef = useRef({ lanes, model, view })
  useLayoutEffect(() => {
    layoutRef.current = { lanes, model, view }
  })

  useEffect(() => {
    const element = scroller.current
    if (!element) return
    const onWheel = (event: WheelEvent) => {
      const { view: current, lanes: currentLanes } = layoutRef.current
      if (current.width <= 0) return
      const rect = bodies.current?.getBoundingClientRect()
      const x = rect ? event.clientX - rect.left : current.width / 2
      if (event.ctrlKey || event.metaKey) {
        event.preventDefault()
        zoomAround(Math.exp(event.deltaY * 0.0022), tOf(current, x))
        return
      }
      if (event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) {
        event.preventDefault()
        const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY
        panBy((delta / current.width) * (current.end - current.start))
        return
      }
      if (event.altKey) {
        const target = (event.target as HTMLElement).closest<HTMLElement>('[data-lane="pitch"]')
        if (!target) return
        event.preventDefault()
        const laneRect = target.getBoundingClientRect()
        const lane = currentLanes.find((l) => l.id === 'pitch')
        if (!lane) return
        setManualRange((previous) => {
          const range = previous ?? autoPitchRange(layoutRef.current.model)
          const ratio = 1 - (event.clientY - laneRect.top) / laneRect.height
          const anchor = range.low + ratio * (range.high - range.low)
          const factor = Math.exp(event.deltaY * 0.002)
          const span = Math.max(4, Math.min(60, (range.high - range.low) * factor))
          return { low: anchor - ratio * span, high: anchor - ratio * span + span }
        })
      }
    }
    element.addEventListener('wheel', onWheel, { passive: false })
    return () => element.removeEventListener('wheel', onWheel)
  }, [bodies])

  const locate = (event: React.PointerEvent | React.MouseEvent) => {
    const rect = bodies.current?.getBoundingClientRect()
    const laneElement = (event.target as HTMLElement).closest<HTMLElement>('[data-lane]')
    const laneRect = laneElement?.getBoundingClientRect()
    const x = rect ? event.clientX - rect.left : 0
    return {
      x,
      t: tOf(view, x),
      laneId: laneElement?.dataset.lane ?? '',
      y: laneRect ? event.clientY - laneRect.top : 0,
      laneHeight: laneRect?.height ?? 0,
    }
  }

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return
    const { x, t, laneId, y, laneHeight } = locate(event)
    if (!laneId) return
    let kind: DragState['kind'] = 'select'
    let anchor: Anchor | undefined
    if (rulerActive) kind = 'ruler'
    else if (laneId === 'ruler') kind = 'scrub'
    else if (laneId === 'alignment') {
      const hit = hitAnchor(anchors, view, x, y, laneHeight)
      if (hit) {
        kind = 'anchor'
        anchor = hit
      }
    }
    event.currentTarget.setPointerCapture(event.pointerId)
    drag.current = {
      laneId,
      pointerId: event.pointerId,
      startX: x,
      startT: t,
      moved: false,
      kind,
      anchor,
      lastSeek: 0,
    }
    if (kind === 'scrub') engine.seek(Math.max(0, t))
    if (kind === 'ruler') {
      const current = useWorkspace.getState().ruler
      if (!current || current.b !== null) useWorkspace.setState({ ruler: { a: t, b: null } })
      else useWorkspace.setState({ ruler: { a: current.a, b: t } })
    }
  }

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const { x, t } = locate(event)
    const state = drag.current
    if (!state) {
      window.cancelAnimationFrame(hoverFrame.current)
      hoverFrame.current = window.requestAnimationFrame(() => useWorkspace.setState({ hover: t }))
      return
    }
    if (!state.moved && Math.abs(x - state.startX) > DRAG_THRESHOLD) state.moved = true
    if (!state.moved) return
    if (state.kind === 'scrub') {
      const now = performance.now()
      const fine = event.shiftKey || event.altKey
      const target = fine ? state.startT + (t - state.startT) * 0.1 : t
      useWorkspace.setState({ hover: target })
      if (now - state.lastSeek > 40) {
        state.lastSeek = now
        engine.seek(Math.max(0, target))
      }
    } else if (state.kind === 'anchor' && state.anchor) {
      setAnchorDrag({ id: state.anchor.id, userTime: Math.max(0, t) })
    } else if (state.kind === 'select') {
      const start = Math.max(0, Math.min(state.startT, t))
      const end = Math.max(state.startT, t)
      useWorkspace.setState({ region: { start, end }, hover: t })
    }
  }

  const onPointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    const state = drag.current
    drag.current = null
    if (!state) return
    try {
      event.currentTarget.releasePointerCapture(state.pointerId)
    } catch {
      return
    }
    const { x, t, laneId, y, laneHeight } = locate(event)
    if (state.kind === 'anchor' && state.anchor) {
      if (state.moved && onAnchorMove) onAnchorMove(state.anchor, Math.max(0, t))
      setAnchorDrag(null)
      return
    }
    if (state.kind === 'scrub') {
      if (!state.moved) {
        const bookmark = hitBookmark(bookmarks, view, x)
        if (bookmark) onBookmarkClick?.(bookmark)
      }
      return
    }
    if (state.kind === 'ruler') return
    if (state.moved) {
      const current = useWorkspace.getState().region
      if (current && event.altKey)
        useWorkspace.setState({ region: snapRegion(model, current.start, current.end) })
      return
    }
    const lane = lanes.find((l) => l.id === (laneId || state.laneId))
    if (lane?.id === 'heatmap') {
      const hit = hitHeatmap(view, heat, heatRows, x, y, laneHeight)
      if (hit) {
        setHeatSelection({ row: hit.row, column: hit.column })
        const segmentId = hit.cell?.segment_id
        const refSegment = segmentId ? model.ref?.analysis?.segments.get(segmentId) : null
        if (refSegment) {
          select({
            kind: 'segment',
            level: refSegment.level,
            refId: refSegment.id,
            takeId: model.cindex?.refToUser.get(refSegment.id) ?? null,
            start: refSegment.start_s,
            end: refSegment.end_s,
            label: refSegment.label,
          })
          useWorkspace.setState({
            region: { start: hit.cell?.ref_start ?? hit.start, end: hit.cell?.ref_end ?? hit.end },
          })
        } else {
          useWorkspace.setState({ region: { start: hit.start, end: hit.end } })
        }
        return
      }
    }
    const selectionHit = lane?.hit?.(x, y, laneHeight) ?? null
    if (selectionHit) {
      select(selectionHit)
      if (event.altKey) {
        const pinTime = t
        useWorkspace.setState((s) => ({ pins: [...s.pins, pinAt(model, pinTime)] }))
      }
      return
    }
    if (event.altKey) {
      useWorkspace.setState((s) => ({ pins: [...s.pins, pinAt(model, t)] }))
      return
    }
    useWorkspace.setState({ region: null })
    engine.seek(Math.max(0, t))
  }

  const onDoubleClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const { t } = locate(event)
    const phrase = model.ref?.analysis ? segmentAt(model.ref.analysis.byLevel.phrase, t) : null
    if (!phrase) return
    select({
      kind: 'segment',
      level: 'phrase',
      refId: phrase.id,
      takeId: model.cindex?.refToUser.get(phrase.id) ?? null,
      start: phrase.start_s,
      end: phrase.end_s,
      label: phrase.label,
    })
    useWorkspace.setState({ region: { start: phrase.start_s, end: phrase.end_s } })
  }

  const startResize = (lane: LaneDef) => (event: React.PointerEvent<HTMLDivElement>) => {
    if (lane.id === 'ruler') return
    event.preventDefault()
    const startY = event.clientY
    const startHeight = laneHeights[lane.id as LaneId]
    const target = event.currentTarget
    target.setPointerCapture(event.pointerId)
    const move = (e: PointerEvent) => setLaneHeight(lane.id as LaneId, startHeight + (e.clientY - startY))
    const up = () => {
      target.removeEventListener('pointermove', move)
      target.removeEventListener('pointerup', up)
    }
    target.addEventListener('pointermove', move)
    target.addEventListener('pointerup', up)
  }

  const zoomLabel = `${(viewRange.end - viewRange.start).toFixed(viewRange.end - viewRange.start < 10 ? 2 : 1)} s visible`

  return (
    <section className="timeline" aria-label="Timeline">
      <div className="timeline-toolbar">
        <div className="row" style={{ gap: 2 }}>
          <IconButton
            icon="zoom-out"
            label="Zoom out"
            shortcut="−"
            onClick={() => zoomAround(1.6, engine.position(), true)}
          />
          <IconButton
            icon="zoom-in"
            label="Zoom in"
            shortcut="+"
            onClick={() => zoomAround(1 / 1.6, engine.position(), true)}
          />
          <IconButton
            icon="fit"
            label="Fit selection"
            shortcut="F"
            onClick={() => {
              const target = region ?? selection
              if (target) fitRange(target.start, target.end)
              else fitAll()
            }}
          />
          <Button size="xs" variant="ghost" onClick={() => fitAll()}>
            All
          </Button>
          <span className="faint tiny num" style={{ marginLeft: 6 }}>
            {zoomLabel}
          </span>
        </div>
        <div className="timeline-readout">
          <HoverReadout model={model} />
        </div>
        <div className="row" style={{ gap: 6 }}>
          {model.take ? (
            <Tooltip content="Aligned: your take is warped onto the reference timeline so the same words line up. Raw: both recordings on their own clocks.">
              <Segmented
                size="sm"
                ariaLabel="Time mode"
                value={timeMode}
                onChange={(value) => setUi({ timeMode: value })}
                options={[
                  { value: 'aligned', label: 'Aligned' },
                  { value: 'raw', label: 'Raw time' },
                ]}
              />
            </Tooltip>
          ) : null}
          <IconButton
            icon="ruler"
            label={rulerActive ? 'Stop measuring' : 'Measure time between two points'}
            active={rulerActive}
            onClick={() => useWorkspace.setState({ rulerActive: !rulerActive, ruler: null })}
          />
          <IconButton
            icon="target"
            label={follow ? 'Stop following the playhead' : 'Follow the playhead'}
            active={follow}
            onClick={() => setFollow((v) => !v)}
          />
          {toolbarExtra}
        </div>
      </div>
      <div className="timeline-minimap-row">
        <div className="timeline-legend" style={{ width: HEADER_WIDTH }}>
          <span className="legend-item">
            <span className="legend-swatch ref" />
            Reference
          </span>
          {model.take ? (
            <span className="legend-item">
              <span className="legend-swatch take" />
              Take
            </span>
          ) : null}
        </div>
        <Minimap
          model={model}
          theme={theme}
          width={width}
          heat={model.comparison?.heatmap.views.fine ?? null}
        />
      </div>
      <div ref={scroller} className="timeline-scroll">
        <div className="timeline-grid" style={{ gridTemplateColumns: `${HEADER_WIDTH}px minmax(0, 1fr)` }}>
          <div className="lane-headers">
            {lanes.map((lane) => (
              <div
                key={lane.id}
                className={`lane-header lane-header-${lane.id}`}
                style={{ height: lane.height }}
              >
                <div className="lane-header-top">
                  <Tooltip content={lane.help} side="right">
                    <span className="lane-title">{lane.title}</span>
                  </Tooltip>
                  {lane.id !== 'ruler' ? (
                    <button
                      type="button"
                      className="lane-hide"
                      aria-label={`Hide ${lane.title}`}
                      title={`Hide ${lane.title}`}
                      onClick={() =>
                        toggleLayer(
                          mode,
                          (lane.id === 'spectrogram' && !layers.spectrogram
                            ? 'formants'
                            : lane.id) as LayerId,
                          false,
                        )
                      }
                    >
                      <Icon name="eye-off" size={12} />
                    </button>
                  ) : null}
                </div>
                {lane.legend && lane.height >= 44 ? (
                  <div className="lane-legend">
                    <span className="ref-text">ref</span>
                    <span className="take-text">take</span>
                  </div>
                ) : null}
                {lane.header ? <div className="lane-header-extra">{lane.header}</div> : null}
                {lane.id !== 'ruler' ? (
                  <div
                    className="lane-resize"
                    onPointerDown={startResize(lane)}
                    role="separator"
                    aria-orientation="horizontal"
                    aria-label={`Resize ${lane.title}`}
                  />
                ) : null}
              </div>
            ))}
          </div>
          <div
            ref={bodies}
            className={`lane-bodies${rulerActive ? ' is-measuring' : ''}`}
            tabIndex={0}
            role="application"
            aria-label="Timeline lanes. Space plays, arrow keys seek, drag to select a region."
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={() => {
              window.cancelAnimationFrame(hoverFrame.current)
              if (!drag.current) useWorkspace.setState({ hover: null })
            }}
            onDoubleClick={onDoubleClick}
            onContextMenu={(event) => onContextMenu(event, locate(event).t)}
          >
            {lanes.map((lane) => (
              <div
                key={lane.id}
                className={`lane-body lane-body-${lane.id}`}
                data-lane={lane.id}
                style={{ height: lane.height }}
              >
                {width > 0 ? lane.body : null}
              </div>
            ))}
            {width > 0 ? (
              <Overlay view={view} model={model} showConfidence={layers.confidence} follow={follow} />
            ) : null}
          </div>
        </div>
      </div>
    </section>
  )
}

function pinAt(model: TimelineModel, t: number) {
  const u = takeTime(model, t)
  const refHz = sampleTrack(model.ref?.features, 'f0_hz', t)
  const takeHz = sampleTrack(model.take?.features, 'f0_hz', u)
  const refLevel = sampleTrack(model.ref?.features, 'level_rel_db', t)
  const takeLevel = sampleTrack(model.take?.features, 'level_rel_db', u)
  const refF1 = sampleTrack(model.ref?.features, 'f1_hz', t)
  const takeF1 = sampleTrack(model.take?.features, 'f1_hz', u)
  const refF2 = sampleTrack(model.ref?.features, 'f2_hz', t)
  const takeF2 = sampleTrack(model.take?.features, 'f2_hz', u)
  const fmt = (hz: number | null) => (hz && hz > 30 ? describeHz(hz) : '–')
  const hz = (value: number | null) => (value && value > 0 ? `${value.toFixed(0)} Hz` : '–')
  return {
    id: nextPinId(),
    time: t,
    label: `Pin at ${t.toFixed(2)} s`,
    values: [
      { name: 'Pitch', ref: fmt(refHz), take: fmt(takeHz) },
      { name: 'Level', ref: formatDb(refLevel), take: formatDb(takeLevel) },
      { name: 'F1', ref: hz(refF1), take: hz(takeF1) },
      { name: 'F2', ref: hz(refF2), take: hz(takeF2) },
    ],
  }
}
