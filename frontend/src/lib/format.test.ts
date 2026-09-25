import { describe, expect, it } from 'vitest'
import {
  clamp,
  confidenceLevel,
  displayUnit,
  formatBytes,
  formatDuration,
  formatHz,
  formatSigned,
  formatTime,
  formatUnitValue,
  humanize,
  pluralize,
  relativeTime,
} from './format'

describe('formatTime', () => {
  it('pads seconds and keeps the requested precision', () => {
    expect(formatTime(0)).toBe('0:00.00')
    expect(formatTime(75.5)).toBe('1:15.50')
    expect(formatTime(9.25, 1)).toBe('0:09.3')
    expect(formatTime(125, 0)).toBe('2:05')
  })

  it('carries rounding into the next second and minute', () => {
    expect(formatTime(3.999)).toBe('0:04.00')
    expect(formatTime(59.999)).toBe('1:00.00')
    expect(formatTime(119.6, 0)).toBe('2:00')
  })

  it('handles negative and non-finite input', () => {
    expect(formatTime(-3, 0)).toBe('-0:03')
    expect(formatTime(-0.001)).toBe('0:00.00')
    expect(formatTime(Number.NaN)).toBe('--:--')
    expect(formatTime(Number.POSITIVE_INFINITY)).toBe('--:--')
  })
})

describe('formatDuration', () => {
  it('uses seconds, minutes and hours', () => {
    expect(formatDuration(4.2)).toBe('4.2 s')
    expect(formatDuration(42)).toBe('42 s')
    expect(formatDuration(125)).toBe('2 min 5 s')
    expect(formatDuration(120)).toBe('2 min')
    expect(formatDuration(3700)).toBe('1 h 1 min')
    expect(formatDuration(null)).toBe('–')
  })

  it('never shows 60 seconds', () => {
    expect(formatDuration(59.7)).toBe('1 min')
    expect(formatDuration(119.6)).toBe('2 min')
    expect(formatDuration(9.97)).toBe('10 s')
  })
})

describe('number formatting', () => {
  it('signs values with a real minus and a plus-minus for zero', () => {
    expect(formatSigned(12, 0)).toBe('+12')
    expect(formatSigned(-2.5, 1, 'dB')).toBe('−2.5 dB')
    expect(formatSigned(0.04, 1)).toBe('±0.0')
    expect(formatSigned(undefined)).toBe('–')
  })

  it('scales bytes and frequencies', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(5 * 1024 ** 3)).toBe('5.0 GB')
    expect(formatHz(82.4)).toBe('82.4 Hz')
    expect(formatHz(440)).toBe('440 Hz')
    expect(formatHz(2500)).toBe('2.5 kHz')
    expect(formatHz(12000)).toBe('12 kHz')
  })

  it('clamps', () => {
    expect(clamp(5, 0, 3)).toBe(3)
    expect(clamp(-1, 0, 3)).toBe(0)
    expect(clamp(2, 0, 3)).toBe(2)
  })
})

describe('relativeTime', () => {
  const base = Date.parse('2026-03-01T12:00:00Z')
  const at = (ms: number) => new Date(base - ms).toISOString()

  it('describes recent times', () => {
    expect(relativeTime(at(30_000), base)).toBe('just now')
    expect(relativeTime(at(5 * 60_000), base)).toBe('5 min ago')
    expect(relativeTime(at(3 * 3_600_000), base)).toBe('3 h ago')
    expect(relativeTime(at(30 * 3_600_000), base)).toBe('yesterday')
    expect(relativeTime(at(3 * 86_400_000), base)).toBe('3 days ago')
  })

  it('passes through missing and unparseable values', () => {
    expect(relativeTime(null, base)).toBe('never')
    expect(relativeTime('not a date', base)).toBe('not a date')
  })
})

describe('confidence and units', () => {
  it('buckets confidence', () => {
    expect(confidenceLevel(0.9)).toBe('high')
    expect(confidenceLevel(0.6)).toBe('medium')
    expect(confidenceLevel(0.3)).toBe('low')
    expect(confidenceLevel(0.1)).toBe('insufficient')
    expect(confidenceLevel(null)).toBe('insufficient')
    expect(confidenceLevel(Number.NaN)).toBe('insufficient')
  })

  it('hides internal unit names', () => {
    expect(displayUnit('0-100')).toBe('')
    expect(displayUnit('log units')).toBe('')
    expect(displayUnit('cents')).toBe('¢')
    expect(displayUnit('dB')).toBe('dB')
  })

  it('formats values with their units', () => {
    expect(formatUnitValue(62.14, '0-100')).toBe('62.1')
    expect(formatUnitValue(0.42, 'ratio')).toBe('42%')
    expect(formatUnitValue(-35.5, 'cents')).toBe('-35.5¢')
    expect(formatUnitValue(240, 'Hz')).toBe('240 Hz')
    expect(formatUnitValue(true)).toBe('yes')
    expect(formatUnitValue([1, 2.5])).toBe('1.00 – 2.50')
    expect(formatUnitValue([])).toBe('none')
    expect(formatUnitValue(null)).toBe('–')
    expect(formatUnitValue(Number.POSITIVE_INFINITY, 'dB')).toBe('–')
  })
})

describe('humanize', () => {
  it('turns metric keys into readable labels', () => {
    expect(humanize('hnr_db')).toBe('HNR')
    expect(humanize('f1_hz')).toBe('F1')
    expect(humanize('onset_time_ms')).toBe('Onset time')
    expect(humanize('h1h2_db')).toBe('H1–H2')
    expect(humanize('cv_ratio')).toBe('C/V ratio')
  })

  it('pluralizes', () => {
    expect(pluralize(1, 'take')).toBe('1 take')
    expect(pluralize(3, 'take')).toBe('3 takes')
    expect(pluralize(2, 'analysis', 'analyses')).toBe('2 analyses')
  })
})
