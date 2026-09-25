import type { HeatCell, HeatmapView } from '../../../api/types'
import { xOf, type Viewport } from '../viewport'
import type { CanvasSize } from '../useCanvas'
import { hatch, heatColor, type Palette } from './palette'

export const MASK_CONFIDENCE = 0.45

export function drawHeatmapLane(
  ctx: CanvasRenderingContext2D,
  size: CanvasSize,
  view: Viewport,
  heatmap: HeatmapView | null,
  rows: string[],
  p: Palette,
  mask: boolean,
  selected: { row: string; column: number } | null,
): void {
  const { width, height } = size
  if (!heatmap || rows.length === 0) return
  const rowHeight = height / rows.length
  rows.forEach((row, r) => {
    const cells = heatmap.rows[row] ?? []
    const top = r * rowHeight
    heatmap.columns.forEach((column, c) => {
      const x0 = xOf(view, column.start_s)
      const x1 = xOf(view, column.end_s)
      if (x1 < 0 || x0 > width) return
      const cell = cells[c]
      const w = Math.max(1, x1 - x0 - 1)
      if (!cell) {
        ctx.fillStyle = p.heat[0]
        ctx.fillRect(x0, top + 1, w, rowHeight - 2)
        return
      }
      if (row === 'confidence') {
        const value = Math.max(0, Math.min(1, cell.value))
        ctx.fillStyle = `rgba(128, 138, 160, ${0.12 + 0.55 * value})`
        ctx.fillRect(x0, top + 1, w, rowHeight - 2)
        if (value < MASK_CONFIDENCE) hatch(ctx, x0, top + 1, w, rowHeight - 2, 'rgba(255, 90, 110, 0.55)', 4)
        return
      }
      const low = cell.confidence < MASK_CONFIDENCE
      ctx.fillStyle = heatColor(p, mask && low ? cell.value * 0.35 : cell.value)
      ctx.fillRect(x0, top + 1, w, rowHeight - 2)
      if (mask && low) hatch(ctx, x0, top + 1, w, rowHeight - 2, 'rgba(128, 138, 160, 0.45)', 4)
      if (selected && selected.row === row && selected.column === c) {
        ctx.strokeStyle = p.accent
        ctx.lineWidth = 2
        ctx.strokeRect(x0 + 1, top + 1.5, w - 2, rowHeight - 3)
      }
    })
  })
}

export function hitHeatmap(
  view: Viewport,
  heatmap: HeatmapView | null,
  rows: string[],
  x: number,
  y: number,
  height: number,
): { row: string; column: number; cell: HeatCell | null; start: number; end: number } | null {
  if (!heatmap || rows.length === 0) return null
  const r = Math.min(rows.length - 1, Math.max(0, Math.floor((y / height) * rows.length)))
  for (let c = 0; c < heatmap.columns.length; c += 1) {
    const column = heatmap.columns[c]
    if (x >= xOf(view, column.start_s) && x <= xOf(view, column.end_s)) {
      return {
        row: rows[r],
        column: c,
        cell: heatmap.rows[rows[r]]?.[c] ?? null,
        start: column.start_s,
        end: column.end_s,
      }
    }
  }
  return null
}
