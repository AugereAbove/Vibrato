import type { CSSProperties, ReactNode } from 'react'
import { describeError } from '../../api/client'
import { Button } from './Button'
import { Icon } from './Icon'

export function Spinner({ size = 16, label }: { size?: number; label?: string }) {
  return (
    <span
      className="spinner"
      style={{ width: size, height: size }}
      role="status"
      aria-label={label ?? 'Loading'}
    />
  )
}

export function ProgressBar({
  value,
  indeterminate,
  tone = 'accent',
  label,
}: {
  value?: number
  indeterminate?: boolean
  tone?: 'accent' | 'good' | 'warn' | 'bad'
  label?: string
}) {
  const clamped = Math.max(0, Math.min(1, value ?? 0))
  return (
    <div
      className={`progress progress-${tone}${indeterminate ? ' is-indeterminate' : ''}`}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : Math.round(clamped * 100)}
    >
      <span className="progress-fill" style={{ transform: `scaleX(${indeterminate ? 1 : clamped})` }} />
    </div>
  )
}

export function Skeleton({
  width,
  height = 12,
  radius,
  style,
}: {
  width?: number | string
  height?: number | string
  radius?: number
  style?: CSSProperties
}) {
  return (
    <span
      className="skeleton"
      style={{ width: width ?? '100%', height, borderRadius: radius, ...style }}
      aria-hidden
    />
  )
}

export function SkeletonLines({ lines = 3 }: { lines?: number }) {
  return (
    <div className="stack" style={{ gap: 8 }} aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} width={`${90 - i * 14}%`} />
      ))}
    </div>
  )
}

export function EmptyState({
  icon = 'info',
  title,
  children,
  actions,
  compact,
}: {
  icon?: string
  title: ReactNode
  children?: ReactNode
  actions?: ReactNode
  compact?: boolean
}) {
  return (
    <div className={`empty-state${compact ? ' is-compact' : ''}`}>
      <span className="empty-icon">
        <Icon name={icon} size={compact ? 18 : 22} />
      </span>
      <div className="empty-title">{title}</div>
      {children ? <div className="empty-body">{children}</div> : null}
      {actions ? <div className="empty-actions">{actions}</div> : null}
    </div>
  )
}

export function ErrorState({
  error,
  onRetry,
  compact,
}: {
  error: unknown
  onRetry?: () => void
  compact?: boolean
}) {
  const { what, why, action } = describeError(error)
  return (
    <div className={`error-state${compact ? ' is-compact' : ''}`} role="alert">
      <Icon name="alert" size={18} />
      <div className="stack" style={{ gap: 4 }}>
        <strong>{what}</strong>
        <span className="muted">{why}</span>
        <span className="faint">{action}</span>
        {onRetry ? (
          <div>
            <Button size="sm" icon="refresh" onClick={onRetry}>
              Retry
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  )
}

export function Callout({
  tone = 'info',
  icon,
  title,
  children,
}: {
  tone?: 'info' | 'warn' | 'bad' | 'good' | 'synthetic'
  icon?: string
  title?: ReactNode
  children?: ReactNode
}) {
  const fallback =
    tone === 'good' ? 'check' : tone === 'info' ? 'info' : tone === 'synthetic' ? 'flask' : 'alert'
  return (
    <div className={`callout callout-${tone}`}>
      <Icon name={icon ?? fallback} size={16} />
      <div className="stack" style={{ gap: 2 }}>
        {title ? <strong>{title}</strong> : null}
        {children ? <div className="callout-body">{children}</div> : null}
      </div>
    </div>
  )
}
