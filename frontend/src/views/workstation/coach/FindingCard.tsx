import { useState } from 'react'
import { projectsApi } from '../../../api/endpoints'
import type { Finding, Recording } from '../../../api/types'
import { engine } from '../../../audio/engine'
import { fitRange } from '../../../components/timeline/viewport'
import { Badge, BasisTag, ConfidenceBadge } from '../../../components/ui/Badge'
import { Button } from '../../../components/ui/Button'
import { Icon } from '../../../components/ui/Icon'
import { MenuButton } from '../../../components/ui/Menu'
import { Tooltip } from '../../../components/ui/Tooltip'
import { CATEGORY_ICONS, categoryLabel } from '../../../lib/categories'
import { formatNumber } from '../../../lib/format'
import { keys } from '../../../state/data'
import { attempt } from '../../../state/errors'
import type { ViewMode } from '../../../state/prefs'
import { invalidate } from '../../../state/resource'
import { pushToast } from '../../../state/toasts'
import { useWorkspace } from '../../../state/workspace'
import { compareTake, loopRegion } from '../actions'
import { showFinding } from './focus'

export function RankingDetails({ finding }: { finding: Finding }) {
  const r = finding.ranking
  const rows: [string, string, string][] = [
    ['Size of difference', formatNumber(r.magnitude_term, 2), r.magnitude_basis],
    ['Confidence', formatNumber(r.confidence, 2), 'How reliable the measurements are'],
    ['Perceptual importance', formatNumber(r.perceptual_importance, 2), 'How strongly listeners notice this'],
    [
      'Persistence',
      `×${formatNumber(r.persistence_multiplier, 2)}`,
      `Seen in ${finding.history_takes} earlier takes`,
    ],
    ['Trainability', `×${formatNumber(r.trainability_factor, 2)}`, 'How directly practice changes it'],
    [
      'Systematic',
      `×${formatNumber(r.systematic_bonus, 2)}`,
      finding.systematic ? 'Happens throughout the take' : 'Localised',
    ],
    ['Your adjustment', `×${formatNumber(r.user_override, 2)}`, r.user_action ?? 'None'],
  ]
  return (
    <div className="ranking">
      <table className="ranking-table">
        <tbody>
          {rows.map(([label, value, note]) => (
            <tr key={label}>
              <th>{label}</th>
              <td className="num">{value}</td>
              <td className="faint">{note}</td>
            </tr>
          ))}
          <tr className="ranking-total">
            <th>Priority</th>
            <td className="num">{formatNumber(finding.priority, 3)}</td>
            <td className="faint">Product of the factors above</td>
          </tr>
        </tbody>
      </table>
      <p className="faint tiny" style={{ marginTop: 6 }}>
        {r.formula}. The weighting is a transparent heuristic, not a validated perceptual model.
      </p>
    </div>
  )
}

export function EvidenceList({ finding }: { finding: Finding }) {
  return (
    <div className="evidence">
      <div className="evidence-row evidence-head">
        <span>Where</span>
        <span className="ref-text">Reference</span>
        <span className="take-text">Take</span>
        <span>Difference</span>
        <span>Conf.</span>
      </div>
      {finding.evidence.map((item, index) => (
        <button
          key={`${item.segment_id}-${index}`}
          type="button"
          className="evidence-row"
          onClick={() => {
            useWorkspace.setState({ region: { start: item.ref_start, end: item.ref_end } })
            fitRange(item.ref_start, item.ref_end, 0.6)
            engine.seek(item.ref_start)
          }}
        >
          <span className="truncate">{item.label}</span>
          <span className="num">{item.reference}</span>
          <span className="num">{item.take}</span>
          <span className="num">
            {item.difference} <BasisTag basis={item.basis} />
          </span>
          <span className="num faint">{Math.round(item.confidence * 100)}%</span>
        </button>
      ))}
    </div>
  )
}

export function FindingCard({
  finding,
  rank,
  mode,
  projectId,
  take,
  referenceId,
  compact = false,
}: {
  finding: Finding
  rank?: number
  mode: ViewMode
  projectId: string
  take: Recording | null
  referenceId: string | null
  compact?: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const [showRanking, setShowRanking] = useState(false)
  const focusKey = useWorkspace((s) => s.focusKey)
  const practice = finding.practice
  const text = mode === 'coach' ? finding.texts.beginner : finding.texts.expert
  const secondary = mode === 'coach' ? null : finding.texts.beginner
  const override = async (action: 'boost' | 'ignore' | 'dismiss') => {
    const result = await attempt(
      () => projectsApi.addOverride(projectId, finding.key, action),
      'Could not save your preference',
    )
    if (!result) return
    invalidate(keys.overrides(projectId))
    pushToast({
      kind: 'info',
      title:
        action === 'boost'
          ? 'Raised in your priorities'
          : action === 'ignore'
            ? 'Hidden from coaching'
            : 'Marked as not useful',
      body: 'Re-ranking this take with your preference…',
    })
    if (take) await compareTake(projectId, take, referenceId)
  }
  return (
    <article
      className={`finding-card${compact ? ' is-compact' : ''}${focusKey === finding.key ? ' is-focused' : ''}`}
    >
      <header className="finding-header">
        {rank !== undefined ? <span className="finding-rank">{rank}</span> : null}
        <span className="finding-category" style={{ color: `var(--cat-${finding.category})` }}>
          <Icon name={CATEGORY_ICONS[finding.category] ?? 'dot'} size={14} />
        </span>
        <div className="grow">
          <h4 className="finding-title">{finding.title}</h4>
          <div className="finding-meta">
            <span className="faint">{categoryLabel(finding.category)}</span>
            <ConfidenceBadge value={finding.confidence} />
            <Tooltip
              content={`${finding.texts.importance_label}: how strongly listeners usually notice this kind of difference.`}
            >
              <Badge tone={finding.importance >= 0.95 ? 'accent' : 'neutral'}>
                {finding.texts.importance_label.replace(' perceptual', '')}
              </Badge>
            </Tooltip>
            <Tooltip content={finding.texts.pattern}>
              <Badge
                tone={finding.systematic ? 'warn' : 'neutral'}
                icon={finding.systematic ? 'activity' : 'dot'}
              >
                {finding.systematic ? 'Systematic' : 'One-off'}
              </Badge>
            </Tooltip>
            {finding.history_takes > 0 ? (
              <Tooltip
                content={`Also found in ${finding.history_takes} earlier take${finding.history_takes === 1 ? '' : 's'}`}
              >
                <Badge tone="bad" icon="history">
                  Recurring
                </Badge>
              </Tooltip>
            ) : null}
          </div>
        </div>
        <MenuButton
          label="Adjust how this is ranked"
          items={[
            {
              label: 'Prioritise this',
              icon: 'trend-up',
              hint: 'Rank it higher in future',
              onSelect: () => void override('boost'),
            },
            {
              label: 'Not useful for me',
              icon: 'trend-down',
              hint: 'Rank it lower',
              onSelect: () => void override('dismiss'),
            },
            {
              label: 'Never show this',
              icon: 'eye-off',
              hint: 'Hide it from coaching',
              onSelect: () => void override('ignore'),
            },
            'separator',
            {
              label: showRanking ? 'Hide ranking details' : 'Why is it ranked here?',
              icon: 'info',
              onSelect: () => setShowRanking((v) => !v),
            },
          ]}
        />
      </header>
      <p className="finding-text">{text}</p>
      {secondary && !compact ? <p className="finding-subtext">{secondary}</p> : null}
      {!compact ? (
        <div className="finding-advice">
          <div>
            <span className="eyebrow">Try</span>
            <p>
              {finding.texts.adjust} <BasisTag basis={finding.texts.adjust_basis} />
            </p>
          </div>
          {mode !== 'coach' || expanded ? (
            <div>
              <span className="eyebrow">Exercise</span>
              <p>{finding.texts.exercise}</p>
            </div>
          ) : null}
        </div>
      ) : null}
      <footer className="finding-actions">
        {practice ? (
          <>
            <Button size="sm" variant="accent-soft" icon="target" onClick={() => showFinding(finding, mode)}>
              Show me
            </Button>
            <Button
              size="sm"
              variant="ghost"
              icon="loop"
              onClick={() => {
                showFinding(finding, mode)
                loopRegion({ start: practice.ref_start, end: practice.ref_end })
                void engine.play(practice.ref_start)
              }}
            >
              Loop it
            </Button>
            <Button
              size="sm"
              variant="ghost"
              icon="compare"
              onClick={() => {
                showFinding(finding, mode)
                loopRegion({ start: practice.focus_start, end: practice.focus_end })
                engine.setMode('ref')
                engine.setAlternate(true)
                void engine.play(practice.focus_start)
              }}
            >
              Hear A/B
            </Button>
          </>
        ) : null}
        <span className="spacer" />
        {finding.evidence.length ? (
          <Button
            size="sm"
            variant="ghost"
            iconRight={expanded ? 'chevron-up' : 'chevron-down'}
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? 'Less' : `Evidence (${finding.evidence.length})`}
          </Button>
        ) : null}
      </footer>
      {showRanking ? <RankingDetails finding={finding} /> : null}
      {expanded ? <EvidenceList finding={finding} /> : null}
      {finding.corroborating.length && expanded ? (
        <p className="faint tiny">Supported by: {finding.corroborating.map((c) => c.title).join(', ')}</p>
      ) : null}
    </article>
  )
}
