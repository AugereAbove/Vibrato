import type { ReactNode } from 'react'
import { create } from 'zustand'

export interface ConfirmRequest {
  title: string
  body?: ReactNode
  confirmLabel?: string
  danger?: boolean
  resolve: (value: boolean) => void
}

export const useConfirmStore = create<{ request: ConfirmRequest | null }>(() => ({ request: null }))

export function confirmAction(options: Omit<ConfirmRequest, 'resolve'>): Promise<boolean> {
  return new Promise((resolve) => {
    useConfirmStore.getState().request?.resolve(false)
    useConfirmStore.setState({ request: { ...options, resolve } })
  })
}
