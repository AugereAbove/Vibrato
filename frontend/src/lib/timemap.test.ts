import { describe, expect, it } from 'vitest'
import { IDENTITY_MAP, TimeMap } from './timemap'

describe('TimeMap', () => {
  const map = new TimeMap({
    ref_times: [0, 1, 2, 3],
    user_times: [0, 1.5, 2.5, 4],
    confidence: [1, 0.9, 0.2, 0.8],
  })

  it('interpolates between alignment points in both directions', () => {
    expect(map.refToUser(0.5)).toBeCloseTo(0.75)
    expect(map.refToUser(1.5)).toBeCloseTo(2)
    expect(map.userToRef(2)).toBeCloseTo(1.5)
    expect(map.userToRef(3.25)).toBeCloseTo(2.5)
  })

  it('extends linearly past both ends', () => {
    expect(map.refToUser(-1)).toBeCloseTo(-1)
    expect(map.refToUser(4)).toBeCloseTo(5)
    expect(map.userToRef(5)).toBeCloseTo(4)
  })

  it('round-trips a strictly increasing path', () => {
    for (let t = 0; t <= 3; t += 0.125) expect(map.userToRef(map.refToUser(t))).toBeCloseTo(t, 6)
  })

  it('reports the confidence of the enclosing step', () => {
    expect(map.confidenceAt(0.2)).toBe(1)
    expect(map.confidenceAt(2.1)).toBeCloseTo(0.2)
    expect(map.confidenceAt(10)).toBeCloseTo(0.8)
  })

  it('never runs backwards when the path is jittery', () => {
    const jittery = new TimeMap({
      ref_times: [0, 2, 1.5, 3, 2.9, 4],
      user_times: [0, 2.2, 2.1, 3.1, 3.3, 4.4],
      confidence: [1, 1, 1, 1, 1, 1],
    })
    let last = -Infinity
    for (let t = -0.5; t <= 4.5; t += 0.05) {
      const mapped = jittery.refToUser(t)
      expect(mapped).toBeGreaterThanOrEqual(last)
      last = mapped
    }
  })

  it('falls back to identity without a usable path', () => {
    expect(IDENTITY_MAP.identity).toBe(true)
    expect(IDENTITY_MAP.refToUser(3.3)).toBe(3.3)
    expect(IDENTITY_MAP.confidenceAt(3.3)).toBe(1)
    const single = new TimeMap({ ref_times: [1], user_times: [2], confidence: [1] })
    expect(single.identity).toBe(true)
    expect(single.userToRef(7)).toBe(7)
  })
})
