import { describe, expect, it } from 'vitest'
import { yin } from './pitch'

const RATE = 44100

function tone(f0: number, harmonics = 1, length = 2048): Float32Array {
  const out = new Float32Array(length)
  for (let i = 0; i < length; i += 1) {
    let value = 0
    for (let k = 1; k <= harmonics; k += 1) value += Math.sin((2 * Math.PI * f0 * k * i) / RATE) / k
    out[i] = 0.4 * value
  }
  return out
}

function noise(length = 2048, seed = 7): Float32Array {
  const out = new Float32Array(length)
  let state = seed
  for (let i = 0; i < length; i += 1) {
    state = (state * 1664525 + 1013904223) >>> 0
    out[i] = state / 2 ** 31 - 1
  }
  return out
}

describe('yin', () => {
  it.each([110, 220, 440, 659.25])('tracks a %s Hz sine', (f0) => {
    const reading = yin(tone(f0), RATE)
    expect(reading.f0).not.toBeNull()
    expect(Math.abs(1200 * Math.log2((reading.f0 as number) / f0))).toBeLessThan(10)
    expect(reading.clarity).toBeGreaterThan(0.9)
  })

  it('finds the fundamental of a harmonic-rich tone instead of an octave', () => {
    const reading = yin(tone(147, 6), RATE)
    expect(reading.f0).not.toBeNull()
    expect(reading.f0 as number).toBeGreaterThan(140)
    expect(reading.f0 as number).toBeLessThan(154)
  })

  it('stays silent on silence and noise', () => {
    expect(yin(new Float32Array(2048), RATE).f0).toBeNull()
    expect(yin(noise(), RATE).f0).toBeNull()
  })

  it('gives up when the buffer is too short for the range', () => {
    expect(yin(tone(220, 1, 64), RATE)).toEqual({ f0: null, clarity: 0 })
  })
})
