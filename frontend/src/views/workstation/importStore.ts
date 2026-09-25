import { create } from 'zustand'

interface ImportState {
  open: boolean
  kind: 'reference' | 'take'
  files: File[]
}

export const useImportStore = create<ImportState>(() => ({ open: false, kind: 'take', files: [] }))

export function openImport(kind: 'reference' | 'take', files: File[] = []): void {
  useImportStore.setState({ open: true, kind, files })
}
