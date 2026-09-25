import { create } from 'zustand'

interface ImportState {
  open: boolean
  kind: 'reference' | 'take'
  files: File[]
  session: number
}

export const useImportStore = create<ImportState>(() => ({
  open: false,
  kind: 'take',
  files: [],
  session: 0,
}))

export function openImport(kind: 'reference' | 'take', files: File[] = []): void {
  useImportStore.setState((state) => ({ open: true, kind, files, session: state.session + 1 }))
}
