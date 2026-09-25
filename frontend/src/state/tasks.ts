import { create } from 'zustand'
import { tasksApi } from '../api/endpoints'
import type { Task } from '../api/types'
import { pushToast } from './toasts'

const FINISHED = new Set(['complete', 'failed', 'cancelled', 'interrupted'])
const POLL_MS = 600

interface Handlers {
  onComplete?: (task: Task) => void
  onFailed?: (task: Task) => void
  silent?: boolean
}

interface TaskStoreState {
  tasks: Record<string, Task>
  order: string[]
}

export const useTaskStore = create<TaskStoreState>(() => ({ tasks: {}, order: [] }))

const handlers = new Map<string, Handlers[]>()
let timer: number | null = null
let saving = 0
const savingListeners = new Set<() => void>()

export function isFinished(task: Task): boolean {
  return FINISHED.has(task.status)
}

function upsert(task: Task): void {
  useTaskStore.setState((state) => ({
    tasks: { ...state.tasks, [task.id]: task },
    order: state.order.includes(task.id) ? state.order : [task.id, ...state.order].slice(0, 50),
  }))
}

function settle(task: Task): void {
  const list = handlers.get(task.id) ?? []
  handlers.delete(task.id)
  for (const handler of list) {
    if (task.status === 'complete') handler.onComplete?.(task)
    else handler.onFailed?.(task)
  }
  const silent = list.some((h) => h.silent)
  if (task.status === 'failed' && !silent) {
    pushToast({
      kind: 'error',
      title: task.error?.what ?? `${task.message || task.kind} failed`,
      body: task.error?.why,
      detail: task.error?.action,
    })
  } else if (task.status === 'interrupted' && !silent) {
    pushToast({ kind: 'warning', title: 'A background task was interrupted', body: task.message })
  }
}

async function poll(): Promise<void> {
  timer = null
  const pending = Object.values(useTaskStore.getState().tasks).filter((t) => !isFinished(t))
  if (pending.length === 0) return
  await Promise.all(
    pending.map(async (task) => {
      try {
        const { task: fresh } = await tasksApi.get(task.id)
        upsert(fresh)
        if (isFinished(fresh)) settle(fresh)
      } catch {
        return
      }
    }),
  )
  schedule()
}

function schedule(): void {
  if (timer !== null) return
  const pending = Object.values(useTaskStore.getState().tasks).some((t) => !isFinished(t))
  if (pending) timer = window.setTimeout(() => void poll(), POLL_MS)
}

export function trackTask(task: Task | null | undefined, handler: Handlers = {}): void {
  if (!task) return
  upsert(task)
  if (isFinished(task)) {
    handlers.set(task.id, [...(handlers.get(task.id) ?? []), handler])
    settle(task)
    return
  }
  handlers.set(task.id, [...(handlers.get(task.id) ?? []), handler])
  schedule()
}

export function waitForTask(task: Task | null | undefined, silent = false): Promise<Task> {
  return new Promise((resolve, reject) => {
    if (!task) {
      reject(new Error('No task was started.'))
      return
    }
    trackTask(task, {
      silent,
      onComplete: resolve,
      onFailed: (t) =>
        reject(Object.assign(new Error(t.error?.what ?? `${t.kind} ${t.status}`), { task: t })),
    })
  })
}

export async function cancelTask(id: string): Promise<void> {
  try {
    const { task } = await tasksApi.cancel(id)
    upsert(task)
    schedule()
  } catch {
    return
  }
}

export async function resumeActiveTasks(): Promise<void> {
  try {
    const { tasks } = await tasksApi.list(true)
    for (const task of tasks) trackTask(task, { silent: true })
  } catch {
    return
  }
}

export function activeTasks(state: TaskStoreState): Task[] {
  return state.order.map((id) => state.tasks[id]).filter((t) => t && !isFinished(t))
}

export function beginSave(): () => void {
  saving += 1
  for (const listener of savingListeners) listener()
  let done = false
  return () => {
    if (done) return
    done = true
    saving = Math.max(0, saving - 1)
    for (const listener of savingListeners) listener()
  }
}

export function subscribeSaving(listener: () => void): () => void {
  savingListeners.add(listener)
  return () => {
    savingListeners.delete(listener)
  }
}

export function savingCount(): number {
  return saving
}

export async function withSaving<T>(work: () => Promise<T>): Promise<T> {
  const end = beginSave()
  try {
    return await work()
  } finally {
    end()
  }
}
