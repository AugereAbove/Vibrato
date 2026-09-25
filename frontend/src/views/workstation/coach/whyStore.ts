import { create } from 'zustand'
import type { Region } from '../../../state/workspace'

export const useWhyStore = create<{ region: Region | null }>(() => ({ region: null }))

export function openWhy(region: Region): void {
  useWhyStore.setState({ region: { ...region } })
}

export function closeWhy(): void {
  useWhyStore.setState({ region: null })
}
