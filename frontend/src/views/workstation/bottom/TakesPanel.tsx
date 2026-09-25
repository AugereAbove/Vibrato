import { useMemo, useState } from 'react'
import type { Recording } from '../../../api/types'
import { Badge } from '../../../components/ui/Badge'
import { Button } from '../../../components/ui/Button'
import { Select } from '../../../components/ui/Controls'
import { EmptyState, SkeletonLines } from '../../../components/ui/Feedback'
import { Icon } from '../../../components/ui/Icon'
import { scoreTone } from '../../../lib/score'
import { CATEGORY_ORDER, categoryLabel } from '../../../lib/categories'
import { formatDate, formatScore } from '../../../lib/format'
import { useProgress } from '../../../state/data'
import { navigate } from '../../../state/router'

export function TakesPanel({
  projectId,
  referenceId,
  currentTake,
}: {
  projectId: string
  referenceId: string | null
  takes: Recording[]
  currentTake: Recording | null
}) {
  const progress = useProgress(projectId, referenceId)
  const history = useMemo(() => progress.data?.takes ?? [], [progress.data])
  const currentIndex = history.findIndex((t) => t.take_id === currentTake?.id)
  const [a, setA] = useState<string | null>(null)
  const [b, setB] = useState<string | null>(null)
  if (progress.loading) return <SkeletonLines lines={4} />
  if (history.length === 0) {
    return (
      <EmptyState compact icon="history" title="No compared takes yet">
        Record or import a take against this reference to build a history.
      </EmptyState>
    )
  }
  const defaultA = currentIndex > 0 ? history[currentIndex - 1].take_id : history[0].take_id
  const defaultB = currentTake?.id ?? history[history.length - 1].take_id
  const takeA = history.find((t) => t.take_id === (a ?? defaultA)) ?? history[0]
  const takeB = history.find((t) => t.take_id === (b ?? defaultB)) ?? history[history.length - 1]
  const best = progress.data?.best_take
  const options = history.map((t) => ({
    value: t.take_id,
    label: `${t.take_name}${t.overall != null ? ` · ${t.overall.toFixed(0)}` : ''}`,
  }))
  return (
    <div className="takes-panel">
      <div className="takes-compare card">
        <div className="panel-toolbar">
          <div style={{ width: 180 }}>
            <Select ariaLabel="First take" value={takeA.take_id} options={options} onChange={setA} />
          </div>
          <Icon name="compare" size={16} />
          <div style={{ width: 180 }}>
            <Select ariaLabel="Second take" value={takeB.take_id} options={options} onChange={setB} />
          </div>
          <span className="spacer" />
          {best ? (
            <Button size="sm" variant="ghost" icon="star" onClick={() => setA(best.take_id)}>
              Compare with personal best
            </Button>
          ) : null}
        </div>
        <table className="data-table compact">
          <thead>
            <tr>
              <th scope="col">Category</th>
              <th scope="col">{takeA.take_name}</th>
              <th scope="col">{takeB.take_name}</th>
              <th scope="col">Change</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['overall', 'Overall'] as const,
              ...CATEGORY_ORDER.map((c) => [c, categoryLabel(c)] as const),
            ].map(([key, label]) => {
              const va = key === 'overall' ? takeA.overall : (takeA.categories[key] ?? null)
              const vb = key === 'overall' ? takeB.overall : (takeB.categories[key] ?? null)
              const delta = va != null && vb != null ? vb - va : null
              return (
                <tr key={key}>
                  <th scope="row">{label}</th>
                  <td className="num">{formatScore(va)}</td>
                  <td className="num">{formatScore(vb)}</td>
                  <td
                    className={`num ${delta == null ? '' : delta >= 1 ? 'good-text' : delta <= -1 ? 'bad-text' : 'faint'}`}
                  >
                    {delta == null ? '–' : `${delta >= 0 ? '+' : '−'}${Math.abs(delta).toFixed(1)}`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="takes-matrix">
        <table className="data-table compact">
          <thead>
            <tr>
              <th scope="col">Take</th>
              <th scope="col">When</th>
              <th scope="col">Overall</th>
              {CATEGORY_ORDER.map((c) => (
                <th key={c} scope="col" title={categoryLabel(c)}>
                  {categoryLabel(c).slice(0, 5)}
                </th>
              ))}
              <th scope="col">Main focus</th>
            </tr>
          </thead>
          <tbody>
            {[...history].reverse().map((t) => (
              <tr
                key={t.take_id}
                className={t.take_id === currentTake?.id ? 'is-active' : undefined}
                onClick={() => navigate({ name: 'project', projectId, tab: 'compare', take: t.take_id })}
                tabIndex={0}
                onKeyDown={(event) =>
                  event.key === 'Enter' &&
                  navigate({ name: 'project', projectId, tab: 'compare', take: t.take_id })
                }
              >
                <th scope="row">
                  {t.take_name} {best?.take_id === t.take_id ? <Badge tone="accent">best</Badge> : null}
                </th>
                <td className="faint">{formatDate(t.created_at)}</td>
                <td className={`num score-cell tone-${scoreTone(t.overall)}`}>{formatScore(t.overall)}</td>
                {CATEGORY_ORDER.map((c) => {
                  const value = t.categories[c] ?? null
                  return (
                    <td
                      key={c}
                      className={`num score-cell tone-${scoreTone(value)}`}
                      style={{ opacity: (t.category_confidence[c] ?? 1) < 0.5 ? 0.55 : 1 }}
                    >
                      {formatScore(value)}
                    </td>
                  )
                })}
                <td className="truncate" style={{ maxWidth: 220 }}>
                  {t.primary_focus ?? '–'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
