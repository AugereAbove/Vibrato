import { dismissToast, pauseToast, resumeToast, useToasts } from '../../state/toasts'
import { Button, IconButton } from './Button'
import { Icon } from './Icon'

const ICONS = { info: 'info', success: 'check', warning: 'alert', error: 'alert' } as const

export function Toaster() {
  const toasts = useToasts((state) => state.toasts)
  return (
    <div className="toaster" aria-live="polite" aria-relevant="additions">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`toast toast-${toast.kind}`}
          role={toast.kind === 'error' ? 'alert' : 'status'}
          onPointerEnter={() => pauseToast(toast.id)}
          onPointerLeave={() => resumeToast(toast.id)}
        >
          <Icon name={ICONS[toast.kind]} size={16} className="toast-icon" />
          <div className="toast-content">
            <div className="toast-title">{toast.title}</div>
            {toast.body ? <div className="toast-body">{toast.body}</div> : null}
            {toast.detail ? <div className="toast-detail">{toast.detail}</div> : null}
            {toast.action ? (
              <div style={{ marginTop: 6 }}>
                <Button
                  size="xs"
                  variant="secondary"
                  onClick={() => {
                    toast.action?.run()
                    dismissToast(toast.id)
                  }}
                >
                  {toast.action.label}
                </Button>
              </div>
            ) : null}
          </div>
          <IconButton
            icon="x"
            label="Dismiss"
            size="xs"
            onClick={() => dismissToast(toast.id)}
            tooltipSide="left"
          />
        </div>
      ))}
    </div>
  )
}
