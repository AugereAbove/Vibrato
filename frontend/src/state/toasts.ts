import { create } from 'zustand'

export type ToastKind = 'info' | 'success' | 'warning' | 'error'

export interface Toast {
  id: number
  kind: ToastKind
  title: string
  body?: string
  detail?: string
  action?: { label: string; run: () => void }
  timeout: number
}

interface ToastState {
  toasts: Toast[]
}

export const useToasts = create<ToastState>(() => ({ toasts: [] }))

let counter = 0
const timers = new Map<number, number>()

export function dismissToast(id: number): void {
  const timer = timers.get(id)
  if (timer) window.clearTimeout(timer)
  timers.delete(id)
  useToasts.setState((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }))
}

export function pushToast(toast: Omit<Toast, 'id' | 'timeout'> & { timeout?: number }): number {
  counter += 1
  const id = counter
  const timeout = toast.timeout ?? (toast.kind === 'error' ? 10000 : toast.kind === 'warning' ? 8000 : 5000)
  useToasts.setState((state) => ({ toasts: [...state.toasts.slice(-3), { ...toast, id, timeout }] }))
  if (timeout > 0)
    timers.set(
      id,
      window.setTimeout(() => dismissToast(id), timeout),
    )
  return id
}

export function pauseToast(id: number): void {
  const timer = timers.get(id)
  if (timer) window.clearTimeout(timer)
  timers.delete(id)
}

export function resumeToast(id: number): void {
  const toast = useToasts.getState().toasts.find((t) => t.id === id)
  if (!toast || toast.timeout <= 0) return
  timers.set(
    id,
    window.setTimeout(() => dismissToast(id), 3000),
  )
}
