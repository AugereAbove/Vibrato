import { create } from 'zustand'
import type { MenuEntry } from './Menu'

interface ContextState {
  menu: { items: MenuEntry[]; x: number; y: number; label: string } | null
}

export const useContextMenu = create<ContextState>(() => ({ menu: null }))

export function openContextMenu(
  event: { clientX: number; clientY: number; preventDefault: () => void },
  items: MenuEntry[],
  label = 'Context menu',
): void {
  event.preventDefault()
  useContextMenu.setState({ menu: { items, x: event.clientX, y: event.clientY, label } })
}
