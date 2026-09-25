import { describe, expect, it } from 'vitest'
import { centsOff, describeHz, describeMidi, hzToMidi, isBlackKey, midiToHz, noteName } from './music'

describe('pitch helpers', () => {
  it('converts between hertz and MIDI', () => {
    expect(hzToMidi(440)).toBe(69)
    expect(hzToMidi(880)).toBeCloseTo(81)
    expect(midiToHz(60)).toBeCloseTo(261.6256, 3)
    expect(hzToMidi(432, 432)).toBe(69)
    expect(hzToMidi(midiToHz(57.3))).toBeCloseTo(57.3, 9)
  })

  it('names notes with octaves', () => {
    expect(noteName(60)).toBe('C4')
    expect(noteName(61)).toBe('C♯4')
    expect(noteName(59.6)).toBe('C4')
    expect(noteName(69, false)).toBe('A')
    expect(noteName(21)).toBe('A0')
  })

  it('knows the black keys', () => {
    expect([60, 61, 62, 63, 64, 65, 66].map(isBlackKey)).toEqual([
      false,
      true,
      false,
      true,
      false,
      false,
      true,
    ])
  })

  it('describes the offset in cents', () => {
    expect(centsOff(69.25)).toBeCloseTo(25)
    expect(describeMidi(69.25)).toBe('A4 +25¢')
    expect(describeHz(440)).toBe('A4 ±0¢')
    expect(describeHz(440 * 2 ** (-0.1 / 12))).toBe('A4 −10¢')
  })
})
