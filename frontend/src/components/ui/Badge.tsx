import type { ReactNode } from 'react'
import type { CategoryId } from '../../api/types'
import { BASIS_HELP, BASIS_LABELS, CATEGORY_ICONS, categoryLabel } from '../../lib/categories'
import { CONFIDENCE_TEXT, confidenceLevel, formatPercent } from '../../lib/format'
import { Icon } from './Icon'
import { Tooltip } from './Tooltip'

export type Tone = 'neutral' | 'good' | 'warn' | 'bad' | 'info' | 'accent' | 'ref' | 'take' | 'synthetic'

export function Badge({
  tone = 'neutral',
  icon,
  children,
  title,
  className,
}: {
  tone?: Tone
  icon?: string
  children: ReactNode
  title?: string
  className?: string
}) {
  return (
    <span className={`badge badge-${tone}${className ? ` ${className}` : ''}`} title={title}>
      {icon ? <Icon name={icon} size={12} /> : null}
      {children}
    </span>
  )
}

const LEVEL_TONE = { high: 'good', medium: 'info', low: 'warn', insufficient: 'bad' } as const
const LEVEL_ICON = { high: 'check', medium: 'info', low: 'alert', insufficient: 'alert' } as const

export function ConfidenceBadge({
  value,
  reasons,
  compact = false,
}: {
  value: number | null | undefined
  reasons?: string[]
  compact?: boolean
}) {
  const level = confidenceLevel(value)
  const text = compact ? formatPercent(value) : CONFIDENCE_TEXT[level]
  return (
    <Tooltip
      content={
        <div className="stack" style={{ gap: 4, maxWidth: 280 }}>
          <strong>
            {CONFIDENCE_TEXT[level]} ({formatPercent(value)})
          </strong>
          {reasons && reasons.length ? (
            <ul className="tooltip-list">
              {reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : (
            <span className="muted">
              Combines tracking reliability, recording quality and how well the two performances are aligned
              here.
            </span>
          )}
        </div>
      }
    >
      <span
        className={`badge badge-${LEVEL_TONE[level]} confidence-badge confidence-${level}`}
        aria-label={`${CONFIDENCE_TEXT[level]}, ${formatPercent(value)}`}
      >
        <Icon name={LEVEL_ICON[level]} size={12} />
        {text}
      </span>
    </Tooltip>
  )
}

export function BasisTag({ basis }: { basis: string }) {
  const label = BASIS_LABELS[basis] ?? basis
  return (
    <Tooltip content={BASIS_HELP[basis] ?? label}>
      <span className={`basis-tag basis-${basis}`}>{label}</span>
    </Tooltip>
  )
}

export function CategoryChip({
  category,
  active,
  onClick,
}: {
  category: string
  active?: boolean
  onClick?: () => void
}) {
  const content = (
    <>
      <span className="cat-dot" style={{ background: `var(--cat-${category})` }} />
      <Icon name={CATEGORY_ICONS[category as CategoryId] ?? 'dot'} size={12} />
      {categoryLabel(category)}
    </>
  )
  if (onClick) {
    return (
      <button
        type="button"
        className={`chip${active ? ' is-active' : ''}`}
        onClick={onClick}
        aria-pressed={active}
      >
        {content}
      </button>
    )
  }
  return <span className="chip">{content}</span>
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd">{children}</kbd>
}
