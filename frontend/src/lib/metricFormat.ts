import type { MetricComparison } from '../api/types'
import { displayUnit, formatSigned, formatUnitValue } from './format'
import { describeMidi } from './music'

const PRESENCE = new Set([
  'vibrato.presence',
  'breath.presence',
  'pitch.scoop_presence',
  'articulation.presence',
])

export function isPresenceMetric(metric: MetricComparison): boolean {
  return PRESENCE.has(metric.metric_id) || metric.metric_id.endsWith('.presence')
}

export function formatMetricValue(metric: MetricComparison, side: 'ref' | 'user', unit: string): string {
  const value = side === 'ref' ? metric.ref_value : metric.user_value
  if (value == null) return side === 'user' && metric.user_segment_id == null ? 'missing' : '–'
  if (typeof value === 'string') return value.replace(/_/g, ' ')
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (metric.metric_id === 'pitch.center') return describeMidi(value / 100)
  if (isPresenceMetric(metric)) return value >= 0.5 ? 'yes' : 'no'
  return formatUnitValue(value, unit)
}

export function formatMetricDifference(metric: MetricComparison, unit: string): string {
  if (metric.difference == null)
    return metric.direction && metric.direction !== 'unknown' ? metric.direction : '–'
  if (isPresenceMetric(metric)) return metric.direction
  const magnitude = Math.abs(metric.difference)
  const decimals = magnitude >= 100 ? 0 : magnitude >= 10 ? 1 : magnitude >= 1 ? 1 : 2
  const cleanUnit = displayUnit(unit)
  const text = formatSigned(metric.difference, decimals)
  if (!cleanUnit) return text
  return cleanUnit === '¢' || cleanUnit === '%' ? `${text}${cleanUnit}` : `${text} ${cleanUnit}`
}

export function severity(metric: MetricComparison): 'close' | 'minor' | 'notable' | 'large' | 'uncertain' {
  if (metric.confidence < 0.45 || metric.validity === 'LOW_CONFIDENCE') return 'uncertain'
  const z = Math.abs(metric.normalized ?? 0)
  if (z < 1) return 'close'
  if (z < 2) return 'minor'
  if (z < 3) return 'notable'
  return 'large'
}

export const SEVERITY_LABEL = {
  close: 'Close',
  minor: 'Small difference',
  notable: 'Noticeable',
  large: 'Large',
  uncertain: 'Insufficient confidence',
} as const
