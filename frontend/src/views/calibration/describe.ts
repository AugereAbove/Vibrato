import { describeError } from '../../api/client'

export function describeApi(error: unknown): string {
  const { what, why, action } = describeError(error)
  return [what, why, action].filter(Boolean).join(' ')
}
