import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Icon } from './Icon'
import { Tooltip } from './Tooltip'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'subtle' | 'accent-soft'
type Size = 'xs' | 'sm' | 'md' | 'lg'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  icon?: string
  iconRight?: string
  loading?: boolean
  active?: boolean
  children?: ReactNode
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'secondary',
    size = 'md',
    icon,
    iconRight,
    loading,
    active,
    className,
    children,
    disabled,
    type,
    ...rest
  },
  ref,
) {
  const classes = ['btn', `btn-${variant}`, `btn-${size}`]
  if (active) classes.push('is-active')
  if (loading) classes.push('is-loading')
  if (!children) classes.push('btn-icon-only')
  if (className) classes.push(className)
  const iconSize = size === 'lg' ? 18 : size === 'xs' ? 13 : 15
  return (
    <button
      ref={ref}
      type={type ?? 'button'}
      className={classes.join(' ')}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? (
        <span className="spinner spinner-inline" aria-hidden />
      ) : icon ? (
        <Icon name={icon} size={iconSize} />
      ) : null}
      {children ? <span className="btn-label">{children}</span> : null}
      {iconRight ? <Icon name={iconRight} size={iconSize} /> : null}
    </button>
  )
})

export interface IconButtonProps extends Omit<ButtonProps, 'children' | 'icon'> {
  icon: string
  label: string
  shortcut?: string
  tooltipSide?: 'top' | 'bottom' | 'left' | 'right'
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { icon, label, shortcut, tooltipSide = 'bottom', variant = 'ghost', size = 'sm', ...rest },
  ref,
) {
  return (
    <Tooltip
      side={tooltipSide}
      content={
        <span className="row" style={{ gap: 8 }}>
          {label}
          {shortcut ? <kbd className="kbd">{shortcut}</kbd> : null}
        </span>
      }
    >
      <Button ref={ref} variant={variant} size={size} icon={icon} aria-label={label} {...rest} />
    </Tooltip>
  )
})
