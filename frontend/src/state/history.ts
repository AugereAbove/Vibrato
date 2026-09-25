import { create } from 'zustand'
import { reportError } from './errors'

export interface UndoEntry {
  label: string
  undo: () => Promise<void> | void
  redo: () => Promise<void> | void
}

interface HistoryState {
  past: UndoEntry[]
  future: UndoEntry[]
  busy: boolean
}

const LIMIT = 50

export const useHistory = create<HistoryState>(() => ({ past: [], future: [], busy: false }))

export function pushUndo(entry: UndoEntry): void {
  useHistory.setState((state) => ({ past: [...state.past.slice(-(LIMIT - 1)), entry], future: [] }))
}

export async function undo(): Promise<void> {
  const { past, busy } = useHistory.getState()
  const entry = past[past.length - 1]
  if (!entry || busy) return
  useHistory.setState({ busy: true })
  try {
    await entry.undo()
    useHistory.setState((state) => ({ past: state.past.slice(0, -1), future: [...state.future, entry] }))
  } catch (error) {
    reportError(error, `Could not undo "${entry.label}"`)
  } finally {
    useHistory.setState({ busy: false })
  }
}

export async function redo(): Promise<void> {
  const { future, busy } = useHistory.getState()
  const entry = future[future.length - 1]
  if (!entry || busy) return
  useHistory.setState({ busy: true })
  try {
    await entry.redo()
    useHistory.setState((state) => ({ future: state.future.slice(0, -1), past: [...state.past, entry] }))
  } catch (error) {
    reportError(error, `Could not redo "${entry.label}"`)
  } finally {
    useHistory.setState({ busy: false })
  }
}

export function clearHistory(): void {
  useHistory.setState({ past: [], future: [] })
}
