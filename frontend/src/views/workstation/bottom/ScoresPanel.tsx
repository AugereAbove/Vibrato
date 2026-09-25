import { useEffect, useRef, useState } from 'react'
import { comparisonsApi } from '../../../api/endpoints'
import type { CategoryId, Comparison, Scores } from '../../../api/types'
import { Badge, BasisTag, ConfidenceBadge } from '../../../components/ui/Badge'
import { Button } from '../../../components/ui/Button'
import { Slider, Switch } from '../../../components/ui/Controls'
import { Icon } from '../../../components/ui/Icon'
import { AnimatedNumber, ScoreRing } from '../../../components/ui/Motion'
import { CATEGORY_ICONS, CATEGORY_ORDER } from '../../../lib/categories'
import { formatNumber, formatPercent } from '../../../lib/format'
import { reportError } from '../../../state/errors'
import { setPref } from '../../../state/prefs'
import { pushToast } from '../../../state/toasts'

function DeltaBar({
  previous,
  current,
  color,
}: {
  previous: number | null
  current: number | null
  color: string
}) {
  const bar = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    const element = bar.current
    if (!element) return
    element.style.width = `${previous ?? current ?? 0}%`
    const frame = window.requestAnimationFrame(() => {
      element.style.width = `${current ?? 0}%`
    })
    return () => window.cancelAnimationFrame(frame)
  }, [previous, current])
  const improved = previous != null && current != null && current - previous >= 5
  return (
    <span className={`delta-track${improved ? ' pulse-good' : ''}`}>
      {previous != null ? (
        <span
          className="delta-prev"
          style={{ left: `${previous}%` }}
          title={`Previous take: ${previous.toFixed(0)}`}
        />
      ) : null}
      <span ref={bar} className="delta-fill" style={{ background: color }} />
    </span>
  )
}

export function ScoresPanel({ comparison }: { comparison: Comparison }) {
  const original = comparison.scores
  const [enabled, setEnabled] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(CATEGORY_ORDER.map((c) => [c, original.categories[c]?.enabled ?? true])),
  )
  const [weights, setWeights] = useState<Record<string, number>>(() =>
    Object.fromEntries(CATEGORY_ORDER.map((c) => [c, original.categories[c]?.weight ?? 1])),
  )
  const [scores, setScores] = useState<Scores>(original)
  const [open, setOpen] = useState<CategoryId | null>(null)
  const [dirty, setDirty] = useState(false)
  const timer = useRef<number | null>(null)

  const rescore = (nextEnabled: Record<string, boolean>, nextWeights: Record<string, number>) => {
    setDirty(true)
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(async () => {
      try {
        setScores(await comparisonsApi.rescore(comparison.id, nextEnabled, nextWeights))
      } catch (error) {
        reportError(error, 'Could not recalculate scores')
      }
    }, 200)
  }

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current)
    },
    [],
  )

  const previous = comparison.previous?.categories ?? null
  const overall = scores.overall
  return (
    <div className="scores-panel">
      <div className="scores-overall card">
        <ScoreRing
          score={overall.score}
          confidence={overall.confidence}
          size={72}
          previous={comparison.previous?.overall}
          label="Overall convenience score"
        />
        <div className="stack" style={{ gap: 4 }}>
          <div className="row">
            <h4>Overall convenience score</h4>
            <ConfidenceBadge value={overall.confidence} />
          </div>
          <p className="small muted">{overall.disclaimer}</p>
          <p className="tiny faint">{scores.method.overall_score}</p>
          <div className="row">
            {dirty ? (
              <>
                <Button
                  size="sm"
                  variant="secondary"
                  icon="check"
                  onClick={() => {
                    for (const c of CATEGORY_ORDER) {
                      setPref(`scoring.enabled.${c}`, enabled[c])
                      setPref(`scoring.weight.${c}`, weights[c])
                    }
                    setDirty(false)
                    pushToast({
                      kind: 'success',
                      title: 'Scoring preferences saved',
                      body: 'New comparisons use these categories and weights.',
                    })
                  }}
                >
                  Use for future comparisons
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    const e = Object.fromEntries(
                      CATEGORY_ORDER.map((c) => [c, original.categories[c]?.enabled ?? true]),
                    )
                    const w = Object.fromEntries(
                      CATEGORY_ORDER.map((c) => [c, original.categories[c]?.weight ?? 1]),
                    )
                    setEnabled(e)
                    setWeights(w)
                    setScores(original)
                    setDirty(false)
                  }}
                >
                  Reset
                </Button>
              </>
            ) : (
              <span className="tiny faint">
                Switch categories off or change weights to see how the overall score responds.
              </span>
            )}
          </div>
        </div>
      </div>
      <div className="scores-grid">
        {CATEGORY_ORDER.map((category) => {
          const score = scores.categories[category]
          if (!score) return null
          const prev = previous?.[category]?.score ?? null
          const isOpen = open === category
          return (
            <div
              key={category}
              className={`score-card card${enabled[category] ? '' : ' is-disabled'}${isOpen ? ' is-open' : ''}`}
            >
              <div className="score-card-head">
                <span className="score-card-icon" style={{ color: `var(--cat-${category})` }}>
                  <Icon name={CATEGORY_ICONS[category]} size={16} />
                </span>
                <div className="grow">
                  <div className="row">
                    <strong>{score.label}</strong>
                    {score.confidence < 0.5 ? (
                      <Badge tone="warn" icon="alert">
                        low confidence
                      </Badge>
                    ) : null}
                  </div>
                  <div className="row small">
                    <span className="num score-card-value">
                      <AnimatedNumber value={score.score} />
                    </span>
                    {prev != null && score.score != null ? (
                      <span className={`num tiny ${score.score - prev >= 0 ? 'good-text' : 'bad-text'}`}>
                        {score.score - prev >= 0 ? '+' : '−'}
                        {Math.abs(score.score - prev).toFixed(0)} vs previous
                      </span>
                    ) : null}
                  </div>
                </div>
                <Switch
                  checked={enabled[category]}
                  onChange={(value) => {
                    const next = { ...enabled, [category]: value }
                    setEnabled(next)
                    rescore(next, weights)
                  }}
                  label={<span className="sr-only">Include {score.label} in the overall score</span>}
                />
              </div>
              <DeltaBar previous={prev} current={score.score} color={`var(--cat-${category})`} />
              <div className="row small faint" style={{ justifyContent: 'space-between' }}>
                <span>confidence {formatPercent(score.confidence)}</span>
                <span>{score.count} measurements</span>
              </div>
              <Slider
                label="Weight in overall score"
                value={weights[category]}
                min={0}
                max={2}
                step={0.05}
                format={(v) => v.toFixed(2)}
                disabled={!enabled[category]}
                onChange={(value) => {
                  const next = { ...weights, [category]: value }
                  setWeights(next)
                  rescore(enabled, next)
                }}
              />
              <Button
                size="xs"
                variant="ghost"
                iconRight={isOpen ? 'chevron-up' : 'chevron-down'}
                onClick={() => setOpen(isOpen ? null : category)}
              >
                {isOpen ? 'Hide' : 'Show'} contributing measurements
              </Button>
              {isOpen ? (
                <div className="score-metrics">
                  {Object.entries(score.metrics).map(([id, metric]) => (
                    <div key={id} className="score-metric">
                      <div className="row">
                        <strong className="grow">{metric.name}</strong>
                        {metric.evidence_only ? (
                          <Badge>evidence only</Badge>
                        ) : (
                          <span className="num small">{formatNumber(metric.mean_score, 0)}</span>
                        )}
                      </div>
                      <div className="row-wrap tiny faint">
                        <BasisTag basis={metric.basis} />
                        <span>
                          {metric.scored_instances}/{metric.instances} scored
                        </span>
                        <span>
                          tolerance {metric.tolerance} {metric.unit}
                        </span>
                        <span>weight {metric.weight}</span>
                        <span>
                          median Δ {formatNumber(metric.median_difference, 1)} {metric.unit}
                        </span>
                        <span>conf. {formatPercent(metric.mean_confidence)}</span>
                      </div>
                      <p className="tiny muted">{metric.normalisation}</p>
                    </div>
                  ))}
                  <p className="tiny faint">{scores.method.category_score}</p>
                  <p className="tiny faint">{scores.method.metric_score}</p>
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}
