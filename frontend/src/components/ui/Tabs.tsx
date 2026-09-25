import { useLayoutEffect, useRef } from 'react'
import { Icon } from './Icon'

export interface TabItem<T extends string> {
  id: T
  label: string
  icon?: string
  count?: number | string
  hidden?: boolean
}

export function Tabs<T extends string>({
  items,
  value,
  onChange,
  ariaLabel,
  size = 'md',
}: {
  items: TabItem<T>[]
  value: T
  onChange: (id: T) => void
  ariaLabel: string
  size?: 'sm' | 'md'
}) {
  const container = useRef<HTMLDivElement>(null)
  const indicator = useRef<HTMLSpanElement>(null)
  const visible = items.filter((item) => !item.hidden)

  useLayoutEffect(() => {
    const element = container.current?.querySelector<HTMLElement>(`[data-tab="${value}"]`)
    const bar = indicator.current
    if (!element || !bar) return
    bar.style.transform = `translateX(${element.offsetLeft}px)`
    bar.style.width = `${element.offsetWidth}px`
  })

  const onKeyDown = (event: React.KeyboardEvent) => {
    const index = visible.findIndex((item) => item.id === value)
    if (event.key === 'ArrowRight') {
      event.preventDefault()
      onChange(visible[(index + 1) % visible.length].id)
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault()
      onChange(visible[(index - 1 + visible.length) % visible.length].id)
    }
  }

  return (
    <div
      ref={container}
      className={`tabs tabs-${size}`}
      role="tablist"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
    >
      {visible.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          data-tab={item.id}
          aria-selected={item.id === value}
          tabIndex={item.id === value ? 0 : -1}
          className={item.id === value ? 'tab is-active' : 'tab'}
          onClick={() => onChange(item.id)}
        >
          {item.icon ? <Icon name={item.icon} size={14} /> : null}
          {item.label}
          {item.count !== undefined ? <span className="tab-count">{item.count}</span> : null}
        </button>
      ))}
      <span ref={indicator} className="tab-indicator" />
    </div>
  )
}
