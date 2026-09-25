import { useEffect, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Button, IconButton } from './Button'
import { useConfirmStore } from './confirm'

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  width = 520,
  className,
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  description?: ReactNode
  children?: ReactNode
  footer?: ReactNode
  width?: number
  className?: string
}) {
  const panel = useRef<HTMLDivElement>(null)
  const restore = useRef<HTMLElement | null>(null)
  const titleId = useId()
  const onCloseRef = useRef(onClose)

  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    if (!open) return
    restore.current = document.activeElement as HTMLElement | null
    const frame = window.requestAnimationFrame(() => {
      const element = panel.current
      if (!element) return
      const preferred = element.querySelector<HTMLElement>('[data-autofocus]')
      ;(preferred ?? element).focus()
    })
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab' || !panel.current) return
      const items = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)]
      if (items.length === 0) return
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => {
      window.cancelAnimationFrame(frame)
      window.removeEventListener('keydown', onKey, true)
      restore.current?.focus?.()
    }
  }, [open])

  if (!open) return null
  return createPortal(
    <div
      className="dialog-layer"
      onPointerDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        ref={panel}
        className={`dialog${className ? ` ${className}` : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        style={{ width: `min(${width}px, calc(100vw - 32px))` }}
      >
        <header className="dialog-header">
          <div className="stack" style={{ gap: 4 }}>
            <h3 id={titleId}>{title}</h3>
            {description ? <p className="muted small">{description}</p> : null}
          </div>
          <IconButton icon="x" label="Close" onClick={onClose} tooltipSide="left" />
        </header>
        <div className="dialog-body">{children}</div>
        {footer ? <footer className="dialog-footer">{footer}</footer> : null}
      </div>
    </div>,
    document.body,
  )
}

export function ConfirmHost() {
  const request = useConfirmStore((state) => state.request)
  const close = (value: boolean) => {
    request?.resolve(value)
    useConfirmStore.setState({ request: null })
  }
  return (
    <Dialog
      open={request !== null}
      onClose={() => close(false)}
      title={request?.title ?? ''}
      width={440}
      footer={
        <>
          <Button variant="ghost" onClick={() => close(false)}>
            Cancel
          </Button>
          <Button variant={request?.danger ? 'danger' : 'primary'} onClick={() => close(true)} data-autofocus>
            {request?.confirmLabel ?? 'Confirm'}
          </Button>
        </>
      }
    >
      {request?.body ? <div className="muted">{request.body}</div> : null}
    </Dialog>
  )
}
