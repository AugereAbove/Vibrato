import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

type Side = 'top' | 'bottom' | 'left' | 'right'

interface Position {
  x: number
  y: number
  side: Side
}

function place(rect: DOMRect, side: Side): Position {
  const margin = 8
  const width = window.innerWidth
  const height = window.innerHeight
  let chosen = side
  if (side === 'top' && rect.top < 60) chosen = 'bottom'
  if (side === 'bottom' && rect.bottom > height - 60) chosen = 'top'
  if (side === 'left' && rect.left < 200) chosen = 'right'
  if (side === 'right' && rect.right > width - 200) chosen = 'left'
  const clampX = (x: number) => Math.max(margin + 140, Math.min(width - margin - 140, x))
  switch (chosen) {
    case 'top':
      return { x: clampX(rect.left + rect.width / 2), y: rect.top - 6, side: chosen }
    case 'bottom':
      return { x: clampX(rect.left + rect.width / 2), y: rect.bottom + 6, side: chosen }
    case 'left':
      return { x: rect.left - 6, y: rect.top + rect.height / 2, side: chosen }
    case 'right':
      return { x: rect.right + 6, y: rect.top + rect.height / 2, side: chosen }
  }
}

export function Tooltip({
  content,
  children,
  side = 'top',
  delay = 380,
  block = false,
}: {
  content: ReactNode
  children: ReactNode
  side?: Side
  delay?: number
  block?: boolean
}) {
  const [position, setPosition] = useState<Position | null>(null)
  const anchor = useRef<HTMLSpanElement>(null)
  const timer = useRef<number | null>(null)
  const id = useId()

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current)
    },
    [],
  )

  const show = () => {
    if (!content) return
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      const element = anchor.current?.firstElementChild ?? anchor.current
      if (element) setPosition(place(element.getBoundingClientRect(), side))
    }, delay)
  }

  const hide = () => {
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = null
    setPosition(null)
  }

  return (
    <span
      ref={anchor}
      className={block ? 'tooltip-anchor tooltip-anchor-block' : 'tooltip-anchor'}
      onPointerEnter={show}
      onPointerLeave={hide}
      onPointerDown={hide}
      onFocus={show}
      onBlur={hide}
      aria-describedby={position ? id : undefined}
    >
      {children}
      {position
        ? createPortal(
            <div
              role="tooltip"
              id={id}
              className={`tooltip tooltip-${position.side}`}
              style={{ left: position.x, top: position.y }}
            >
              {content}
            </div>,
            document.body,
          )
        : null}
    </span>
  )
}
