import { cssVar } from '../useCanvas'

export interface Palette {
  theme: string
  text1: string
  text2: string
  text3: string
  grid: string
  gridStrong: string
  surface1: string
  surface2: string
  surface3: string
  border: string
  ref: string
  refSoft: string
  take: string
  takeSoft: string
  synthetic: string
  accent: string
  accentSoft: string
  good: string
  warn: string
  bad: string
  info: string
  pianoBlack: string
  heat: string[]
  categories: Record<string, string>
  font: string
  mono: string
}

let cached: Palette | null = null

export function palette(theme: string): Palette {
  if (cached && cached.theme === theme) return cached
  const categories: Record<string, string> = {}
  for (const name of [
    'pitch',
    'timing',
    'vowel',
    'vibrato',
    'dynamics',
    'phonation',
    'articulation',
    'breath',
    'timbre',
    'confidence',
  ]) {
    categories[name] = cssVar(`--cat-${name}`)
  }
  cached = {
    theme,
    text1: cssVar('--text-1'),
    text2: cssVar('--text-2'),
    text3: cssVar('--text-3'),
    grid: cssVar('--grid'),
    gridStrong: cssVar('--grid-strong'),
    surface1: cssVar('--surface-1'),
    surface2: cssVar('--surface-2'),
    surface3: cssVar('--surface-3'),
    border: cssVar('--border'),
    ref: cssVar('--ref'),
    refSoft: cssVar('--ref-soft'),
    take: cssVar('--take'),
    takeSoft: cssVar('--take-soft'),
    synthetic: cssVar('--synthetic'),
    accent: cssVar('--accent'),
    accentSoft: cssVar('--accent-soft'),
    good: cssVar('--good'),
    warn: cssVar('--warn'),
    bad: cssVar('--bad'),
    info: cssVar('--info'),
    pianoBlack: cssVar('--piano-black'),
    heat: [
      cssVar('--heat-0'),
      cssVar('--heat-1'),
      cssVar('--heat-2'),
      cssVar('--heat-3'),
      cssVar('--heat-4'),
    ],
    categories,
    font: cssVar('--font-sans', 'sans-serif'),
    mono: cssVar('--font-mono', 'monospace'),
  }
  return cached
}

export function resetPalette(): void {
  cached = null
}

function parseColor(color: string): [number, number, number, number] {
  const value = color.trim()
  if (value.startsWith('#')) {
    const hex = value.slice(1)
    const full =
      hex.length === 3
        ? hex
            .split('')
            .map((c) => c + c)
            .join('')
        : hex
    return [parseInt(full.slice(0, 2), 16), parseInt(full.slice(2, 4), 16), parseInt(full.slice(4, 6), 16), 1]
  }
  const match = value.match(/rgba?\(([^)]+)\)/)
  if (match) {
    const parts = match[1].split(',').map((v) => parseFloat(v))
    return [parts[0], parts[1], parts[2], parts[3] ?? 1]
  }
  return [128, 128, 128, 1]
}

export function heatColor(p: Palette, value: number): string {
  const v = Math.max(0, Math.min(1, value))
  if (v <= 0.02) return p.heat[0]
  const stops = p.heat.slice(1).map(parseColor)
  const position = v * (stops.length - 1)
  const i = Math.min(stops.length - 2, Math.floor(position))
  const f = position - i
  const a = stops[i]
  const b = stops[i + 1]
  const mix = (k: number) => Math.round(a[k] + (b[k] - a[k]) * f)
  return `rgba(${mix(0)}, ${mix(1)}, ${mix(2)}, ${0.35 + 0.65 * v})`
}

export function hatch(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  color: string,
  gap = 5,
): void {
  ctx.save()
  ctx.beginPath()
  ctx.rect(x, y, w, h)
  ctx.clip()
  ctx.strokeStyle = color
  ctx.lineWidth = 1
  ctx.beginPath()
  for (let i = -h; i < w + h; i += gap) {
    ctx.moveTo(x + i, y + h)
    ctx.lineTo(x + i + h, y)
  }
  ctx.stroke()
  ctx.restore()
}

export function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
): void {
  const radius = Math.max(0, Math.min(r, w / 2, h / 2))
  ctx.beginPath()
  ctx.moveTo(x + radius, y)
  ctx.arcTo(x + w, y, x + w, y + h, radius)
  ctx.arcTo(x + w, y + h, x, y + h, radius)
  ctx.arcTo(x, y + h, x, y, radius)
  ctx.arcTo(x, y, x + w, y, radius)
  ctx.closePath()
}

const SPECTRO_STOPS: Record<string, [number, number, number][]> = {
  dark: [
    [8, 9, 14],
    [36, 22, 70],
    [98, 30, 110],
    [170, 50, 100],
    [232, 96, 68],
    [252, 178, 76],
    [252, 244, 190],
  ],
  light: [
    [250, 250, 252],
    [214, 222, 245],
    [150, 170, 230],
    [96, 102, 200],
    [110, 50, 150],
    [70, 20, 80],
    [20, 8, 30],
  ],
}

const lutCache = new Map<string, Uint8ClampedArray>()

export function spectrogramLut(theme: string): Uint8ClampedArray {
  const key = theme === 'light' ? 'light' : 'dark'
  const existing = lutCache.get(key)
  if (existing) return existing
  const stops = SPECTRO_STOPS[key]
  const lut = new Uint8ClampedArray(256 * 4)
  for (let i = 0; i < 256; i += 1) {
    const position = (i / 255) * (stops.length - 1)
    const j = Math.min(stops.length - 2, Math.floor(position))
    const f = position - j
    for (let k = 0; k < 3; k += 1) lut[i * 4 + k] = stops[j][k] + (stops[j + 1][k] - stops[j][k]) * f
    lut[i * 4 + 3] = 255
  }
  lutCache.set(key, lut)
  return lut
}
