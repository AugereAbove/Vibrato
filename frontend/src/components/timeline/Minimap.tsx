import { useCallback, useRef } from 'react'
import type { HeatmapView } from '../../api/types'
import { useWorkspace } from '../../state/workspace'
import type { TimelineModel } from './model'
import { heatColor, palette } from './lanes/palette'
import { drawMiniWave } from './lanes/waveform'
import { useCanvasDraw, type CanvasSize } from './useCanvas'
import { setView } from './viewport'

export function Minimap({
  model,
  theme,
  width,
  heat,
}: {
  model: TimelineModel
  theme: string
  width: number
  heat: HeatmapView | null
}) {
  const view = useWorkspace((s) => s.view)
  const duration = Math.max(0.1, model.duration)
  const height = 30
  const drag = useRef<{ offset: number } | null>(null)
  const draw = useCallback(
    (ctx: CanvasRenderingContext2D, size: CanvasSize) => {
      const p = palette(theme)
      const peaks = model.ref?.peaks ?? model.take?.peaks
      if (peaks)
        drawMiniWave(ctx, { ...size, height: size.height - 5 }, peaks, duration, model.ref ? p.ref : p.take)
      if (heat) {
        const rows = Object.entries(heat.rows).filter(([row]) => row !== 'confidence')
        heat.columns.forEach((column, c) => {
          let value = 0
          for (const [, cells] of rows) value = Math.max(value, cells[c]?.value ?? 0)
          const x0 = (column.start_s / duration) * size.width
          const x1 = (column.end_s / duration) * size.width
          ctx.fillStyle = heatColor(p, value)
          ctx.fillRect(x0, size.height - 4, Math.max(1, x1 - x0 - 0.5), 4)
        })
      }
    },
    [model, theme, heat, duration],
  )
  const canvas = useCanvasDraw(width, height, draw)
  const left = (view.start / duration) * width
  const windowWidth = Math.max(6, ((view.end - view.start) / duration) * width)

  const timeAt = (clientX: number, element: HTMLElement) => {
    const rect = element.getBoundingClientRect()
    return ((clientX - rect.left) / rect.width) * duration
  }

  return (
    <div
      className="minimap"
      style={{ width, height }}
      onPointerDown={(event) => {
        const element = event.currentTarget
        element.setPointerCapture(event.pointerId)
        const t = timeAt(event.clientX, element)
        const spanS = view.end - view.start
        if (t >= view.start && t <= view.end) drag.current = { offset: t - view.start }
        else {
          drag.current = { offset: spanS / 2 }
          setView({ start: t - spanS / 2, end: t + spanS / 2 })
        }
      }}
      onPointerMove={(event) => {
        if (!drag.current) return
        const t = timeAt(event.clientX, event.currentTarget)
        const { view: current } = useWorkspace.getState()
        const spanS = current.end - current.start
        setView({ start: t - drag.current.offset, end: t - drag.current.offset + spanS })
      }}
      onPointerUp={() => {
        drag.current = null
      }}
      role="scrollbar"
      aria-label="Timeline overview"
      aria-orientation="horizontal"
      aria-valuemin={0}
      aria-valuemax={Math.round(duration)}
      aria-valuenow={Math.round(view.start)}
    >
      <canvas ref={canvas} className="minimap-canvas" style={{ width, height }} />
      <div className="minimap-window" style={{ transform: `translateX(${left}px)`, width: windowWidth }} />
    </div>
  )
}
