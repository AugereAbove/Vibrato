import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { setUi, useUi } from '../../state/ui'
import { Icon } from '../ui/Icon'
import { allCommands, score, useCommands } from './commands'

export function CommandPalette() {
  const open = useUi((s) => s.paletteOpen)
  const sources = useCommands((s) => s.sources)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const list = useRef<HTMLDivElement>(null)
  const commands = useMemo(() => allCommands({ sources }), [sources])
  const results = useMemo(
    () =>
      commands
        .map((command) => ({ command, rank: score(command, query) }))
        .filter((r) => r.rank > 0)
        .sort((a, b) => b.rank - a.rank)
        .map((r) => r.command)
        .slice(0, 40),
    [commands, query],
  )
  useEffect(() => {
    if (!open) return
    const frame = window.requestAnimationFrame(() => {
      setQuery('')
      setActive(0)
      input.current?.focus()
    })
    return () => window.cancelAnimationFrame(frame)
  }, [open])
  useEffect(() => {
    list.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [active])
  if (!open) return null
  const headers = results.map((command, index) =>
    !query && (index === 0 || results[index - 1].group !== command.group) ? command.group : null,
  )
  const close = () => setUi({ paletteOpen: false })
  const run = (index: number) => {
    const command = results[index]
    if (!command || command.disabled) return
    close()
    window.setTimeout(() => command.run(), 0)
  }
  return createPortal(
    <div className="palette-layer" onPointerDown={(event) => event.target === event.currentTarget && close()}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette">
        <div className="palette-input">
          <Icon name="search" size={16} />
          <input
            ref={input}
            value={query}
            placeholder="Type a command or search…"
            aria-label="Command"
            aria-controls="palette-list"
            aria-activedescendant={results[active] ? `cmd-${results[active].id}` : undefined}
            onChange={(event) => {
              setQuery(event.target.value)
              setActive(0)
            }}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                event.preventDefault()
                close()
              } else if (event.key === 'ArrowDown') {
                event.preventDefault()
                setActive((i) => Math.min(results.length - 1, i + 1))
              } else if (event.key === 'ArrowUp') {
                event.preventDefault()
                setActive((i) => Math.max(0, i - 1))
              } else if (event.key === 'Enter') {
                event.preventDefault()
                run(active)
              }
            }}
          />
          <kbd className="kbd">Esc</kbd>
        </div>
        <div ref={list} id="palette-list" className="palette-list" role="listbox">
          {results.length === 0 ? <div className="palette-empty">No matching commands</div> : null}
          {results.map((command, index) => {
            const header = headers[index]
            return (
              <div key={command.id}>
                {header ? <div className="palette-group">{header}</div> : null}
                <div
                  id={`cmd-${command.id}`}
                  role="option"
                  aria-selected={index === active}
                  aria-disabled={command.disabled}
                  data-index={index}
                  className={`palette-item${index === active ? ' is-active' : ''}${command.disabled ? ' is-disabled' : ''}`}
                  onPointerMove={() => setActive(index)}
                  onClick={() => run(index)}
                >
                  <Icon name={command.icon ?? 'dot'} size={15} />
                  <span className="grow">{command.title}</span>
                  {query ? <span className="faint tiny">{command.group}</span> : null}
                  {command.shortcut ? <kbd className="kbd">{command.shortcut}</kbd> : null}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>,
    document.body,
  )
}
