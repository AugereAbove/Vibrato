import { useEffect } from 'react'
import { create } from 'zustand'

export interface Command {
  id: string
  title: string
  group: string
  icon?: string
  shortcut?: string
  keywords?: string
  disabled?: boolean
  run: () => void
}

interface CommandState {
  sources: Record<string, Command[]>
}

export const useCommands = create<CommandState>(() => ({ sources: {} }))

export function useRegisterCommands(source: string, commands: Command[]): void {
  useEffect(() => {
    useCommands.setState((state) => ({ sources: { ...state.sources, [source]: commands } }))
  }, [source, commands])
  useEffect(
    () => () => {
      useCommands.setState((state) => {
        const next = { ...state.sources }
        delete next[source]
        return { sources: next }
      })
    },
    [source],
  )
}

export function allCommands(state: CommandState): Command[] {
  return Object.values(state.sources).flat()
}

export function score(command: Command, query: string): number {
  if (!query) return 1
  const text = `${command.title} ${command.group} ${command.keywords ?? ''}`.toLowerCase()
  const q = query.toLowerCase().trim()
  if (command.title.toLowerCase().startsWith(q)) return 100
  if (text.includes(q)) return 60
  let position = 0
  let hits = 0
  for (const char of q) {
    const found = text.indexOf(char, position)
    if (found < 0) return 0
    hits += found === position ? 2 : 1
    position = found + 1
  }
  return hits
}
