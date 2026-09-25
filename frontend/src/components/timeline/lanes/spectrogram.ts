import type { FeatureBundle, SpectrogramData } from '../../../api/binary'
import { formatHz } from '../../../lib/format'
import { takeTime, takeToTimeline, type TimelineModel } from '../model'
import { tOf, xOf, type Viewport } from '../viewport'
import type { CanvasSize } from '../useCanvas'
import { withAlpha } from '../useCanvas'
import { spectrogramLut, type Palette } from './palette'

const images = new WeakMap<SpectrogramData, { theme: string; canvas: HTMLCanvasElement }>()

function imageFor(data: SpectrogramData, theme: string): HTMLCanvasElement {
  const cached = images.get(data)
  if (cached && cached.theme === theme) return cached.canvas
  const canvas = document.createElement('canvas')
  canvas.width = data.frames
  canvas.height = data.bins
  const ctx = canvas.getContext('2d')
  if (ctx) {
    const image = ctx.createImageData(data.frames, data.bins)
    const lut = spectrogramLut(theme)
    const pixels = image.data
    for (let f = 0; f < data.frames; f += 1) {
      for (let b = 0; b < data.bins; b += 1) {
        const value = data.data[f * data.bins + b]
        const offset = ((data.bins - 1 - b) * data.frames + f) * 4
        pixels[offset] = lut[value * 4]
        pixels[offset + 1] = lut[value * 4 + 1]
        pixels[offset + 2] = lut[value * 4 + 2]
        pixels[offset + 3] = 255
      }
    }
    ctx.putImageData(image, 0, 0)
  }
  images.set(data, { theme, canvas })
  return canvas
}

export function yOfHz(data: { fmin: number; fmax: number }, height: number, hz: number): number {
  const ratio = Math.log(hz / data.fmin) / Math.log(data.fmax / data.fmin)
  return height - ratio * height
}

export function hzAtY(data: { fmin: number; fmax: number }, height: number, y: number): number {
  const ratio = (height - y) / height
  return data.fmin * (data.fmax / data.fmin) ** ratio
}

const FORMANT_COLORS = ['#ff7b8a', '#ffd166', '#7fe0ff']

function drawFormants(
  ctx: CanvasRenderingContext2D,
  features: FeatureBundle,
  view: Viewport,
  height: number,
  axis: { fmin: number; fmax: number },
  toTimeline: (u: number) => number,
  fromTimeline: (t: number) => number,
): void {
  const hop = features.hopS
  const conf = features.tracks.formant_conf
  const voiced = features.tracks.voiced
  const i0 = Math.max(0, Math.floor(fromTimeline(view.start) / hop) - 1)
  const i1 = Math.min(features.n - 1, Math.ceil(fromTimeline(view.end) / hop) + 1)
  const stride = Math.max(1, Math.floor((i1 - i0) / (view.width * 1.5)))
  ;['f1_hz', 'f2_hz', 'f3_hz'].forEach((name, k) => {
    const track = features.tracks[name]
    if (!track) return
    ctx.fillStyle = FORMANT_COLORS[k]
    for (let i = i0; i <= i1; i += stride) {
      const hz = track[i]
      if (!(hz > axis.fmin) || hz > axis.fmax) continue
      if (voiced && voiced[i] < 0.5) continue
      const c = conf ? conf[i] : 1
      if (c < 0.2) continue
      ctx.globalAlpha = 0.25 + 0.75 * c
      ctx.fillRect(xOf(view, toTimeline(i * hop)) - 1, yOfHz(axis, height, hz) - 1, 2.2, 2.2)
    }
  })
  ctx.globalAlpha = 1
}

export function drawSpectrogram(
  ctx: CanvasRenderingContext2D,
  size: CanvasSize,
  view: Viewport,
  model: TimelineModel,
  p: Palette,
  showFormants: boolean,
  showImage = true,
): void {
  const { width, height } = size
  const side = model.spectrogramSide
  const track = side === 'take' ? model.take : model.ref
  const data = track?.spectrogram
  ctx.fillStyle = p.surface1
  ctx.fillRect(0, 0, width, height)
  if (!track || !data) return
  const image = imageFor(data, p.theme)
  const mapped = side === 'take' && model.aligned && !model.map.identity
  ctx.imageSmoothingEnabled = true
  if (!showImage) {
    ctx.fillStyle = p.surface2
    ctx.fillRect(0, 0, width, height)
  } else if (!mapped) {
    const toSource = side === 'take' ? (t: number) => takeTime(model, t) : (t: number) => t
    const s0 = toSource(view.start) / data.hopS
    const s1 = toSource(view.end) / data.hopS
    const clipped0 = Math.max(0, s0)
    const clipped1 = Math.min(data.frames, s1)
    if (clipped1 > clipped0) {
      const dx0 = ((clipped0 - s0) / (s1 - s0)) * width
      const dx1 = ((clipped1 - s0) / (s1 - s0)) * width
      ctx.drawImage(image, clipped0, 0, clipped1 - clipped0, data.bins, dx0, 0, dx1 - dx0, height)
    }
  } else {
    const step = width > 1400 ? 2 : 1
    for (let px = 0; px < width; px += step) {
      const u = takeTime(model, tOf(view, px + step / 2))
      const frame = u / data.hopS
      if (frame < 0 || frame >= data.frames) continue
      ctx.drawImage(image, Math.floor(frame), 0, 1, data.bins, px, 0, step, height)
    }
  }
  if (showFormants && track.features) {
    const toTimeline = side === 'take' ? (u: number) => takeToTimeline(model, u) : (u: number) => u
    const fromTimeline = side === 'take' ? (t: number) => takeTime(model, t) : (t: number) => t
    drawFormants(ctx, track.features, view, height, data, toTimeline, fromTimeline)
  }
  ctx.font = `500 9px ${p.mono}`
  ctx.textBaseline = 'middle'
  for (const hz of [100, 200, 500, 1000, 2000, 4000, 8000, 12000]) {
    if (hz <= data.fmin || hz >= data.fmax) continue
    const yy = yOfHz(data, height, hz)
    ctx.fillStyle = withAlpha('#000000', 0.35)
    ctx.fillRect(0, yy - 6, 34, 12)
    ctx.fillStyle = '#e8ebf2'
    ctx.fillText(formatHz(hz).replace(' ', ''), 3, yy)
  }
  ctx.font = `600 9px ${p.font}`
  ctx.fillStyle = side === 'take' ? p.take : p.ref
  ctx.fillText(side === 'take' ? 'TAKE' : 'REFERENCE', width - (side === 'take' ? 36 : 64), 10)
}
