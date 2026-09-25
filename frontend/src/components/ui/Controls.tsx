import { useId, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from 'react'
import { Icon } from './Icon'

export interface SegmentOption<T extends string> {
  value: T
  label: ReactNode
  icon?: string
  title?: string
  disabled?: boolean
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  size = 'md',
  ariaLabel,
}: {
  value: T
  options: SegmentOption<T>[]
  onChange: (value: T) => void
  size?: 'sm' | 'md'
  ariaLabel: string
}) {
  const index = Math.max(
    0,
    options.findIndex((o) => o.value === value),
  )
  return (
    <div
      className={`segmented segmented-${size}`}
      role="radiogroup"
      aria-label={ariaLabel}
      style={{ ['--seg-count' as string]: options.length, ['--seg-index' as string]: index }}
    >
      <span className="segmented-thumb" aria-hidden />
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={option.value === value}
          className={option.value === value ? 'is-active' : undefined}
          disabled={option.disabled}
          title={option.title}
          onClick={() => onChange(option.value)}
        >
          {option.icon ? <Icon name={option.icon} size={13} /> : null}
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function Switch({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  label?: ReactNode
  description?: ReactNode
  disabled?: boolean
}) {
  const id = useId()
  return (
    <label className={`switch-row${disabled ? ' is-disabled' : ''}`} htmlFor={id}>
      <span className="switch">
        <input
          id={id}
          type="checkbox"
          role="switch"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span className="switch-track" aria-hidden>
          <span className="switch-thumb" />
        </span>
      </span>
      {label || description ? (
        <span className="switch-text">
          {label ? <span className="switch-label">{label}</span> : null}
          {description ? <span className="switch-description">{description}</span> : null}
        </span>
      ) : null}
    </label>
  )
}

export function Slider({
  value,
  min,
  max,
  step = 0.01,
  onChange,
  label,
  format,
  disabled,
  ariaLabel,
}: {
  value: number
  min: number
  max: number
  step?: number
  onChange: (value: number) => void
  label?: ReactNode
  format?: (value: number) => string
  disabled?: boolean
  ariaLabel?: string
}) {
  const id = useId()
  const fraction = max > min ? (value - min) / (max - min) : 0
  return (
    <div className="slider-field">
      {label ? (
        <label className="field-label row" htmlFor={id}>
          <span className="grow">{label}</span>
          <span className="num faint">{format ? format(value) : value}</span>
        </label>
      ) : null}
      <input
        id={id}
        className="slider"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        aria-label={ariaLabel}
        style={{ ['--fill' as string]: `${Math.max(0, Math.min(1, fraction)) * 100}%` }}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </div>
  )
}

export function Select({
  value,
  options,
  onChange,
  label,
  ariaLabel,
  disabled,
}: {
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
  label?: ReactNode
  ariaLabel?: string
  disabled?: boolean
}) {
  const id = useId()
  return (
    <div className="field">
      {label ? (
        <label className="field-label" htmlFor={id}>
          {label}
        </label>
      ) : null}
      <div className="select-wrap">
        <select
          id={id}
          className="select"
          value={value}
          aria-label={ariaLabel}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <Icon name="chevron-down" size={14} className="select-caret" />
      </div>
    </div>
  )
}

export function TextField({
  label,
  hint,
  error,
  icon,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & {
  label?: ReactNode
  hint?: ReactNode
  error?: ReactNode
  icon?: string
}) {
  const id = useId()
  return (
    <div className="field">
      {label ? (
        <label className="field-label" htmlFor={rest.id ?? id}>
          {label}
        </label>
      ) : null}
      <div className={`input-wrap${icon ? ' has-icon' : ''}${error ? ' has-error' : ''}`}>
        {icon ? <Icon name={icon} size={14} className="input-icon" /> : null}
        <input id={id} className="input" {...rest} />
      </div>
      {error ? (
        <span className="field-error">{error}</span>
      ) : hint ? (
        <span className="field-hint">{hint}</span>
      ) : null}
    </div>
  )
}

export function TextArea({
  label,
  hint,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: ReactNode; hint?: ReactNode }) {
  const id = useId()
  return (
    <div className="field">
      {label ? (
        <label className="field-label" htmlFor={rest.id ?? id}>
          {label}
        </label>
      ) : null}
      <textarea id={id} className="input textarea" {...rest} />
      {hint ? <span className="field-hint">{hint}</span> : null}
    </div>
  )
}

export function Checkbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  label: ReactNode
}) {
  return (
    <label className="checkbox">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span className="checkbox-box" aria-hidden>
        <Icon name="check" size={11} />
      </span>
      <span>{label}</span>
    </label>
  )
}
