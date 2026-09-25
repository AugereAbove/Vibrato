import { useState } from 'react'
import type { Comparison, Recording } from '../../../api/types'
import { Badge, CategoryChip } from '../../../components/ui/Badge'
import { Button } from '../../../components/ui/Button'
import { Callout, EmptyState } from '../../../components/ui/Feedback'
import { Icon } from '../../../components/ui/Icon'
import { ScoreRing } from '../../../components/ui/Motion'
import { Tooltip } from '../../../components/ui/Tooltip'
import { categoryLabel } from '../../../lib/categories'
import { formatPercent } from '../../../lib/format'
import type { ViewMode } from '../../../state/prefs'
import { setUi, useUi } from '../../../state/ui'
import { useWorkspace } from '../../../state/workspace'
import { applyFocus } from '../actions'
import { FindingCard } from './FindingCard'
import { openWhy } from './whyStore'

export function CoachPanel({
  comparison,
  mode,
  projectId,
  take,
}: {
  comparison: Comparison
  mode: ViewMode
  projectId: string
  take: Recording | null
}) {
  const open = useUi((s) => s.coachOpen)
  const region = useWorkspace((s) => s.region)
  const selection = useWorkspace((s) => s.selection)
  const [showMinor, setShowMinor] = useState(false)
  const [showDontWorry, setShowDontWorry] = useState(false)
  const coaching = comparison.coaching
  const top = [...coaching.primary, ...coaching.secondary].slice(0, 3)
  const overall = comparison.scores.overall
  const isBest =
    comparison.personal_best?.comparison_id === comparison.id &&
    comparison.previous !== null &&
    comparison.previous.overall !== null &&
    overall.score !== null &&
    overall.score > comparison.previous.overall
  const whyTarget = region ?? (selection ? { start: selection.start, end: selection.end } : null)
  return (
    <section className={`coach-panel${open ? '' : ' is-collapsed'}`} aria-label="Coaching summary">
      <header className="coach-header">
        <button
          type="button"
          className="coach-toggle"
          aria-expanded={open}
          onClick={() => setUi({ coachOpen: !open })}
          aria-label={open ? 'Collapse coaching' : 'Expand coaching'}
        >
          <Icon name="chevron-down" size={14} className="chevron" />
        </button>
        <div className="grow coach-heading">
          <h3>Your biggest differences in this take</h3>
          {open ? <p className="coach-summary">{coaching.summary}</p> : null}
        </div>
        {isBest ? (
          <span className="celebrate" role="status">
            <Icon name="star-filled" size={13} /> Personal best
          </span>
        ) : null}
        <Tooltip
          content={
            <div className="stack" style={{ gap: 4, maxWidth: 260 }}>
              <strong>
                Overall {overall.score?.toFixed(0) ?? '–'} · confidence {formatPercent(overall.confidence)}
              </strong>
              <span className="muted">{overall.disclaimer}</span>
            </div>
          }
        >
          <span>
            <ScoreRing
              score={overall.score}
              confidence={overall.confidence}
              size={40}
              label="Overall convenience score"
              previous={comparison.previous?.overall}
            />
          </span>
        </Tooltip>
        <Button
          variant="ghost"
          icon="bulb"
          disabled={!whyTarget}
          title={whyTarget ? 'Explain the selected region' : 'Select a region on the timeline first'}
          onClick={() => whyTarget && openWhy(whyTarget)}
        >
          Why does it sound different?
        </Button>
        <Button
          variant="primary"
          icon="target"
          disabled={!coaching.next_focus}
          onClick={() => coaching.next_focus && applyFocus(coaching.next_focus, mode)}
        >
          What should I fix next?
        </Button>
      </header>
      {open ? (
        <div className="coach-body">
          {comparison.warnings.length ? (
            <Callout tone="warn" title="Read these results with care">
              {comparison.warnings.join(' ')}
            </Callout>
          ) : null}
          {top.length === 0 ? (
            <EmptyState compact icon="check" title="No reliable differences stand out">
              Every measured category is within its tolerance, or the remaining differences are too uncertain
              to call. Try a harder passage, or look at the raw measurements.
            </EmptyState>
          ) : (
            <div className="finding-grid">
              {top.map((finding, index) => (
                <FindingCard
                  key={finding.key}
                  finding={finding}
                  rank={index + 1}
                  mode={mode}
                  projectId={projectId}
                  take={take}
                  referenceId={comparison.reference_id}
                />
              ))}
            </div>
          )}
          <div className="coach-lower">
            <div className="coach-good">
              <span className="eyebrow">What already matches well</span>
              <div className="row-wrap">
                {coaching.already_good.slice(0, mode === 'coach' ? 5 : 10).map((item) => (
                  <Tooltip key={item.metric_id} content={item.text}>
                    <span className="good-chip">
                      <Icon name="check" size={12} />
                      {item.name}
                    </span>
                  </Tooltip>
                ))}
                {coaching.already_good.length === 0 ? (
                  <span className="faint small">Nothing confirmed yet.</span>
                ) : null}
              </div>
            </div>
            {coaching.dont_worry.length ? (
              <div className="coach-dontworry">
                <button
                  type="button"
                  className="link-button"
                  onClick={() => setShowDontWorry((v) => !v)}
                  aria-expanded={showDontWorry}
                >
                  <Icon name={showDontWorry ? 'chevron-down' : 'chevron-right'} size={12} />
                  Don’t spend time on these yet ({coaching.dont_worry.length})
                </button>
                {showDontWorry ? (
                  <ul className="plain-list">
                    {coaching.dont_worry.map((item) => (
                      <li key={item.key}>
                        <CategoryChip category={item.category} /> <strong>{item.title}</strong>{' '}
                        <span className="muted">— {item.reason}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
            {coaching.minor.length ? (
              <div className="coach-minor">
                <button
                  type="button"
                  className="link-button"
                  onClick={() => setShowMinor((v) => !v)}
                  aria-expanded={showMinor}
                >
                  <Icon name={showMinor ? 'chevron-down' : 'chevron-right'} size={12} />
                  Also noticed ({coaching.minor.length})
                </button>
                {showMinor ? (
                  <div className="finding-grid is-compact">
                    {coaching.minor.map((finding) => (
                      <FindingCard
                        key={finding.key}
                        finding={finding}
                        mode={mode}
                        projectId={projectId}
                        take={take}
                        referenceId={comparison.reference_id}
                        compact
                      />
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
            {coaching.uncertain.length ? (
              <div className="coach-uncertain">
                <span className="eyebrow">Insufficient confidence</span>
                <p className="small muted">
                  {coaching.uncertain.map((f) => `${f.title} (${categoryLabel(f.category)})`).join(', ')} —
                  differences may exist here, but the measurements are not reliable enough to interpret.
                </p>
              </div>
            ) : null}
            {mode !== 'coach' ? (
              <div className="coach-meta faint tiny">
                <Badge>{coaching.version}</Badge> {coaching.findings.length} findings ranked from{' '}
                {comparison.metrics.length} measurements · alignment confidence{' '}
                {formatPercent(comparison.alignment.overall_confidence)}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  )
}
