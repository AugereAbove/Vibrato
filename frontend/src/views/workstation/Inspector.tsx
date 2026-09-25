import { useState, type ReactNode } from 'react'
import { comparisonsApi, recordingsApi } from '../../api/endpoints'
import type { AnalysisEvent, AnalysisResult, Comparison, MetricComparison } from '../../api/types'
import { engine } from '../../audio/engine'
import { fitRange } from '../../components/timeline/viewport'
import { Badge, BasisTag, ConfidenceBadge } from '../../components/ui/Badge'
import { Button, IconButton } from '../../components/ui/Button'
import { EmptyState } from '../../components/ui/Feedback'
import { Icon } from '../../components/ui/Icon'
import { ScoreRing } from '../../components/ui/Motion'
import { Tooltip } from '../../components/ui/Tooltip'
import {
  ancestor,
  isFlagged,
  magnitude,
  metricName,
  metricUnit,
  metricsInRange,
  sortByImportance,
  type AnalysisIndex,
} from '../../lib/analysis'
import { CATEGORY_ORDER, categoryLabel } from '../../lib/categories'
import {
  CONFIDENCE_TEXT,
  confidenceLevel,
  formatPercent,
  formatTime,
  formatUnitValue,
  humanize,
} from '../../lib/format'
import { formatMetricDifference, formatMetricValue, severity } from '../../lib/metricFormat'
import type { ViewMode } from '../../state/prefs'
import { setUi } from '../../state/ui'
import { useWorkspace, type Selection } from '../../state/workspace'
import { EVENT_LABELS } from '../../components/timeline/lanes/events'
import type { WorkstationData } from './useWorkstation'
import { addBookmark, loopRegion, realignRegion } from './actions'
import { openWhy } from './coach/whyStore'
import { showFinding } from './coach/focus'

function Section({
  title,
  children,
  defaultOpen = true,
  extra,
}: {
  title: string
  children: ReactNode
  defaultOpen?: boolean
  extra?: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className="panel-section">
      <div className="row" style={{ paddingRight: 8 }}>
        <button
          type="button"
          className="panel-section-header"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <Icon name="chevron-down" size={12} className="chevron" />
          {title}
        </button>
        {extra}
      </div>
      {open ? <div className="panel-section-body">{children}</div> : null}
    </section>
  )
}

function ListenControls({
  start,
  end,
  takeStart,
  takeEnd,
}: {
  start: number
  end: number
  takeStart?: number | null
  takeEnd?: number | null
}) {
  return (
    <div className="listen-controls">
      <Button size="sm" variant="subtle" icon="play" onClick={() => void engine.playRange('ref', start, end)}>
        <span className="ref-text">Reference</span>
      </Button>
      <Button
        size="sm"
        variant="subtle"
        icon="play"
        disabled={takeStart == null || !engine.state.hasTake}
        onClick={() => void engine.playRange('take', start, end)}
      >
        <span className="take-text">You</span>
      </Button>
      <Tooltip content="Loop this passage, alternating reference and take">
        <Button
          size="sm"
          variant="subtle"
          icon="compare"
          disabled={!engine.state.hasTake}
          onClick={() => {
            loopRegion({ start, end })
            engine.setMode('ref')
            engine.setAlternate(true)
            void engine.play(start)
          }}
        >
          A/B
        </Button>
      </Tooltip>
      <IconButton
        icon="loop"
        label="Loop this passage"
        size="sm"
        variant="subtle"
        onClick={() => {
          loopRegion({ start, end })
          void engine.play(start)
        }}
      />
      <IconButton
        icon="fit"
        label="Zoom to this"
        size="sm"
        variant="subtle"
        onClick={() => fitRange(start, end, 0.4)}
      />
      {takeStart != null && takeEnd != null ? (
        <span className="sr-only">
          Take time {formatTime(takeStart)} to {formatTime(takeEnd)}
        </span>
      ) : null}
    </div>
  )
}

function MetricTable({
  metrics,
  comparison,
  mode,
}: {
  metrics: MetricComparison[]
  comparison: Comparison | null
  mode: ViewMode
}) {
  if (metrics.length === 0) return <p className="faint small">No compared measurements here.</p>
  return (
    <table className="metric-table">
      <thead>
        <tr>
          <th scope="col">Measure</th>
          <th scope="col" className="ref-text">
            Reference
          </th>
          <th scope="col" className="take-text">
            You
          </th>
          <th scope="col">Difference</th>
          {mode !== 'coach' ? <th scope="col">Conf.</th> : null}
        </tr>
      </thead>
      <tbody>
        {metrics.map((metric) => {
          const unit = metricUnit(comparison, metric)
          const level = severity(metric)
          return (
            <tr
              key={`${metric.metric_id}:${metric.ref_segment_id}:${metric.ref_start}`}
              className={`sev-${level}`}
            >
              <th scope="row">
                <Tooltip
                  content={
                    comparison?.scores.categories[metric.category]?.metrics[metric.metric_id]
                      ?.normalisation ?? metric.metric_id
                  }
                >
                  <span className="metric-name">{metricName(comparison, metric)}</span>
                </Tooltip>
              </th>
              <td className="num">{formatMetricValue(metric, 'ref', unit)}</td>
              <td className="num">{formatMetricValue(metric, 'user', unit)}</td>
              <td className="num diff-cell">
                <span className={`sev-dot sev-dot-${level}`} aria-hidden />
                {level === 'uncertain' ? (
                  <span className="faint">uncertain</span>
                ) : (
                  formatMetricDifference(metric, unit)
                )}
              </td>
              {mode !== 'coach' ? <td className="num faint">{formatPercent(metric.confidence)}</td> : null}
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function interpretation(metrics: MetricComparison[], comparison: Comparison | null): string {
  if (metrics.length === 0)
    return 'Insufficient confidence: nothing here could be measured reliably in both performances.'
  const reliable = metrics.filter((m) => m.confidence >= 0.45 && m.weight > 0)
  if (reliable.length === 0)
    return 'Insufficient confidence: the measurements here are too uncertain to interpret.'
  const flagged = sortByImportance(reliable.filter(isFlagged))
  const closeCategories = CATEGORY_ORDER.filter((category) => {
    const list = reliable.filter((m) => m.category === category)
    return list.length > 0 && list.every((m) => magnitude(m) < 1)
  })
  if (flagged.length === 0) {
    return `Already close: ${closeCategories.map((c) => categoryLabel(c).toLowerCase()).join(', ') || 'every reliable measurement'} ${closeCategories.length === 1 ? 'is' : 'are'} within tolerance here.`
  }
  const top = flagged[0]
  const lead = closeCategories.length
    ? `${closeCategories
        .slice(0, 2)
        .map((c) => categoryLabel(c))
        .join(' and ')} ${closeCategories.length === 1 ? 'is' : 'are'} already close. `
    : ''
  return `${lead}The more important difference here is ${metricName(comparison, top).toLowerCase()}: ${top.direction} (${formatMetricDifference(top, metricUnit(comparison, top))}).`
}

function categoryConfidence(metrics: MetricComparison[]): { category: string; value: number }[] {
  const out: { category: string; value: number }[] = []
  for (const category of CATEGORY_ORDER) {
    const values = metrics.filter((m) => m.category === category).map((m) => m.confidence)
    if (values.length) out.push({ category, value: Math.min(...values) })
  }
  return out
}

function RawResults({
  title,
  results,
  tone,
}: {
  title: string
  results: AnalysisResult[]
  tone: 'ref' | 'take'
}) {
  if (results.length === 0) return null
  return (
    <div className="raw-results">
      <span className={`eyebrow ${tone}-text`}>{title}</span>
      {results.map((result) => (
        <details key={`${result.analyzer_id}:${result.segment_id}`} className="raw-result">
          <summary>
            <span className="grow">{humanize(result.analyzer_id)}</span>
            <Badge
              tone={
                result.validity === 'VALID'
                  ? 'good'
                  : result.validity === 'LOW_CONFIDENCE'
                    ? 'warn'
                    : 'neutral'
              }
            >
              {result.validity.replace('_', ' ').toLowerCase()}
            </Badge>
            <span className="num faint">{formatPercent(result.confidence)}</span>
          </summary>
          <dl className="kv">
            {Object.entries(result.values).map(([key, value]) => (
              <div key={key} style={{ display: 'contents' }}>
                <dt>
                  {humanize(key)} {result.basis[key] ? <BasisTag basis={result.basis[key]} /> : null}
                </dt>
                <dd>{formatUnitValue(value, result.units[key])}</dd>
              </div>
            ))}
          </dl>
          {result.confidence_reasons.length ? (
            <p className="faint tiny">Confidence: {result.confidence_reasons.join('; ')}</p>
          ) : null}
          {result.warning_flags.length ? (
            <p className="warn-text tiny">Flags: {result.warning_flags.join(', ')}</p>
          ) : null}
          {result.derived_interpretation ? (
            <p className="tiny muted">
              {result.derived_interpretation.text} <BasisTag basis={result.derived_interpretation.basis} />{' '}
              <span className="faint">({formatPercent(result.derived_interpretation.confidence)})</span>
            </p>
          ) : null}
          <p className="faint tiny">
            {result.analyzer_id} v{result.analyzer_version}
          </p>
        </details>
      ))}
    </div>
  )
}

function SegmentDetails({
  selection,
  data,
  mode,
}: {
  selection: Extract<Selection, { kind: 'segment' }>
  data: WorkstationData
  mode: ViewMode
}) {
  const { refIndex, takeIndex, cindex, comparison } = data
  const refSegment = selection.refId ? (refIndex?.segments.get(selection.refId) ?? null) : null
  const takeSegment = selection.takeId ? (takeIndex?.segments.get(selection.takeId) ?? null) : null
  const direct = selection.refId
    ? (cindex?.byRefSegment.get(selection.refId) ?? [])
    : selection.takeId
      ? (cindex?.byUserSegment.get(selection.takeId) ?? [])
      : []
  const broad = selection.level === 'word' || selection.level === 'phrase' || selection.level === 'section'
  const metrics = broad && comparison ? metricsInRange(comparison, selection.start, selection.end) : direct
  const sorted = broad
    ? sortByImportance(metrics).slice(0, mode === 'coach' ? 8 : 24)
    : [...metrics].sort((a, b) => a.category.localeCompare(b.category))
  const findings = selection.refId ? (cindex?.findingsBySegment.get(selection.refId) ?? []) : []
  const finding = findings[0] ?? null
  const phrase = refSegment && refIndex ? ancestor(refIndex, refSegment, 'phrase') : null
  const word = refSegment && refIndex ? ancestor(refIndex, refSegment, 'word') : null
  const confidences = categoryConfidence(metrics)
  const refResults = refSegment ? (refIndex?.results.get(refSegment.id) ?? []) : []
  const takeResults = takeSegment ? (takeIndex?.results.get(takeSegment.id) ?? []) : []
  return (
    <>
      <div className="inspector-title">
        <Badge tone="accent">{humanize(selection.level)}</Badge>
        <h3 className="truncate">{selection.label}</h3>
        {word && word.id !== refSegment?.id ? <span className="muted">“{word.label}”</span> : null}
      </div>
      <p className="faint small">
        {phrase && phrase.id !== refSegment?.id ? `${phrase.label} · ` : ''}
        {formatTime(selection.start)} – {formatTime(selection.end)}
        {takeSegment
          ? ` · your take ${formatTime(takeSegment.start_s)} – ${formatTime(takeSegment.end_s)}`
          : ''}
      </p>
      <ListenControls
        start={selection.start}
        end={selection.end}
        takeStart={takeSegment?.start_s}
        takeEnd={takeSegment?.end_s}
      />
      {!takeSegment && selection.refId && data.take && comparison ? (
        <p className="warn-text small">
          No matching part of your take was found for this. It may be missing or too different to align.
        </p>
      ) : null}
      <Section title="Interpretation">
        <p className="inspector-interpretation">
          {finding
            ? mode === 'coach'
              ? finding.texts.beginner
              : finding.texts.expert
            : interpretation(metrics, comparison)}
        </p>
        {finding ? (
          <div className="stack" style={{ gap: 6, marginTop: 8 }}>
            <p className="small">
              <span className="eyebrow">Coaching</span>
              <br />
              {finding.texts.adjust} <BasisTag basis={finding.texts.adjust_basis} />
            </p>
            <div className="row-wrap">
              <ConfidenceBadge value={finding.confidence} />
              <Badge>{finding.texts.importance_label}</Badge>
              <Button size="xs" variant="ghost" icon="target" onClick={() => showFinding(finding, mode)}>
                Practice this
              </Button>
            </div>
          </div>
        ) : null}
      </Section>
      <Section title={broad ? 'Largest differences here' : 'Reference · You · Difference'}>
        <MetricTable metrics={sorted} comparison={comparison} mode={mode} />
      </Section>
      {confidences.length ? (
        <Section title="Confidence" defaultOpen={mode !== 'coach'}>
          <div className="confidence-list">
            {confidences.map((item) => (
              <div key={item.category} className="confidence-item">
                <span>{categoryLabel(item.category)}</span>
                <span className={`num conf-${confidenceLevel(item.value)}`}>{formatPercent(item.value)}</span>
              </div>
            ))}
          </div>
          <p className="faint tiny">
            Lowest confidence among the measurements of each category for this selection.
          </p>
        </Section>
      ) : null}
      {mode !== 'coach' ? (
        <Section title="Raw analyzer output" defaultOpen={mode === 'research'}>
          <RawResults title="Reference" results={refResults} tone="ref" />
          <RawResults title="Your take" results={takeResults} tone="take" />
          {refResults.length + takeResults.length === 0 ? (
            <p className="faint small">No analyzer results are attached to this segment.</p>
          ) : null}
        </Section>
      ) : null}
    </>
  )
}

function matchEvent(
  event: AnalysisEvent,
  other: AnalysisIndex | null,
  map: (t: number) => number,
): AnalysisEvent | null {
  if (!other) return null
  const target = map(event.start_s)
  let best: AnalysisEvent | null = null
  let distance = 0.4
  for (const candidate of other.events) {
    if (candidate.type !== event.type) continue
    const d = Math.abs(candidate.start_s - target)
    if (d < distance) {
      distance = d
      best = candidate
    }
  }
  return best
}

function EventDetails({
  selection,
  data,
}: {
  selection: Extract<Selection, { kind: 'event' }>
  data: WorkstationData
}) {
  const own = selection.side === 'take' ? data.takeIndex : data.refIndex
  const other = selection.side === 'take' ? data.refIndex : data.takeIndex
  const event = own?.events.find((e) => e.id === selection.eventId) ?? null
  if (!event) return <EmptyState compact title="This event is no longer available" />
  const toOther = (t: number) =>
    selection.side === 'take' ? data.model.map.userToRef(t) : data.model.map.refToUser(t)
  const counterpart = matchEvent(event, other, data.model.aligned ? toOther : (t) => t)
  const props = (e: AnalysisEvent | null) =>
    Object.entries(e?.props ?? {}).filter(([, v]) => typeof v !== 'object' || v === null)
  return (
    <>
      <div className="inspector-title">
        <Badge tone={selection.side === 'take' ? 'take' : 'ref'}>
          {selection.side === 'take' ? 'Your take' : 'Reference'}
        </Badge>
        <h3>{EVENT_LABELS[event.type] ?? humanize(event.type)}</h3>
      </div>
      <p className="faint small">
        {formatTime(event.start_s)} – {formatTime(event.end_s)} ·{' '}
        {((event.end_s - event.start_s) * 1000).toFixed(0)} ms
      </p>
      <ListenControls start={selection.start} end={Math.max(selection.end, selection.start + 0.25)} />
      <Section title="Measurements">
        <dl className="kv">
          <dt>Confidence</dt>
          <dd>
            <ConfidenceBadge value={event.confidence} compact />
          </dd>
          {props(event).map(([key, value]) => (
            <div key={key} style={{ display: 'contents' }}>
              <dt>{humanize(key)}</dt>
              <dd>{formatUnitValue(value)}</dd>
            </div>
          ))}
        </dl>
      </Section>
      <Section title={selection.side === 'take' ? 'In the reference' : 'In your take'}>
        {counterpart ? (
          <dl className="kv">
            <dt>Time</dt>
            <dd className="num">
              {formatTime(counterpart.start_s)} – {formatTime(counterpart.end_s)}
            </dd>
            {props(counterpart).map(([key, value]) => (
              <div key={key} style={{ display: 'contents' }}>
                <dt>{humanize(key)}</dt>
                <dd>{formatUnitValue(value)}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="small muted">
            No matching {EVENT_LABELS[event.type]?.toLowerCase() ?? event.type} was found nearby
            {selection.side === 'ref' ? ' in your take.' : ' in the reference.'}
          </p>
        )}
      </Section>
    </>
  )
}

function RegionDetails({ data, mode }: { data: WorkstationData; mode: ViewMode }) {
  const region = useWorkspace((s) => s.region)
  const [busy, setBusy] = useState(false)
  if (!region) return null
  const metrics = data.comparison ? metricsInRange(data.comparison, region.start, region.end) : []
  const flagged = sortByImportance(metrics.filter(isFlagged)).slice(0, 8)
  const refRecording = data.reference
  const takeRecording = data.take
  const u0 = data.model.aligned ? data.model.map.refToUser(region.start) : region.start
  const u1 = data.model.aligned ? data.model.map.refToUser(region.end) : region.end
  return (
    <>
      <div className="inspector-title">
        <Badge tone="accent">Selection</Badge>
        <h3 className="num">
          {formatTime(region.start)} – {formatTime(region.end)}
        </h3>
      </div>
      <p className="faint small">
        {(region.end - region.start).toFixed(2)} s · {metrics.length} measurements
      </p>
      <ListenControls start={region.start} end={region.end} takeStart={u0} takeEnd={u1} />
      <div className="stack" style={{ gap: 6, padding: '4px 12px 10px' }}>
        {data.comparison ? (
          <Button variant="accent-soft" icon="bulb" onClick={() => openWhy(region)}>
            Why does this sound different?
          </Button>
        ) : null}
        <div className="row-wrap">
          {refRecording ? (
            <Button
              size="sm"
              variant="ghost"
              icon="bookmark"
              onClick={() => void addBookmark(refRecording.id, region.start, region.end, 'Selection')}
            >
              Bookmark
            </Button>
          ) : null}
          {data.comparison ? (
            <a
              className="btn btn-ghost btn-sm"
              href={comparisonsApi.abUrl(data.comparison.id, region.start, region.end)}
              download
            >
              <Icon name="download" size={15} />
              A/B snippet
            </a>
          ) : null}
          {refRecording ? (
            <a
              className="btn btn-ghost btn-sm"
              href={recordingsApi.segmentUrl(refRecording.id, region.start, region.end)}
              download
            >
              <Icon name="download" size={15} />
              Reference audio
            </a>
          ) : null}
          {takeRecording ? (
            <a
              className="btn btn-ghost btn-sm"
              href={recordingsApi.segmentUrl(takeRecording.id, Math.max(0, u0), Math.max(u0 + 0.05, u1))}
              download
            >
              <Icon name="download" size={15} />
              Take audio
            </a>
          ) : null}
          {data.comparison && takeRecording && mode !== 'coach' ? (
            <Button
              size="sm"
              variant="ghost"
              icon="anchor"
              loading={busy}
              onClick={async () => {
                setBusy(true)
                await realignRegion(data.projectId, data.comparison!.id, takeRecording.id, region)
                setBusy(false)
              }}
            >
              Realign region
            </Button>
          ) : null}
        </div>
      </div>
      <Section title="Largest differences in the selection">
        <MetricTable
          metrics={flagged.length ? flagged : sortByImportance(metrics).slice(0, 6)}
          comparison={data.comparison}
          mode={mode}
        />
      </Section>
    </>
  )
}

function Overview({ data, mode }: { data: WorkstationData; mode: ViewMode }) {
  const comparison = data.comparison
  if (!comparison) {
    return (
      <EmptyState compact icon="info" title="Nothing selected">
        Click a note, word, event or heatmap cell on the timeline to inspect it. Drag across the timeline to
        select a region.
      </EmptyState>
    )
  }
  const categories = comparison.scores.categories
  const previous = comparison.previous?.categories ?? null
  return (
    <>
      <div className="inspector-title">
        <Badge tone="take">Take {data.take?.take_number ?? ''}</Badge>
        <h3 className="truncate">vs reference</h3>
      </div>
      <p className="faint small">Nothing selected. Click something on the timeline for details.</p>
      <Section title="Category scores">
        <div className="category-bars">
          {CATEGORY_ORDER.map((category) => {
            const score = categories[category]
            if (!score) return null
            const prev = previous?.[category]?.score ?? null
            return (
              <button
                key={category}
                type="button"
                className={`category-bar${score.enabled ? '' : ' is-disabled'}`}
                onClick={() => {
                  setUi({
                    bottomOpen: true,
                    bottomTab: 'measurements',
                    tableFilters: {
                      category,
                      minConfidence: 0,
                      minMagnitude: 0,
                      search: '',
                      onlyFlagged: false,
                    },
                  })
                }}
              >
                <span className="category-bar-label">
                  <span className="cat-dot" style={{ background: `var(--cat-${category})` }} />
                  {score.label}
                </span>
                <span className="category-bar-track">
                  {prev != null ? <span className="category-bar-prev" style={{ width: `${prev}%` }} /> : null}
                  <span
                    className={`category-bar-fill${score.confidence < 0.5 ? ' is-uncertain' : ''}`}
                    style={{ width: `${score.score ?? 0}%`, background: `var(--cat-${category})` }}
                  />
                </span>
                <span className="num category-bar-value">
                  {score.score == null ? '–' : score.score.toFixed(0)}
                </span>
              </button>
            )
          })}
        </div>
        <p className="faint tiny">
          Faint bars show the previous take. Scores are 100 when every measurement is within its tolerance;
          low-confidence categories are drawn translucent.
        </p>
      </Section>
      <Section title="Alignment" defaultOpen={mode !== 'coach'}>
        <dl className="kv">
          <dt>Confidence</dt>
          <dd>{CONFIDENCE_TEXT[confidenceLevel(comparison.alignment.overall_confidence)]}</dd>
          <dt>Tempo ratio</dt>
          <dd className="num">{comparison.alignment.tempo_ratio.toFixed(3)}</dd>
          <dt>Transposition</dt>
          <dd className="num">
            {comparison.alignment.transposition_semitones
              ? `${comparison.alignment.transposition_semitones} semitones`
              : 'none'}
          </dd>
          <dt>Matched notes</dt>
          <dd className="num">
            {comparison.coverage.matched_notes} / {comparison.coverage.reference_notes}
          </dd>
          <dt>Matched phrases</dt>
          <dd className="num">
            {comparison.coverage.matched_phrases} / {comparison.coverage.reference_phrases}
          </dd>
        </dl>
        {comparison.alignment.warnings.length ? (
          <p className="warn-text tiny">{comparison.alignment.warnings.join(' ')}</p>
        ) : null}
      </Section>
      {comparison.extras.embedding_similarity && mode === 'research' ? (
        <Section title="Overall similarity (not scored)">
          <div className="row">
            <ScoreRing score={comparison.extras.embedding_similarity.cosine_similarity * 100} size={36} />
            <p className="tiny muted">
              {comparison.extras.embedding_similarity.kind}. {comparison.extras.embedding_similarity.note}
            </p>
          </div>
        </Section>
      ) : null}
    </>
  )
}

export function Inspector({
  data,
  mode,
  onClose,
}: {
  data: WorkstationData
  mode: ViewMode
  onClose: () => void
}) {
  const selection = useWorkspace((s) => s.selection)
  const region = useWorkspace((s) => s.region)
  const pins = useWorkspace((s) => s.pins)
  const pulse = useWorkspace((s) => s.pulse)
  let body: ReactNode
  if (selection?.kind === 'segment') body = <SegmentDetails selection={selection} data={data} mode={mode} />
  else if (selection?.kind === 'event') body = <EventDetails selection={selection} data={data} />
  else if (region) body = <RegionDetails data={data} mode={mode} />
  else body = <Overview data={data} mode={mode} />
  return (
    <aside className="inspector" aria-label="Inspector">
      <header className="panel-header">
        <span className="panel-title">Inspector</span>
        <span className="spacer" />
        {selection || region ? (
          <IconButton
            icon="x"
            label="Clear selection"
            size="xs"
            onClick={() => useWorkspace.setState({ selection: null, region: null })}
          />
        ) : null}
        <IconButton icon="chevron-right" label="Collapse inspector" size="xs" onClick={onClose} />
      </header>
      <div className="inspector-body" key={pulse}>
        {body}
        {pins.length ? (
          <Section
            title={`Pinned measurements (${pins.length})`}
            extra={
              <Button size="xs" variant="ghost" onClick={() => useWorkspace.setState({ pins: [] })}>
                Clear
              </Button>
            }
          >
            {pins.map((pin) => (
              <div key={pin.id} className="pin-card">
                <div className="row">
                  <Icon name="pin" size={12} />
                  <strong className="num">{formatTime(pin.time)}</strong>
                  <span className="spacer" />
                  <IconButton
                    icon="x"
                    label="Remove pin"
                    size="xs"
                    onClick={() =>
                      useWorkspace.setState((s) => ({ pins: s.pins.filter((p) => p.id !== pin.id) }))
                    }
                  />
                </div>
                <table className="metric-table compact">
                  <tbody>
                    {pin.values.map((row) => (
                      <tr key={row.name}>
                        <th scope="row">{row.name}</th>
                        <td className="num ref-text">{row.ref}</td>
                        <td className="num take-text">{row.take}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </Section>
        ) : null}
        {mode !== 'coach' && selection?.kind === 'segment' && data.comparison ? (
          <p className="faint tiny" style={{ padding: '8px 12px' }}>
            Values are measured on each performance separately and compared after alignment
            {data.comparison.alignment.transposition_semitones ? ' and transposition' : ''}.
          </p>
        ) : null}
      </div>
    </aside>
  )
}
