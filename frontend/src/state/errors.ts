import { describeError } from '../api/client'
import { pushToast } from './toasts'

export function reportError(error: unknown, context?: string): void {
  if (error instanceof DOMException && error.name === 'AbortError') return
  const { what, why, action } = describeError(error)
  pushToast({
    kind: 'error',
    title: context ? `${context}: ${what}` : what,
    body: why,
    detail: action,
  })
}

export async function attempt<T>(work: () => Promise<T>, context?: string): Promise<T | undefined> {
  try {
    return await work()
  } catch (error) {
    reportError(error, context)
    return undefined
  }
}
