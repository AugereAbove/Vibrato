import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Button, IconButton } from './Button'
import { useContextMenu } from './contextMenu'
import { Icon } from './Icon'

export interface MenuItem {
  label: string
  icon?: string
  onSelect: () => void
  danger?: boolean
  disabled?: boolean
  shortcut?: string
  checked?: boolean
  hint?: string
}

export type MenuEntry = MenuItem | 'separator' | { heading: string }

function isItem(entry: MenuEntry): entry is MenuItem {
  return typeof entry === 'object' && 'onSelect' in entry
}

function MenuList({
  items,
  x,
  y,
  onClose,
  label,
}: {
  items: MenuEntry[]
  x: number
  y: number
  onClose: () => void
  label: string
}) {
  const list = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const element = list.current
    if (!element) return
    const rect = element.getBoundingClientRect()
    const nx = Math.max(8, Math.min(x, window.innerWidth - rect.width - 8))
    const ny = y + rect.height > window.innerHeight - 8 ? Math.max(8, y - rect.height) : y
    element.style.left = `${nx}px`
    element.style.top = `${ny}px`
  }, [x, y])

  useEffect(() => {
    const element = list.current
    element?.querySelector<HTMLElement>('[role="menuitem"]:not([disabled])')?.focus()
    const onPointer = (event: PointerEvent) => {
      if (element && !element.contains(event.target as Node)) onClose()
    }
    const onKey = (event: KeyboardEvent) => {
      if (!element) return
      const buttons = [...element.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])')]
      const index = buttons.indexOf(document.activeElement as HTMLElement)
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        onClose()
      } else if (event.key === 'ArrowDown') {
        event.preventDefault()
        buttons[(index + 1) % buttons.length]?.focus()
      } else if (event.key === 'ArrowUp') {
        event.preventDefault()
        buttons[(index - 1 + buttons.length) % buttons.length]?.focus()
      } else if (event.key === 'Tab') {
        onClose()
      }
    }
    window.addEventListener('pointerdown', onPointer, true)
    window.addEventListener('keydown', onKey, true)
    window.addEventListener('blur', onClose)
    window.addEventListener('resize', onClose)
    return () => {
      window.removeEventListener('pointerdown', onPointer, true)
      window.removeEventListener('keydown', onKey, true)
      window.removeEventListener('blur', onClose)
      window.removeEventListener('resize', onClose)
    }
  }, [onClose])

  return createPortal(
    <div ref={list} className="menu" role="menu" aria-label={label} style={{ left: x, top: y }}>
      {items.map((entry, index) => {
        if (entry === 'separator') return <div key={index} className="menu-separator" role="separator" />
        if (!isItem(entry)) {
          return (
            <div key={index} className="menu-heading">
              {entry.heading}
            </div>
          )
        }
        return (
          <button
            key={index}
            type="button"
            role="menuitem"
            className={`menu-item${entry.danger ? ' is-danger' : ''}`}
            disabled={entry.disabled}
            onClick={() => {
              onClose()
              entry.onSelect()
            }}
          >
            <span className="menu-icon">
              {entry.checked !== undefined ? (
                entry.checked ? (
                  <Icon name="check" size={14} />
                ) : null
              ) : entry.icon ? (
                <Icon name={entry.icon} size={14} />
              ) : null}
            </span>
            <span className="grow">
              <span className="menu-label">{entry.label}</span>
              {entry.hint ? <span className="menu-hint">{entry.hint}</span> : null}
            </span>
            {entry.shortcut ? <kbd className="kbd">{entry.shortcut}</kbd> : null}
          </button>
        )
      })}
    </div>,
    document.body,
  )
}

export function MenuButton({
  items,
  label,
  icon = 'more',
  text,
  variant = 'ghost',
  size = 'sm',
  align = 'end',
}: {
  items: MenuEntry[] | (() => MenuEntry[])
  label: string
  icon?: string
  text?: ReactNode
  variant?: 'ghost' | 'secondary' | 'subtle'
  size?: 'xs' | 'sm' | 'md'
  align?: 'start' | 'end'
}) {
  const [anchor, setAnchor] = useState<{ x: number; y: number } | null>(null)
  const button = useRef<HTMLButtonElement>(null)
  const open = () => {
    const rect = button.current?.getBoundingClientRect()
    if (!rect) return
    setAnchor({ x: align === 'end' ? rect.right - 220 : rect.left, y: rect.bottom + 4 })
  }
  const close = () => {
    setAnchor(null)
    button.current?.focus()
  }
  const resolved = anchor ? (typeof items === 'function' ? items() : items) : []
  return (
    <>
      {text ? (
        <Button
          ref={button}
          variant={variant}
          size={size}
          icon={icon}
          iconRight="chevron-down"
          aria-haspopup="menu"
          aria-expanded={anchor !== null}
          onClick={() => (anchor ? close() : open())}
        >
          {text}
        </Button>
      ) : (
        <IconButton
          ref={button}
          icon={icon}
          label={label}
          variant={variant}
          size={size}
          aria-haspopup="menu"
          aria-expanded={anchor !== null}
          onClick={() => (anchor ? close() : open())}
        />
      )}
      {anchor ? <MenuList items={resolved} x={anchor.x} y={anchor.y} onClose={close} label={label} /> : null}
    </>
  )
}

export function ContextMenuHost() {
  const menu = useContextMenu((state) => state.menu)
  if (!menu) return null
  return (
    <MenuList
      items={menu.items}
      x={menu.x}
      y={menu.y}
      label={menu.label}
      onClose={() => useContextMenu.setState({ menu: null })}
    />
  )
}
