import { useCallback, useEffect, useLayoutEffect, useRef, useSyncExternalStore } from 'react'

export type Fetcher<T> = (signal: AbortSignal) => Promise<T>

export type ResourceStatus = 'idle' | 'loading' | 'success' | 'error'

export interface ResourceSnapshot<T> {
  data: T | undefined
  error: unknown
  status: ResourceStatus
  stale: boolean
  updatedAt: number
}

interface Entry {
  snapshot: ResourceSnapshot<unknown>
  fetcher?: Fetcher<unknown>
  controller?: AbortController
  promise?: Promise<unknown>
  listeners: Set<() => void>
  lastUsed: number
}

const MAX_ENTRIES = 120
const entries = new Map<string, Entry>()
const EMPTY: ResourceSnapshot<never> = {
  data: undefined,
  error: undefined,
  status: 'idle',
  stale: false,
  updatedAt: 0,
}

function entryFor(key: string): Entry {
  let entry = entries.get(key)
  if (!entry) {
    entry = { snapshot: EMPTY, listeners: new Set(), lastUsed: Date.now() }
    entries.set(key, entry)
    evict()
  }
  entry.lastUsed = Date.now()
  return entry
}

function evict(): void {
  if (entries.size <= MAX_ENTRIES) return
  const idle = [...entries.entries()]
    .filter(([, entry]) => entry.listeners.size === 0 && entry.snapshot.status !== 'loading')
    .sort((a, b) => a[1].lastUsed - b[1].lastUsed)
  for (const [key] of idle.slice(0, entries.size - MAX_ENTRIES)) entries.delete(key)
}

function update(entry: Entry, patch: Partial<ResourceSnapshot<unknown>>): void {
  entry.snapshot = { ...entry.snapshot, ...patch }
  for (const listener of [...entry.listeners]) listener()
}

export function fetchResource<T>(key: string, fetcher: Fetcher<T>, force = false): Promise<T> {
  const entry = entryFor(key)
  entry.fetcher = fetcher as Fetcher<unknown>
  if (entry.promise && !force) return entry.promise as Promise<T>
  entry.controller?.abort()
  const controller = new AbortController()
  entry.controller = controller
  update(entry, { status: 'loading', error: undefined })
  const promise = fetcher(controller.signal).then(
    (data) => {
      if (entry.controller === controller) {
        entry.promise = undefined
        entry.controller = undefined
        update(entry, { data, status: 'success', stale: false, error: undefined, updatedAt: Date.now() })
      }
      return data
    },
    (error: unknown) => {
      if (entry.controller === controller) {
        entry.promise = undefined
        entry.controller = undefined
        const aborted = error instanceof DOMException && error.name === 'AbortError'
        if (!aborted) update(entry, { status: 'error', error })
      }
      throw error
    },
  )
  entry.promise = promise
  promise.catch(() => undefined)
  return promise
}

export function invalidate(match: string | ((key: string) => boolean)): void {
  const test =
    typeof match === 'string' ? (key: string) => key === match || key.startsWith(`${match}:`) : match
  for (const [key, entry] of entries) {
    if (!test(key)) continue
    if (entry.listeners.size > 0 && entry.fetcher) {
      entry.snapshot = { ...entry.snapshot, stale: true }
      void fetchResource(key, entry.fetcher, true).catch(() => undefined)
    } else {
      update(entry, { stale: true })
    }
  }
}

export function forget(match: string | ((key: string) => boolean)): void {
  const test =
    typeof match === 'string' ? (key: string) => key === match || key.startsWith(`${match}:`) : match
  for (const key of [...entries.keys()]) {
    const entry = entries.get(key)
    if (entry && test(key) && entry.listeners.size === 0) entries.delete(key)
  }
}

export function setResourceData<T>(key: string, updater: (previous: T | undefined) => T): void {
  const entry = entryFor(key)
  const next = updater(entry.snapshot.data as T | undefined)
  update(entry, { data: next, status: 'success', updatedAt: Date.now() })
}

export function peekResource<T>(key: string): T | undefined {
  return entries.get(key)?.snapshot.data as T | undefined
}

function subscribeKey(key: string, listener: () => void): () => void {
  const entry = entryFor(key)
  entry.listeners.add(listener)
  return () => {
    entry.listeners.delete(listener)
  }
}

export interface ResourceState<T> {
  data: T | undefined
  error: unknown
  loading: boolean
  status: ResourceStatus
  refresh: () => Promise<T | undefined>
}

export function useResource<T>(key: string | null, fetcher: Fetcher<T>): ResourceState<T> {
  const fetcherRef = useRef(fetcher)
  useLayoutEffect(() => {
    fetcherRef.current = fetcher
  })
  const subscribe = useCallback(
    (listener: () => void) => (key ? subscribeKey(key, listener) : () => undefined),
    [key],
  )
  const getSnapshot = useCallback(
    () => (key ? (entryFor(key).snapshot as ResourceSnapshot<T>) : (EMPTY as ResourceSnapshot<T>)),
    [key],
  )
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
  useEffect(() => {
    if (!key) return
    const entry = entryFor(key)
    const run: Fetcher<T> = (signal) => fetcherRef.current(signal)
    entry.fetcher = run as Fetcher<unknown>
    if (entry.snapshot.status === 'idle' || entry.snapshot.stale) {
      void fetchResource(key, run).catch(() => undefined)
    }
  }, [key])
  const refresh = useCallback(async () => {
    if (!key) return undefined
    try {
      return await fetchResource(key, (signal) => fetcherRef.current(signal), true)
    } catch {
      return undefined
    }
  }, [key])
  return {
    data: snapshot.data,
    error: snapshot.error,
    loading: snapshot.status === 'loading' && snapshot.data === undefined,
    status: snapshot.status,
    refresh,
  }
}
