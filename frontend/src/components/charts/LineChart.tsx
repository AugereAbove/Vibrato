import { useMemo, useState } from 'react'
import { useElementSize } from '../timeline/useCanvas'

export interface Series {
  id: string
  label: string
  color: string
  values: (number | null)[]
  confidence?: (number | null)[]
  dashed?: boolean
  width?: number
}

export function LineChart({
  series,
  labels,
  height = 200,
  min = 0,
  max = 100,
  ariaLabel,
  onPointClick,
}: {
  series: Series[]
  labels: string[]
  height?: number
  min?: number
  max?: number
  ariaLabel: string
  onPointClick?: (index: number) => void
}) {
  const [hover, setHover] = useState<number | null>(null)
  const [container, size] = useElementSize<HTMLDivElement>()
  const width = Math.max(320, Math.round(size.width || 640))
  const pad = { left: 34, right: 12, top: 12, bottom: 24 }
  const count = Math.max(labels.length, ...series.map((s) => s.values.length))
  const x = (i: number) =>
    pad.left +
    (count <= 1 ? (width - pad.left - pad.right) / 2 : (i / (count - 1)) * (width - pad.left - pad.right))
  const y = (v: number) =>
    pad.top + (1 - (Math.max(min, Math.min(max, v)) - min) / (max - min)) * (height - pad.top - pad.bottom)
  const grid = useMemo(() => {
    const steps = 4
    return Array.from({ length: steps + 1 }, (_, i) => min + ((max - min) * i) / steps)
  }, [min, max])
  const labelEvery = Math.max(1, Math.ceil(count / 10))
  return (
    <div ref={container} className="line-chart">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={ariaLabel}
        onPointerLeave={() => setHover(null)}
      >
        {grid.map((value) => (
          <g key={value}>
            <line x1={pad.left} x2={width - pad.right} y1={y(value)} y2={y(value)} className="chart-grid" />
            <text x={pad.left - 6} y={y(value) + 3} textAnchor="end" className="chart-axis">
              {Math.round(value)}
            </text>
          </g>
        ))}
        {labels.map((label, i) =>
          i % labelEvery === 0 || i === labels.length - 1 ? (
            <text key={`${label}-${i}`} x={x(i)} y={height - 6} textAnchor="middle" className="chart-axis">
              {label}
            </text>
          ) : null,
        )}
        {series.map((s) => {
          let path = ''
          let open = false
          s.values.forEach((value, i) => {
            if (value == null) {
              open = false
              return
            }
            path += `${open ? 'L' : 'M'}${x(i).toFixed(1)} ${y(value).toFixed(1)}`
            open = true
          })
          return (
            <g key={s.id}>
              <path
                d={path}
                fill="none"
                stroke={s.color}
                strokeWidth={s.width ?? 2}
                strokeDasharray={s.dashed ? '4 4' : undefined}
                strokeLinejoin="round"
                strokeLinecap="round"
                className={s.dashed ? undefined : 'chart-line-draw'}
              />
              {!s.dashed
                ? s.values.map((value, i) =>
                    value == null ? null : (
                      <circle
                        key={i}
                        cx={x(i)}
                        cy={y(value)}
                        r={hover === i ? 4.5 : 3}
                        fill={(s.confidence?.[i] ?? 1) < 0.5 ? 'var(--surface-1)' : s.color}
                        stroke={s.color}
                        strokeWidth={1.5}
                      />
                    ),
                  )
                : null}
            </g>
          )
        })}
        {Array.from({ length: count }, (_, i) => (
          <rect
            key={i}
            x={x(i) - (width - pad.left - pad.right) / Math.max(1, count - 1) / 2}
            y={0}
            width={(width - pad.left - pad.right) / Math.max(1, count - 1)}
            height={height}
            fill="transparent"
            onPointerEnter={() => setHover(i)}
            onClick={() => onPointClick?.(i)}
            style={{ cursor: onPointClick ? 'pointer' : 'default' }}
          />
        ))}
        {hover !== null ? (
          <line x1={x(hover)} x2={x(hover)} y1={pad.top} y2={height - pad.bottom} className="chart-hover" />
        ) : null}
      </svg>
      {hover !== null ? (
        <div className="chart-tooltip">
          <strong>{labels[hover]}</strong>
          {series
            .filter((s) => !s.dashed)
            .map((s) => (
              <span key={s.id}>
                <span className="legend-dot" style={{ background: s.color }} /> {s.label}:{' '}
                {s.values[hover] == null ? '–' : s.values[hover]!.toFixed(1)}
                {(s.confidence?.[hover] ?? 1) < 0.5 ? ' (low confidence)' : ''}
              </span>
            ))}
        </div>
      ) : null}
    </div>
  )
}

export function Sparkline({
  values,
  width = 90,
  height = 22,
  color = 'var(--accent)',
}: {
  values: (number | null)[]
  width?: number
  height?: number
  color?: string
}) {
  const clean = values.filter((v): v is number => v != null)
  if (clean.length === 0) return <span className="faint tiny">–</span>
  const lo = Math.min(...clean, 50)
  const hi = Math.max(...clean, 100)
  const x = (i: number) => (values.length <= 1 ? width / 2 : (i / (values.length - 1)) * (width - 4) + 2)
  const y = (v: number) => height - 2 - ((v - lo) / Math.max(1, hi - lo)) * (height - 4)
  let path = ''
  let open = false
  values.forEach((v, i) => {
    if (v == null) {
      open = false
      return
    }
    path += `${open ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`
    open = true
  })
  const last = values.length - 1
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden className="sparkline">
      <path d={path} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />
      {values[last] != null ? (
        <circle cx={x(last)} cy={y(values[last] as number)} r={2.2} fill={color} />
      ) : null}
    </svg>
  )
}
