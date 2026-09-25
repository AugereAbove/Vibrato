import { useSyncExternalStore } from 'react'

export type ProjectTab = 'compare' | 'train' | 'progress'

export type Route =
  | { name: 'home' }
  | { name: 'project'; projectId: string; tab: ProjectTab; take?: string; ref?: string }
  | { name: 'settings'; section?: string }
  | { name: 'calibration' }
  | { name: 'profiles'; profileId?: string }
  | { name: 'diagnostics' }
  | { name: 'help'; topic?: string }

const TABS: ProjectTab[] = ['compare', 'train', 'progress']

export function parseHash(hash: string): Route {
  const clean = hash.replace(/^#\/?/, '')
  const [pathPart, searchPart = ''] = clean.split('?')
  const parts = pathPart.split('/').filter(Boolean).map(decodeURIComponent)
  const params = new URLSearchParams(searchPart)
  switch (parts[0]) {
    case 'p':
    case 'project': {
      if (!parts[1]) return { name: 'home' }
      const tab = TABS.includes(parts[2] as ProjectTab) ? (parts[2] as ProjectTab) : 'compare'
      return {
        name: 'project',
        projectId: parts[1],
        tab,
        take: params.get('take') ?? undefined,
        ref: params.get('ref') ?? undefined,
      }
    }
    case 'settings':
      return { name: 'settings', section: parts[1] }
    case 'calibration':
      return { name: 'calibration' }
    case 'profiles':
      return { name: 'profiles', profileId: parts[1] }
    case 'diagnostics':
      return { name: 'diagnostics' }
    case 'help':
      return { name: 'help', topic: parts[1] }
    default:
      return { name: 'home' }
  }
}

export function routeToHash(route: Route): string {
  switch (route.name) {
    case 'home':
      return '#/'
    case 'project': {
      const params = new URLSearchParams()
      if (route.take) params.set('take', route.take)
      if (route.ref) params.set('ref', route.ref)
      const search = params.toString()
      return `#/p/${encodeURIComponent(route.projectId)}/${route.tab}${search ? `?${search}` : ''}`
    }
    case 'settings':
      return route.section ? `#/settings/${encodeURIComponent(route.section)}` : '#/settings'
    case 'calibration':
      return '#/calibration'
    case 'profiles':
      return route.profileId ? `#/profiles/${encodeURIComponent(route.profileId)}` : '#/profiles'
    case 'diagnostics':
      return '#/diagnostics'
    case 'help':
      return route.topic ? `#/help/${encodeURIComponent(route.topic)}` : '#/help'
  }
}

let current = parseHash(typeof window === 'undefined' ? '' : window.location.hash)
let currentHash = typeof window === 'undefined' ? '' : window.location.hash
const listeners = new Set<() => void>()

function sync(): void {
  if (window.location.hash === currentHash) return
  currentHash = window.location.hash
  current = parseHash(currentHash)
  for (const listener of listeners) listener()
}

if (typeof window !== 'undefined') window.addEventListener('hashchange', sync)

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function getRoute(): Route {
  return current
}

export function useRoute(): Route {
  return useSyncExternalStore(subscribe, getRoute, getRoute)
}

export function navigate(route: Route, replace = false): void {
  const hash = routeToHash(route)
  if (hash === window.location.hash) return
  if (replace) window.history.replaceState(null, '', hash)
  else window.history.pushState(null, '', hash)
  sync()
}
