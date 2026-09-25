import { useSyncExternalStore } from 'react'
import { create } from 'zustand'
import { http } from '../api/client'
import { preferencesApi } from '../api/endpoints'
import type { PreferenceSchemaItem, PreferenceValue } from '../api/types'
import { readStorage, writeStorage } from '../lib/storage'
import { reportError } from './errors'

interface PrefsState {
  values: Record<string, PreferenceValue>
  defaults: Record<string, PreferenceValue>
  schema: PreferenceSchemaItem[]
  loaded: boolean
}

const CACHE_KEY = 'vibrato.prefs.cache'

const LOCAL_DEFAULTS: Record<string, PreferenceValue> = {
  'display.theme': 'system',
  'display.view_mode': 'coach',
  'display.reduced_motion': 'system',
  'display.spectrogram_resolution': 'medium',
  'display.spectrogram_max_hz': 8000,
  'display.show_note_names': true,
  'audio.gain_match': true,
  'audio.preroll_s': 3,
  'audio.metronome': false,
  'audio.metronome_bpm': 84,
  'audio.reference_during_recording': true,
  'audio.reference_level': 0.8,
  'audio.monitor_level': 0,
  'audio.latency_ms': 0,
  'audio.loop_recording': false,
  'training.auto_loop': true,
  'training.slow_factor': 0.75,
  'training.alternate_ab': false,
  'training.mastery_threshold': 85,
  'training.min_takes_before_move_on': 3,
}

export const usePrefsStore = create<PrefsState>(() => ({
  values: { ...LOCAL_DEFAULTS, ...readStorage<Record<string, PreferenceValue>>(CACHE_KEY, {}) },
  defaults: LOCAL_DEFAULTS,
  schema: [],
  loaded: false,
}))

let pending: Record<string, PreferenceValue> = {}
let flushTimer: number | null = null

function cacheLocally(values: Record<string, PreferenceValue>): void {
  const subset: Record<string, PreferenceValue> = {}
  for (const key of Object.keys(values)) {
    if (key.startsWith('display.') || key.startsWith('audio.') || key.startsWith('training.'))
      subset[key] = values[key]
  }
  writeStorage(CACHE_KEY, subset)
}

export async function loadPrefs(): Promise<void> {
  try {
    const response = await preferencesApi.get()
    usePrefsStore.setState({
      values: { ...response.values, ...pending },
      defaults: response.defaults,
      schema: response.schema,
      loaded: true,
    })
    cacheLocally(usePrefsStore.getState().values)
  } catch (error) {
    usePrefsStore.setState({ loaded: true })
    reportError(error, 'Settings could not be loaded')
  }
}

async function flush(): Promise<void> {
  flushTimer = null
  const batch = pending
  pending = {}
  if (Object.keys(batch).length === 0) return
  try {
    const { values } = await preferencesApi.update(batch)
    usePrefsStore.setState((state) => ({ values: { ...state.values, ...values, ...pending } }))
    cacheLocally(usePrefsStore.getState().values)
  } catch (error) {
    reportError(error, 'Setting was not saved')
  }
}

function flushBeforeLeaving(): void {
  if (Object.keys(pending).length === 0) return
  if (flushTimer !== null) window.clearTimeout(flushTimer)
  flushTimer = null
  const body = JSON.stringify({ values: pending })
  pending = {}
  void fetch(http.url('/preferences'), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
  }).catch(() => undefined)
}

if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', flushBeforeLeaving)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushBeforeLeaving()
  })
}

export function setPref(key: string, value: PreferenceValue): void {
  usePrefsStore.setState((state) => ({ values: { ...state.values, [key]: value } }))
  cacheLocally(usePrefsStore.getState().values)
  pending[key] = value
  if (flushTimer !== null) window.clearTimeout(flushTimer)
  flushTimer = window.setTimeout(() => void flush(), 250)
}

export async function resetPrefs(section?: string): Promise<void> {
  try {
    const { values } = await preferencesApi.reset(section)
    usePrefsStore.setState({ values })
    cacheLocally(values)
  } catch (error) {
    reportError(error, 'Settings were not reset')
  }
}

export function usePref<T extends PreferenceValue>(key: string, fallback: T): T {
  const value = usePrefsStore((state) => state.values[key])
  return (value === undefined || value === null ? fallback : value) as T
}

export function getPref<T extends PreferenceValue>(key: string, fallback: T): T {
  const value = usePrefsStore.getState().values[key]
  return (value === undefined || value === null ? fallback : value) as T
}

const darkQuery =
  typeof window !== 'undefined' && window.matchMedia
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null
const motionQuery =
  typeof window !== 'undefined' && window.matchMedia
    ? window.matchMedia('(prefers-reduced-motion: reduce)')
    : null

function subscribeMedia(listener: () => void): () => void {
  darkQuery?.addEventListener('change', listener)
  motionQuery?.addEventListener('change', listener)
  return () => {
    darkQuery?.removeEventListener('change', listener)
    motionQuery?.removeEventListener('change', listener)
  }
}

function systemDark(): boolean {
  return darkQuery ? darkQuery.matches : true
}

function systemReducedMotion(): boolean {
  return motionQuery ? motionQuery.matches : false
}

export function useResolvedTheme(): 'dark' | 'light' {
  const theme = usePref<string>('display.theme', 'system')
  const dark = useSyncExternalStore(subscribeMedia, systemDark, () => true)
  if (theme === 'dark' || theme === 'light') return theme
  return dark ? 'dark' : 'light'
}

export function useReducedMotion(): boolean {
  const setting = usePref<string>('display.reduced_motion', 'system')
  const system = useSyncExternalStore(subscribeMedia, systemReducedMotion, () => false)
  if (setting === 'on') return true
  if (setting === 'off') return false
  return system
}

export function reducedMotionNow(): boolean {
  const setting = getPref<string>('display.reduced_motion', 'system')
  if (setting === 'on') return true
  if (setting === 'off') return false
  return systemReducedMotion()
}

export type ViewMode = 'coach' | 'analyst' | 'research'

export function useViewMode(): ViewMode {
  const mode = usePref<string>('display.view_mode', 'coach')
  return mode === 'analyst' || mode === 'research' ? mode : 'coach'
}
