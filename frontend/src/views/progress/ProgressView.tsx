import { useMemo, useState } from 'react'
import { projectsApi, recordingsApi } from '../../api/endpoints'
import type { CategoryId, TakeHistoryEntry } from '../../api/types'
import { LineChart, Sparkline, type Series } from '../../components/charts/LineChart'
import { Badge, CategoryChip, ConfidenceBadge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Segmented, TextField } from '../../components/ui/Controls'
import { Callout, EmptyState, ErrorState, SkeletonLines } from '../../components/ui/Feedback'
import { Icon } from '../../components/ui/Icon'
import { AnimatedNumber } from '../../components/ui/Motion'
import { scoreTone } from '../../lib/score'
import { Tooltip } from '../../components/ui/Tooltip'
import { CATEGORY_ORDER, categoryLabel } from '../../lib/categories'
import { formatDate, formatDuration, formatNumber, formatScore, relativeTime } from '../../lib/format'
import { keys, useProgress } from '../../state/data'
import { attempt } from '../../state/errors'
import type { ViewMode } from '../../state/prefs'
import { invalidate } from '../../state/resource'
import { navigate } from '../../state/router'
import type { WorkstationData } from '../workstation/useWorkstation'

function Stat({
  label,
  value,
  sub,
  decimals = 0,
}: {
  label: string
  value: number | null | undefined
  sub?: React.ReactNode
  decimals?: number
}) {
  return (
    <div className="stat card">
      <span className="eyebrow">{label}</span>
      <span className="stat-value num">
        <AnimatedNumber value={value} decimals={decimals} />
      </span>
      {sub ? <span className="small muted">{sub}</span> : null}
    </div>
  )
}

function Calendar({ days }: { days: { date: string; takes: number; minutes: number }[] }) {
  const map = new Map(days.map((d) => [d.date, d]))
  const today = new Date()
  const cells: { date: string; takes: number; minutes: number }[] = []
  for (let i = 7 * 12 - 1; i >= 0; i -= 1) {
    const d = new Date(today)
    d.setDate(today.getDate() - i)
    const key = d.toISOString().slice(0, 10)
    cells.push(map.get(key) ?? { date: key, takes: 0, minutes: 0 })
  }
  return (
    <div className="calendar" role="img" aria-label="Practice days over the last twelve weeks">
      {cells.map((cell) => (
        <Tooltip
          key={cell.date}
          content={`${cell.date}: ${cell.takes} take${cell.takes === 1 ? '' : 's'}, ${Math.round(cell.minutes)} min`}
        >
          <span className={`calendar-cell level-${Math.min(4, cell.takes)}`} />
        </Tooltip>
      ))}
    </div>
  )
}

function TakeNotes({ take, projectId }: { take: TakeHistoryEntry; projectId: string }) {
  const [value, setValue] = useState(take.notes)
  const [editing, setEditing] = useState(false)
  if (!editing) {
    return (
      <button type="button" className="link-button" onClick={() => setEditing(true)}>
        {take.notes ? (
          <span className="truncate">{take.notes}</span>
        ) : (
          <span className="faint">Add note</span>
        )}
      </button>
    )
  }
  return (
    <input
      className="input"
      autoFocus
      value={value}
      aria-label={`Notes for ${take.take_name}`}
      onChange={(event) => setValue(event.target.value)}
      onBlur={async () => {
        setEditing(false)
        if (value === take.notes) return
        await attempt(() => recordingsApi.update(take.take_id, { notes: value }), 'Note was not saved')
        invalidate(keys.project(projectId))
        invalidate((key) => key.startsWith(`progress:${projectId}`))
      }}
      onKeyDown={(event) => event.key === 'Enter' && (event.target as HTMLInputElement).blur()}
    />
  )
}

export function ProgressView({ data, mode }: { data: WorkstationData; mode: ViewMode }) {
  const progress = useProgress(data.projectId, data.reference?.id ?? null)
  const [category, setCategory] = useState<'overall' | CategoryId>('overall')
  const [search, setSearch] = useState('')
  const [weaknessFilter, setWeaknessFilter] = useState<'persistent' | 'all'>('persistent')
  const takes = useMemo(() => progress.data?.takes ?? [], [progress.data])
  const filteredTakes = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return takes
    return takes.filter((t) =>
      `${t.take_name} ${t.notes} ${t.primary_focus ?? ''} ${formatDate(t.created_at)}`
        .toLowerCase()
        .includes(q),
    )
  }, [takes, search])
  if (!data.reference) {
    return (
      <div className="page">
        <div className="page-inner">
          <EmptyState icon="trend-up" title="No reference yet">
            Progress is tracked per reference. Import a reference and compare a few takes first.
          </EmptyState>
        </div>
      </div>
    )
  }
  if (progress.loading) {
    return (
      <div className="page">
        <div className="page-inner">
          <SkeletonLines lines={8} />
        </div>
      </div>
    )
  }
  if (progress.error || !progress.data) {
    return (
      <div className="page">
        <div className="page-inner">
          <ErrorState error={progress.error} onRetry={() => void progress.refresh()} />
        </div>
      </div>
    )
  }
  const p = progress.data
  const labels = takes.map((t) => `#${t.take_number ?? '?'}`)
  const trendKey = category
  const trend = p.trends[trendKey]
  const series: Series[] = trend
    ? [
        {
          id: 'series',
          label: trend.label,
          color: category === 'overall' ? 'var(--accent)' : `var(--cat-${category})`,
          values: trend.series,
          confidence: takes.map((t) =>
            category === 'overall' ? t.confidence : (t.category_confidence[category] ?? null),
          ),
        },
        {
          id: 'rolling',
          label: 'Rolling average',
          color: 'var(--text-3)',
          values: trend.rolling,
          dashed: true,
          width: 1.5,
        },
      ]
    : []
  const totalMinutes = p.sessions.reduce((sum, s) => sum + s.active_seconds / 60, 0)
  const weaknesses = weaknessFilter === 'persistent' ? p.weaknesses.filter((w) => w.persistent) : p.weaknesses
  return (
    <div className="page progress-page">
      <div className="page-inner wide">
        <div className="page-header">
          <div>
            <h1>Progress</h1>
            <p className="muted">
              Against “{data.reference.name}” · {takes.length} compared take{takes.length === 1 ? '' : 's'}
            </p>
          </div>
          <div className="row-wrap">
            <a className="btn btn-ghost btn-md" href={projectsApi.progressCsvUrl(data.projectId)} download>
              <Icon name="download" size={15} /> Progress CSV
            </a>
            <a
              className="btn btn-secondary btn-md"
              href={projectsApi.reportUrl(data.projectId, data.comparison?.id ?? null, true)}
              download
            >
              <Icon name="file" size={15} /> Session report
            </a>
          </div>
        </div>
        {takes.length === 0 ? (
          <EmptyState
            icon="trend-up"
            title="No takes compared yet"
            actions={
              <Button
                variant="primary"
                onClick={() => navigate({ name: 'project', projectId: data.projectId, tab: 'compare' })}
              >
                Go to compare
              </Button>
            }
          >
            Every take you record or import is stored and compared, so your history starts with the first one.
          </EmptyState>
        ) : (
          <>
            <div className="stat-row">
              <Stat
                label="Latest take"
                value={p.latest_take?.overall}
                sub={
                  p.trends.overall?.delta != null
                    ? `${p.trends.overall.delta >= 0 ? '+' : '−'}${Math.abs(p.trends.overall.delta).toFixed(1)} vs previous`
                    : undefined
                }
              />
              <Stat
                label="Best take"
                value={p.best_take?.overall}
                sub={p.best_take ? p.best_take.take_name : undefined}
              />
              <Stat
                label="Takes"
                value={takes.length}
                sub={`${p.sessions.length} session${p.sessions.length === 1 ? '' : 's'}`}
              />
              <Stat label="Practice time" value={Math.round(totalMinutes)} sub="minutes of active practice" />
            </div>
            {p.regressions.length ? (
              <Callout tone="warn" title="Recent regressions">
                {p.regressions.map((r) => r.text).join(' ')} One take is noisy evidence: check the recording
                quality before changing anything.
              </Callout>
            ) : null}
            <section className="card card-pad">
              <div className="row-wrap" style={{ justifyContent: 'space-between' }}>
                <h3>Score history</h3>
                <div className="chip-row">
                  <button
                    type="button"
                    className={`chip${category === 'overall' ? ' is-active' : ''}`}
                    onClick={() => setCategory('overall')}
                  >
                    Overall
                  </button>
                  {CATEGORY_ORDER.map((c) => (
                    <CategoryChip
                      key={c}
                      category={c}
                      active={category === c}
                      onClick={() => setCategory(c)}
                    />
                  ))}
                </div>
              </div>
              <LineChart
                series={series}
                labels={labels}
                ariaLabel={`${trend?.label ?? 'Score'} per take`}
                onPointClick={(index) =>
                  navigate({
                    name: 'project',
                    projectId: data.projectId,
                    tab: 'compare',
                    take: takes[index].take_id,
                  })
                }
              />
              {trend ? (
                <p className="small muted">
                  Best {formatScore(trend.best)} · latest {formatScore(trend.latest)} · trend{' '}
                  {trend.slope_per_take == null
                    ? '–'
                    : `${trend.slope_per_take >= 0 ? '+' : '−'}${Math.abs(trend.slope_per_take).toFixed(1)} per take`}
                  .{' '}
                  <span className="faint">
                    Hollow points are low-confidence takes; the dashed line is a confidence-weighted rolling
                    average.
                  </span>
                </p>
              ) : null}
            </section>
            <div className="progress-grid">
              <section className="card card-pad">
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <h3>Recurring weaknesses</h3>
                  <Segmented
                    size="sm"
                    ariaLabel="Weakness filter"
                    value={weaknessFilter}
                    onChange={setWeaknessFilter}
                    options={[
                      { value: 'persistent', label: 'Persistent' },
                      { value: 'all', label: 'All' },
                    ]}
                  />
                </div>
                {weaknesses.length === 0 ? (
                  <p className="small muted" style={{ marginTop: 8 }}>
                    {weaknessFilter === 'persistent'
                      ? 'Nothing has recurred often enough to call a habit yet. A pattern needs several takes and sessions of evidence.'
                      : 'No recurring differences found.'}
                  </p>
                ) : (
                  <ul className="weakness-list">
                    {weaknesses.slice(0, 12).map((w) => (
                      <li key={w.key} className="weakness">
                        <div className="row">
                          <CategoryChip category={w.category} />
                          <strong className="grow">{w.title}</strong>
                          <Badge tone={w.persistent ? 'bad' : 'neutral'}>{w.label}</Badge>
                        </div>
                        <p className="small muted">{w.summary}</p>
                        <div className="weakness-evidence tiny faint">
                          <span>
                            {w.occurrences} occurrence{w.occurrences === 1 ? '' : 's'}
                          </span>
                          <span>
                            {w.takes} take{w.takes === 1 ? '' : 's'}
                          </span>
                          <span>
                            {w.sessions} session{w.sessions === 1 ? '' : 's'}
                          </span>
                          <span>median size {formatNumber(w.median_magnitude, 1)}× tolerance</span>
                          <span
                            className={
                              w.trend === 'improving'
                                ? 'good-text'
                                : w.trend === 'worsening'
                                  ? 'bad-text'
                                  : undefined
                            }
                          >
                            trend {w.trend}
                          </span>
                          <ConfidenceBadge value={w.confidence} compact />
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
              <section className="card card-pad">
                <h3>Consistently good</h3>
                {p.strengths.length === 0 ? (
                  <p className="small muted">Strengths appear after a few takes.</p>
                ) : (
                  <ul className="plain-list">
                    {p.strengths.slice(0, 10).map((s) => (
                      <li key={s.metric_id} className="row">
                        <Icon name="check" size={13} className="good-text" />
                        <span className="grow">{s.text}</span>
                        <span className="num small faint">{formatScore(s.median_score)}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {mode !== 'coach' && p.personal_bests.length ? (
                  <>
                    <h4 style={{ marginTop: 16 }}>Personal bests by measure</h4>
                    <div className="pb-grid">
                      {p.personal_bests.slice(0, 16).map((pb) => (
                        <button
                          key={pb.metric_id}
                          type="button"
                          className="pb-item"
                          onClick={() =>
                            navigate({
                              name: 'project',
                              projectId: data.projectId,
                              tab: 'compare',
                              take: pb.take_id,
                            })
                          }
                        >
                          <span className="truncate">{pb.name}</span>
                          <span className="num">{formatScore(pb.score)}</span>
                          <span className="tiny faint">take {pb.take_number ?? '?'}</span>
                        </button>
                      ))}
                    </div>
                  </>
                ) : null}
              </section>
            </div>
            <div className="progress-grid">
              <section className="card card-pad">
                <h3>Phrases</h3>
                <table className="data-table compact">
                  <thead>
                    <tr>
                      <th scope="col">Phrase</th>
                      <th scope="col">History</th>
                      <th scope="col">Latest</th>
                      <th scope="col">Best</th>
                    </tr>
                  </thead>
                  <tbody>
                    {p.phrases.map((phrase) => (
                      <tr key={phrase.label}>
                        <th scope="row" className="truncate" style={{ maxWidth: 220 }}>
                          {phrase.label}
                        </th>
                        <td>
                          <Sparkline values={phrase.history.map((h) => h.score)} />
                        </td>
                        <td className={`num tone-text-${scoreTone(phrase.latest)}`}>
                          {formatScore(phrase.latest)}
                        </td>
                        <td className="num">{formatScore(phrase.best)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
              <section className="card card-pad">
                <h3>Practice</h3>
                <Calendar days={p.practice_frequency} />
                <h4 style={{ marginTop: 14 }}>Milestones</h4>
                {p.milestones.length === 0 ? (
                  <p className="small muted">Personal bests and category milestones appear here.</p>
                ) : (
                  <ul className="milestones">
                    {p.milestones.slice(0, 10).map((m) => (
                      <li key={m.id}>
                        <Icon
                          name={m.kind === 'personal_best' ? 'star-filled' : 'flag'}
                          size={13}
                          className="ref-text"
                        />
                        <span className="grow">{m.title}</span>
                        <span className="tiny faint">{relativeTime(m.created_at)}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <h4 style={{ marginTop: 14 }}>Sessions</h4>
                <ul className="plain-list">
                  {p.sessions.slice(0, 6).map((s) => (
                    <li key={s.id} className="row small">
                      <span className="grow">{formatDate(s.started_at)}</span>
                      <span className="faint">
                        {s.takes} take{s.takes === 1 ? '' : 's'} · {formatDuration(s.active_seconds)}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
            <section className="card card-pad">
              <div className="row-wrap" style={{ justifyContent: 'space-between' }}>
                <h3>All takes</h3>
                <div style={{ width: 260 }}>
                  <TextField
                    icon="search"
                    placeholder="Search takes, notes or focus"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    aria-label="Search takes"
                  />
                </div>
              </div>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Take</th>
                      <th scope="col">Date</th>
                      <th scope="col">Overall</th>
                      {CATEGORY_ORDER.map((c) => (
                        <th key={c} scope="col">
                          {categoryLabel(c).slice(0, 5)}
                        </th>
                      ))}
                      <th scope="col">Main focus</th>
                      <th scope="col">Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...filteredTakes].reverse().map((t) => (
                      <tr key={t.take_id}>
                        <th scope="row">
                          <button
                            type="button"
                            className="link-button"
                            onClick={() =>
                              navigate({
                                name: 'project',
                                projectId: data.projectId,
                                tab: 'compare',
                                take: t.take_id,
                              })
                            }
                          >
                            {t.take_name}
                          </button>{' '}
                          {p.best_take?.take_id === t.take_id ? <Badge tone="accent">best</Badge> : null}
                        </th>
                        <td className="faint">{formatDate(t.created_at)}</td>
                        <td className={`num score-cell tone-${scoreTone(t.overall)}`}>
                          {formatScore(t.overall)}
                        </td>
                        {CATEGORY_ORDER.map((c) => (
                          <td key={c} className={`num score-cell tone-${scoreTone(t.categories[c] ?? null)}`}>
                            {formatScore(t.categories[c] ?? null)}
                          </td>
                        ))}
                        <td className="truncate" style={{ maxWidth: 200 }}>
                          {t.primary_focus ?? '–'}
                        </td>
                        <td style={{ minWidth: 140 }}>
                          <TakeNotes take={t} projectId={data.projectId} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  )
}
