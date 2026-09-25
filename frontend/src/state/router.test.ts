import { describe, expect, it } from 'vitest'
import { getRoute, navigate, parseHash, routeToHash, type Route } from './router'

describe('parseHash', () => {
  it('reads project routes with their query', () => {
    expect(parseHash('#/p/abc/train?take=t1&ref=r1')).toEqual({
      name: 'project',
      projectId: 'abc',
      tab: 'train',
      take: 't1',
      ref: 'r1',
    })
  })

  it('defaults unknown tabs and paths', () => {
    expect(parseHash('#/p/abc/unknown')).toMatchObject({ name: 'project', tab: 'compare' })
    expect(parseHash('#/p/')).toEqual({ name: 'home' })
    expect(parseHash('')).toEqual({ name: 'home' })
    expect(parseHash('#/nowhere')).toEqual({ name: 'home' })
  })
})

describe('routeToHash', () => {
  const routes: Route[] = [
    { name: 'home' },
    { name: 'project', projectId: 'a b/c', tab: 'progress' },
    { name: 'project', projectId: 'p1', tab: 'compare', take: 'take 1', ref: 'ref&1' },
    { name: 'settings' },
    { name: 'settings', section: 'audio' },
    { name: 'calibration' },
    { name: 'profiles', profileId: 'prof-1' },
    { name: 'diagnostics' },
    { name: 'help', topic: 'metrics' },
  ]

  it.each(routes)('round-trips %o', (route) => {
    expect(parseHash(routeToHash(route))).toEqual(route)
  })

  it('escapes ids', () => {
    expect(routeToHash({ name: 'project', projectId: 'a b', tab: 'train' })).toBe('#/p/a%20b/train')
  })
})

describe('navigate', () => {
  it('updates the hash and the current route', () => {
    navigate({ name: 'diagnostics' })
    expect(window.location.hash).toBe('#/diagnostics')
    expect(getRoute()).toEqual({ name: 'diagnostics' })
    navigate({ name: 'help', topic: 'alignment' }, true)
    expect(getRoute()).toEqual({ name: 'help', topic: 'alignment' })
  })
})
