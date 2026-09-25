import { useMemo, useState } from 'react'
import { comparisonsApi } from '../../../api/endpoints'
import type { Comparison, MetricComparison } from '../../../api/types'
import { engine } from '../../../audio/engine'
import { fitRange } from '../../../components/timeline/viewport'
import { Button } from '../../../components/ui/Button'
import { Select, Slider, Switch, TextField } from '../../../components/ui/Controls'
import { EmptyState } from '../../../components/ui/Feedback'
import { Icon } from '../../../components/ui/Icon'
import { magnitude, metricName, metricUnit, type ComparisonIndex } from '../../../lib/analysis'
import { CATEGORY_ORDER, categoryLabel } from '../../../lib/categories'
import { formatPercent, formatTime } from '../../../lib/format'
import {
  formatMetricDifference,
  formatMetricValue,
  severity,
  SEVERITY_LABEL,
} from '../../../lib/metricFormat'
import type { ViewMode } from '../../../state/prefs'
import { setUi, useUi } from '../../../state/ui'
import { select, useWorkspace } from '../../../state/workspace'
import type { CategoryId } from '../../../api/types'

type SortKey = 'time' | 'magnitude' | 'confidence' | 'category' | 'score' | 'name'

const PAGE = 200

export function MeasurementsTable({
  comparison,
  cindex,
  mode,
}: {
  comparison: Comparison
  cindex: ComparisonIndex | null
  mode: ViewMode
}) {
  const filters = useUi((s) => s.tableFilters)
  const selection = useWorkspace((s) => s.selection)
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'magnitude', desc: true })
  const [limit, setLimit] = useState(PAGE)
  const setFilters = (patch: Partial<typeof filters>) => setUi({ tableFilters: { ...filters, ...patch } })
  const rows = useMemo(() => {
    const search = filters.search.trim().toLowerCase()
    const list = comparison.metrics.filter((m) => {
      if (filters.category !== 'all' && m.category !== filters.category) return false
      if (m.confidence < filters.minConfidence) return false
      if (magnitude(m) < filters.minMagnitude) return false
      if (filters.onlyFlagged && (magnitude(m) < 1 || m.confidence < 0.45)) return false
      if (search && !`${m.label} ${metricName(comparison, m)} ${m.direction}`.toLowerCase().includes(search))
        return false
      return true
    })
    const value = (m: MetricComparison): number | string => {
      switch (sort.key) {
        case 'time':
          return m.ref_start
        case 'magnitude':
          return magnitude(m) * (m.confidence >= 0.45 ? 1 : 0.5)
        case 'confidence':
          return m.confidence
        case 'category':
          return `${CATEGORY_ORDER.indexOf(m.category)}`.padStart(2, '0') + m.metric_id
        case 'score':
          return m.score ?? -1
        case 'name':
          return metricName(comparison, m)
      }
    }
    return [...list].sort((a, b) => {
      const va = value(a)
      const vb = value(b)
      const order =
        typeof va === 'number' && typeof vb === 'number' ? va - vb : String(va).localeCompare(String(vb))
      return sort.desc ? -order : order
    })
  }, [comparison, filters, sort])

  const header = (key: SortKey, label: string) => (
    <th scope="col" aria-sort={sort.key === key ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
      <button
        type="button"
        className="sort-button"
        onClick={() =>
          setSort((s) => ({ key, desc: s.key === key ? !s.desc : key !== 'time' && key !== 'name' }))
        }
      >
        {label}
        {sort.key === key ? <Icon name={sort.desc ? 'chevron-down' : 'chevron-up'} size={11} /> : null}
      </button>
    </th>
  )

  const open = (metric: MetricComparison) => {
    if (metric.ref_segment_id) {
      select({
        kind: 'segment',
        level: (metric.level === 'event' ? 'phoneme' : metric.level) as 'note',
        refId: metric.ref_segment_id,
        takeId: metric.user_segment_id ?? cindex?.refToUser.get(metric.ref_segment_id) ?? null,
        start: metric.ref_start,
        end: metric.ref_end,
        label: metric.label,
      })
    }
    useWorkspace.setState({ region: { start: metric.ref_start, end: metric.ref_end } })
    fitRange(metric.ref_start, metric.ref_end, 0.8)
    engine.seek(metric.ref_start)
  }

  return (
    <div className="measurements">
      <div className="panel-toolbar wrap">
        <div style={{ width: 170 }}>
          <Select
            ariaLabel="Category"
            value={filters.category}
            onChange={(value) => setFilters({ category: value as CategoryId | 'all' })}
            options={[
              { value: 'all', label: 'All categories' },
              ...CATEGORY_ORDER.map((c) => ({ value: c, label: categoryLabel(c) })),
            ]}
          />
        </div>
        <div style={{ width: 200 }}>
          <TextField
            icon="search"
            placeholder="Filter by word, note or metric"
            value={filters.search}
            onChange={(e) => setFilters({ search: e.target.value })}
            aria-label="Filter measurements"
          />
        </div>
        <div style={{ width: 150 }}>
          <Slider
            label="Min. confidence"
            value={filters.minConfidence}
            min={0}
            max={1}
            step={0.05}
            format={(v) => formatPercent(v)}
            onChange={(v) => setFilters({ minConfidence: v })}
          />
        </div>
        <div style={{ width: 150 }}>
          <Slider
            label="Min. difference"
            value={filters.minMagnitude}
            min={0}
            max={4}
            step={0.25}
            format={(v) => `${v.toFixed(2)}×tol`}
            onChange={(v) => setFilters({ minMagnitude: v })}
          />
        </div>
        <Switch
          checked={filters.onlyFlagged}
          onChange={(v) => setFilters({ onlyFlagged: v })}
          label="Only notable"
        />
        <span className="spacer" />
        <span className="faint small num">
          {rows.length} of {comparison.metrics.length}
        </span>
        <a className="btn btn-ghost btn-sm" href={comparisonsApi.csvUrl(comparison.id)} download>
          <Icon name="download" size={14} /> CSV
        </a>
        {mode !== 'coach' ? (
          <a className="btn btn-ghost btn-sm" href={comparisonsApi.jsonUrl(comparison.id)} download>
            <Icon name="download" size={14} /> JSON
          </a>
        ) : null}
      </div>
      {rows.length === 0 ? (
        <EmptyState compact icon="search" title="No measurements match these filters" />
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                {header('time', 'Time')}
                {header('category', 'Category')}
                {header('name', 'Measure')}
                <th scope="col">Where</th>
                <th scope="col" className="ref-text">
                  Reference
                </th>
                <th scope="col" className="take-text">
                  You
                </th>
                {header('magnitude', 'Difference')}
                {header('confidence', 'Confidence')}
                {mode !== 'coach' ? header('score', 'Score') : null}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, limit).map((metric) => {
                const unit = metricUnit(comparison, metric)
                const level = severity(metric)
                const active = selection?.kind === 'segment' && selection.refId === metric.ref_segment_id
                return (
                  <tr
                    key={`${metric.metric_id}:${metric.ref_segment_id}:${metric.ref_start}`}
                    className={`sev-${level}${active ? ' is-active' : ''}`}
                    onClick={() => open(metric)}
                    tabIndex={0}
                    onKeyDown={(event) => event.key === 'Enter' && open(metric)}
                  >
                    <td className="num faint">{formatTime(metric.ref_start)}</td>
                    <td>
                      <span className="cat-dot" style={{ background: `var(--cat-${metric.category})` }} />{' '}
                      {categoryLabel(metric.category)}
                    </td>
                    <td>{metricName(comparison, metric)}</td>
                    <td className="truncate" style={{ maxWidth: 160 }}>
                      {metric.label}
                    </td>
                    <td className="num">{formatMetricValue(metric, 'ref', unit)}</td>
                    <td className="num">{formatMetricValue(metric, 'user', unit)}</td>
                    <td className="num">
                      <span className={`sev-dot sev-dot-${level}`} aria-hidden />
                      {level === 'uncertain' ? (
                        <span className="faint">{SEVERITY_LABEL.uncertain}</span>
                      ) : (
                        formatMetricDifference(metric, unit)
                      )}
                      {level !== 'uncertain' && level !== 'close' ? (
                        <span className="faint"> · {metric.direction}</span>
                      ) : null}
                    </td>
                    <td className="num">{formatPercent(metric.confidence)}</td>
                    {mode !== 'coach' ? (
                      <td className="num">{metric.score == null ? '–' : metric.score.toFixed(0)}</td>
                    ) : null}
                  </tr>
                )
              })}
            </tbody>
          </table>
          {rows.length > limit ? (
            <div className="table-more">
              <Button size="sm" variant="ghost" onClick={() => setLimit((l) => l + PAGE)}>
                Show {Math.min(PAGE, rows.length - limit)} more
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
