import { describe, expect, it } from 'vitest'
import type { MetricComparison } from '../api/types'
import { formatMetricDifference, formatMetricValue, severity } from './metricFormat'

function metric(overrides: Partial<MetricComparison> = {}): MetricComparison {
  return {
    metric_id: 'pitch.mean_error',
    category: 'pitch',
    level: 'note',
    label: 'Pitch',
    ref_segment_id: 'r1',
    user_segment_id: 'u1',
    ref_start: 0,
    ref_end: 1,
    user_start: 0,
    user_end: 1,
    ref_value: 0,
    user_value: 0,
    difference: 0,
    normalized: 0,
    direction: 'same',
    confidence: 0.9,
    validity: 'VALID',
    score: 90,
    weight: 1,
    importance: 1,
    evidence: {},
    notes: [],
    ...overrides,
  }
}

describe('formatMetricValue', () => {
  it('shows note names for pitch centres', () => {
    expect(formatMetricValue(metric({ metric_id: 'pitch.center', ref_value: 6900 }), 'ref', 'cents')).toBe(
      'A4 ±0¢',
    )
  })

  it('distinguishes a missing counterpart from an unavailable value', () => {
    expect(formatMetricValue(metric({ user_value: null, user_segment_id: null }), 'user', '')).toBe('missing')
    expect(formatMetricValue(metric({ user_value: null }), 'user', '')).toBe('–')
  })

  it('renders presence as yes or no and cleans categorical labels', () => {
    expect(formatMetricValue(metric({ metric_id: 'vibrato.presence', user_value: 0.8 }), 'user', '')).toBe(
      'yes',
    )
    expect(formatMetricValue(metric({ metric_id: 'breath.presence', ref_value: 0.1 }), 'ref', '')).toBe('no')
    expect(formatMetricValue(metric({ ref_value: 'head_voice' }), 'ref', '')).toBe('head voice')
    expect(formatMetricValue(metric({ ref_value: false }), 'ref', '')).toBe('no')
  })

  it('formats plain numbers with their unit', () => {
    expect(formatMetricValue(metric({ ref_value: 5.62 }), 'ref', 'Hz')).toBe('5.62 Hz')
  })
})

describe('formatMetricDifference', () => {
  it('attaches compact units without a space', () => {
    expect(formatMetricDifference(metric({ difference: 23.4 }), 'cents')).toBe('+23.4¢')
  })

  it('keeps small differences readable', () => {
    expect(formatMetricDifference(metric({ difference: -0.034 }), 'dB')).toBe('−0.03 dB')
    expect(formatMetricDifference(metric({ difference: 140 }), 'ms')).toBe('+140 ms')
  })

  it('falls back to the direction when there is no number', () => {
    expect(formatMetricDifference(metric({ difference: null, direction: 'later' }), 's')).toBe('later')
    expect(formatMetricDifference(metric({ difference: null, direction: 'unknown' }), 's')).toBe('–')
  })
})

describe('severity', () => {
  it('grades by normalised distance', () => {
    expect(severity(metric({ normalized: 0.5 }))).toBe('close')
    expect(severity(metric({ normalized: 1.5 }))).toBe('minor')
    expect(severity(metric({ normalized: -2.5 }))).toBe('notable')
    expect(severity(metric({ normalized: 4 }))).toBe('large')
  })

  it('refuses to grade low-confidence measurements', () => {
    expect(severity(metric({ normalized: 4, confidence: 0.3 }))).toBe('uncertain')
    expect(severity(metric({ normalized: 4, validity: 'LOW_CONFIDENCE' }))).toBe('uncertain')
  })
})
