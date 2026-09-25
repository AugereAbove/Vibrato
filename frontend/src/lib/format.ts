export function formatTime(seconds: number, decimals = 2): string {
  if (!Number.isFinite(seconds)) return '--:--'
  const sign = seconds < 0 ? '-' : ''
  const value = Math.abs(seconds)
  const minutes = Math.floor(value / 60)
  const rest = value - minutes * 60
  const whole = Math.floor(rest)
  const fraction = decimals > 0 ? (rest - whole).toFixed(decimals).slice(1) : ''
  return `${sign}${minutes}:${String(whole).padStart(2, '0')}${fraction}`
}

export function formatSeconds(seconds: number | null | undefined, decimals = 2): string {
  if (seconds == null || !Number.isFinite(seconds)) return '–'
  return `${seconds.toFixed(decimals)} s`
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '–'
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds - minutes * 60)
  if (minutes < 60) return rest ? `${minutes} min ${rest} s` : `${minutes} min`
  const hours = Math.floor(minutes / 60)
  return `${hours} h ${minutes % 60} min`
}

export function formatNumber(value: number | null | undefined, decimals = 1): string {
  if (value == null || !Number.isFinite(value)) return '–'
  return value.toFixed(decimals)
}

export function formatSigned(value: number | null | undefined, decimals = 1, unit = ''): string {
  if (value == null || !Number.isFinite(value)) return '–'
  const rounded = Number(value.toFixed(decimals))
  const sign = rounded > 0 ? '+' : rounded < 0 ? '−' : '±'
  const text = `${sign}${Math.abs(rounded).toFixed(decimals)}`
  return unit ? `${text} ${unit}` : text
}

export function formatPercent(value: number | null | undefined, decimals = 0): string {
  if (value == null || !Number.isFinite(value)) return '–'
  return `${(value * 100).toFixed(decimals)}%`
}

export function formatScore(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '–'
  return value.toFixed(0)
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes)) return '–'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(unit === 0 ? 0 : value < 10 ? 1 : 0)} ${units[unit]}`
}

export function formatHz(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '–'
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)} kHz`
  return `${value.toFixed(value < 100 ? 1 : 0)} Hz`
}

export function formatDb(value: number | null | undefined, decimals = 1): string {
  if (value == null || !Number.isFinite(value)) return '–'
  return `${value.toFixed(decimals)} dB`
}

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

export function relativeTime(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return 'never'
  const time = Date.parse(iso)
  if (Number.isNaN(time)) return iso
  const delta = now - time
  if (delta < MINUTE) return 'just now'
  if (delta < HOUR) return `${Math.floor(delta / MINUTE)} min ago`
  if (delta < DAY) return `${Math.floor(delta / HOUR)} h ago`
  if (delta < 2 * DAY) return 'yesterday'
  if (delta < 7 * DAY) return `${Math.floor(delta / DAY)} days ago`
  return new Date(time).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '–'
  const time = Date.parse(iso)
  if (Number.isNaN(time)) return iso
  return new Date(time).toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export type ConfidenceLevel = 'high' | 'medium' | 'low' | 'insufficient'

export function confidenceLevel(value: number | null | undefined): ConfidenceLevel {
  if (value == null || !Number.isFinite(value)) return 'insufficient'
  if (value >= 0.75) return 'high'
  if (value >= 0.5) return 'medium'
  if (value >= 0.25) return 'low'
  return 'insufficient'
}

export const CONFIDENCE_TEXT: Record<ConfidenceLevel, string> = {
  high: 'High confidence',
  medium: 'Medium confidence',
  low: 'Low confidence',
  insufficient: 'Insufficient confidence',
}

export function importanceText(value: number): string {
  if (value >= 0.95) return 'High perceptual importance'
  if (value >= 0.8) return 'Medium-high perceptual importance'
  if (value >= 0.6) return 'Medium perceptual importance'
  return 'Lower perceptual importance'
}

const UNIT_DISPLAY: Record<string, string> = {
  '0-100': '',
  ratio: '',
  '1 - r': '',
  'log units': '',
  'cents (±)': '¢',
  cents: '¢',
  semitones: 'st',
  'Hz (normalised)': 'Hz',
}

export function displayUnit(unit: string): string {
  return unit in UNIT_DISPLAY ? UNIT_DISPLAY[unit] : unit
}

export function formatUnitValue(value: unknown, rawUnit = ''): string {
  const unit = rawUnit === 'ratio' ? rawUnit : displayUnit(rawUnit)
  if (value == null) return '–'
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return '–'
    const magnitude = Math.abs(value)
    const decimals = magnitude >= 100 ? 0 : magnitude >= 10 ? 1 : magnitude >= 1 ? 2 : 3
    if (unit === 'ratio' && magnitude <= 1) return `${(value * 100).toFixed(0)}%`
    const text = value.toFixed(decimals)
    if (!unit) return text
    return unit === '¢' ? `${text}${unit}` : `${text} ${unit}`
  }
  if (typeof value === 'string') return value || '–'
  if (Array.isArray(value)) {
    if (value.length === 0) return 'none'
    if (value.every((v) => typeof v === 'number')) return value.map((v) => formatUnitValue(v)).join(' – ')
    return `${value.length} items`
  }
  return JSON.stringify(value)
}

export function humanize(key: string): string {
  const text = key
    .replace(/_(hz|db|ms|s|pct|st|oct)$/i, '')
    .replace(/_/g, ' ')
    .replace(/\bf(\d)\b/gi, 'F$1')
    .replace(/\bb(\d)\b/gi, 'B$1')
    .replace(/\bhnr\b/gi, 'HNR')
    .replace(/\bcpps\b/gi, 'CPPS')
    .replace(/\bh1h2\b/gi, 'H1–H2')
    .replace(/\bh2h4\b/gi, 'H2–H4')
    .replace(/\bspr\b/gi, 'SPR')
    .replace(/\bshr\b/gi, 'SHR')
    .replace(/\bcv\b/gi, 'C/V')
    .replace(/\bmidi\b/gi, 'MIDI')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}
