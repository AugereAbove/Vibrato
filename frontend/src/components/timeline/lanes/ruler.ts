import type { Bookmark, Segment, SongSection } from '../../../api/types'
import { formatTime } from '../../../lib/format'
import type { Region } from '../../../state/workspace'
import { ticks, xOf, type Viewport } from '../viewport'
import type { CanvasSize } from '../useCanvas'
import { roundRect, type Palette } from './palette'

export interface RulerExtras {
  sections: (SongSection | Segment)[]
  bookmarks: Bookmark[]
  loop: Region | null
  loopEnabled: boolean
  region: Region | null
}

const BOOKMARK_COLORS: Record<string, string> = {
  amber: '#f2b85b',
  red: '#ff5a6e',
  green: '#47c78c',
  blue: '#52b6ff',
  violet: '#9a8cff',
}

export function bookmarkColor(name: string): string {
  return BOOKMARK_COLORS[name] ?? BOOKMARK_COLORS.amber
}

export function drawRuler(
  ctx: CanvasRenderingContext2D,
  size: CanvasSize,
  view: Viewport,
  p: Palette,
  extras: RulerExtras,
): void {
  const { width, height } = size
  const { major, minor, step } = ticks(view)
  const decimals = step >= 1 ? 0 : step >= 0.1 ? 1 : 2
  const sectionBand = 11
  ctx.font = `500 10px ${p.font}`
  ctx.textBaseline = 'middle'
  extras.sections.forEach((section, index) => {
    const x0 = xOf(view, section.start_s)
    const x1 = xOf(view, section.end_s)
    if (x1 < 0 || x0 > width) return
    ctx.fillStyle = index % 2 === 0 ? p.accentSoft : p.surface3
    roundRect(ctx, x0 + 0.5, 1, Math.max(2, x1 - x0 - 1), sectionBand, 3)
    ctx.fill()
    if (x1 - x0 > 40) {
      ctx.fillStyle = p.text2
      ctx.save()
      ctx.beginPath()
      ctx.rect(Math.max(0, x0), 0, Math.min(width, x1) - Math.max(0, x0), sectionBand + 2)
      ctx.clip()
      ctx.fillText(section.label, Math.max(4, x0 + 5), 1 + sectionBand / 2)
      ctx.restore()
    }
  })
  const top = sectionBand + 3
  ctx.strokeStyle = p.grid
  ctx.lineWidth = 1
  ctx.beginPath()
  for (const t of minor) {
    const x = Math.round(xOf(view, t)) + 0.5
    ctx.moveTo(x, height - 5)
    ctx.lineTo(x, height)
  }
  ctx.stroke()
  ctx.strokeStyle = p.gridStrong
  ctx.beginPath()
  for (const t of major) {
    const x = Math.round(xOf(view, t)) + 0.5
    ctx.moveTo(x, height - 10)
    ctx.lineTo(x, height)
  }
  ctx.stroke()
  ctx.fillStyle = p.text3
  ctx.font = `500 10px ${p.mono}`
  ctx.textBaseline = 'alphabetic'
  for (const t of major) {
    if (t < 0) continue
    const x = xOf(view, t)
    if (x < -40 || x > width + 40) continue
    ctx.fillText(formatTime(t, decimals), x + 4, height - 4)
  }
  if (extras.loop) {
    const x0 = xOf(view, extras.loop.start)
    const x1 = xOf(view, extras.loop.end)
    ctx.fillStyle = extras.loopEnabled ? p.accent : p.text3
    ctx.globalAlpha = extras.loopEnabled ? 0.9 : 0.45
    roundRect(ctx, x0, top, Math.max(2, x1 - x0), 4, 2)
    ctx.fill()
    ctx.globalAlpha = 1
  }
  for (const bookmark of extras.bookmarks) {
    const x = xOf(view, bookmark.start_s)
    if (x < -10 || x > width + 10) continue
    const color = bookmarkColor(bookmark.color)
    if (bookmark.end_s != null) {
      const x1 = xOf(view, bookmark.end_s)
      ctx.fillStyle = color
      ctx.globalAlpha = 0.18
      ctx.fillRect(x, top, x1 - x, height - top)
      ctx.globalAlpha = 1
    }
    ctx.fillStyle = color
    ctx.beginPath()
    ctx.moveTo(x, top)
    ctx.lineTo(x + 7, top + 4)
    ctx.lineTo(x, top + 8)
    ctx.closePath()
    ctx.fill()
    ctx.fillRect(x, top, 1.5, height - top)
  }
}

export function hitBookmark(bookmarks: Bookmark[], view: Viewport, x: number): Bookmark | null {
  for (const bookmark of bookmarks) {
    if (Math.abs(xOf(view, bookmark.start_s) - x) <= 6) return bookmark
  }
  return null
}
