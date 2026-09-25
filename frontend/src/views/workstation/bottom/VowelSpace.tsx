import { useMemo, useState } from 'react'
import { useElementSize } from '../../../components/timeline/useCanvas'
import { numberValue, resultFor, type AnalysisIndex, type ComparisonIndex } from '../../../lib/analysis'
import { EmptyState } from '../../../components/ui/Feedback'
import { select } from '../../../state/workspace'
import type { ViewMode } from '../../../state/prefs'

interface VowelPoint {
  id: string
  label: string
  vowel: string
  f1: number
  f2: number
  f1s: number | null
  f2s: number | null
  f1e: number | null
  f2e: number | null
  confidence: number
  start: number
  end: number
}

function points(index: AnalysisIndex | null): VowelPoint[] {
  if (!index) return []
  const out: VowelPoint[] = []
  for (const syllable of index.byLevel.syllable) {
    const result = resultFor(index, 'vowels', syllable.id)
    const f1 = numberValue(result, 'f1_norm_mid')
    const f2 = numberValue(result, 'f2_norm_mid')
    if (f1 === null || f2 === null || !result) continue
    const vowel = typeof result.values.vowel === 'string' ? result.values.vowel : ''
    out.push({
      id: syllable.id,
      label: syllable.label,
      vowel,
      f1,
      f2,
      f1s: numberValue(result, 'f1_norm_start'),
      f2s: numberValue(result, 'f2_norm_start'),
      f1e: numberValue(result, 'f1_norm_end'),
      f2e: numberValue(result, 'f2_norm_end'),
      confidence: result.confidence,
      start: syllable.start_s,
      end: syllable.end_s,
    })
  }
  return out
}

export function VowelSpace({
  refIndex,
  takeIndex,
  cindex,
  mode,
}: {
  refIndex: AnalysisIndex | null
  takeIndex: AnalysisIndex | null
  cindex: ComparisonIndex | null
  mode: ViewMode
}) {
  const refPoints = useMemo(() => points(refIndex), [refIndex])
  const takePoints = useMemo(() => points(takeIndex), [takeIndex])
  const [hover, setHover] = useState<string | null>(null)
  const [box, size] = useElementSize<HTMLDivElement>()
  const all = [...refPoints, ...takePoints]
  if (all.length === 0) {
    return (
      <EmptyState compact icon="vowel" title="No reliable vowel measurements">
        Formants could not be measured confidently on sustained vowels. High notes, breathy tone and short
        vowels make formant tracking unreliable.
      </EmptyState>
    )
  }
  const f1s = all.map((p) => p.f1)
  const f2s = all.map((p) => p.f2)
  const pad = (lo: number, hi: number) => [lo - (hi - lo) * 0.12 - 20, hi + (hi - lo) * 0.12 + 20]
  const [f1lo, f1hi] = pad(Math.min(...f1s), Math.max(...f1s))
  const [f2lo, f2hi] = pad(Math.min(...f2s), Math.max(...f2s))
  const W = Math.max(320, Math.round(size.width || 520))
  const H = Math.round(Math.min(340, Math.max(220, W * 0.56)))
  const M = 36
  const x = (f2: number) => M + ((f2hi - f2) / (f2hi - f2lo)) * (W - 2 * M)
  const y = (f1: number) => M / 2 + ((f1 - f1lo) / (f1hi - f1lo)) * (H - M * 1.5)
  const takeById = new Map(takePoints.map((p) => [p.id, p]))
  const pairs = refPoints
    .map((r) => {
      const takeId = cindex?.refToUser.get(r.id)
      const t = takeId ? takeById.get(takeId) : undefined
      return t ? { r, t } : null
    })
    .filter((p): p is { r: VowelPoint; t: VowelPoint } => p !== null)
  const choose = (point: VowelPoint, side: 'ref' | 'take') => {
    const refId = side === 'ref' ? point.id : (cindex?.userToRef.get(point.id) ?? null)
    const takeId = side === 'take' ? point.id : (cindex?.refToUser.get(point.id) ?? null)
    const refSegment = refId ? refIndex?.segments.get(refId) : null
    select({
      kind: 'segment',
      level: 'syllable',
      refId,
      takeId,
      start: refSegment?.start_s ?? point.start,
      end: refSegment?.end_s ?? point.end,
      label: point.label,
    })
  }
  const gridF1 = [200, 300, 400, 500, 600, 700, 800, 900, 1000].filter((v) => v > f1lo && v < f1hi)
  const gridF2 = [800, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2400, 2600].filter(
    (v) => v > f2lo && v < f2hi,
  )
  return (
    <div className="vowel-space">
      <div ref={box} style={{ minWidth: 0 }}>
        <svg
          width={W}
          height={H}
          viewBox={`0 0 ${W} ${H}`}
          className="vowel-chart"
          role="img"
          aria-label="Vowel space: normalised F2 horizontally (front at left), F1 vertically (open at the bottom)"
        >
          {gridF1.map((v) => (
            <g key={`f1-${v}`}>
              <line x1={M} x2={W - M} y1={y(v)} y2={y(v)} className="chart-grid" />
              <text x={4} y={y(v) + 3} className="chart-axis">
                {v}
              </text>
            </g>
          ))}
          {gridF2.map((v) => (
            <g key={`f2-${v}`}>
              <line x1={x(v)} x2={x(v)} y1={M / 2} y2={H - M} className="chart-grid" />
              <text x={x(v)} y={H - M + 14} className="chart-axis" textAnchor="middle">
                {v}
              </text>
            </g>
          ))}
          <text x={W / 2} y={H - 4} className="chart-title" textAnchor="middle">
            F2 (normalised Hz) — front ← → back
          </text>
          <text x={12} y={M / 2 - 4} className="chart-title">
            F1 ↓ open
          </text>
          {pairs.map(({ r, t }) => (
            <line
              key={`pair-${r.id}`}
              x1={x(r.f2)}
              y1={y(r.f1)}
              x2={x(t.f2)}
              y2={y(t.f1)}
              className={`vowel-link${hover === r.id || hover === t.id ? ' is-hover' : ''}`}
            />
          ))}
          {mode !== 'coach'
            ? [
                ...refPoints.map((p) => ({ p, side: 'ref' })),
                ...takePoints.map((p) => ({ p, side: 'take' })),
              ].map(({ p, side }) =>
                p.f1s !== null && p.f2s !== null && p.f1e !== null && p.f2e !== null ? (
                  <line
                    key={`traj-${side}-${p.id}`}
                    x1={x(p.f2s)}
                    y1={y(p.f1s)}
                    x2={x(p.f2e)}
                    y2={y(p.f1e)}
                    className={`vowel-trajectory ${side}`}
                    markerEnd={`url(#arrow-${side})`}
                  />
                ) : null,
              )
            : null}
          <defs>
            <marker
              id="arrow-ref"
              viewBox="0 0 6 6"
              refX="5"
              refY="3"
              markerWidth="5"
              markerHeight="5"
              orient="auto"
            >
              <path d="M0 0L6 3L0 6z" className="arrow-ref" />
            </marker>
            <marker
              id="arrow-take"
              viewBox="0 0 6 6"
              refX="5"
              refY="3"
              markerWidth="5"
              markerHeight="5"
              orient="auto"
            >
              <path d="M0 0L6 3L0 6z" className="arrow-take" />
            </marker>
          </defs>
          {refPoints.map((p) => (
            <g
              key={`ref-${p.id}`}
              className="vowel-point ref"
              transform={`translate(${x(p.f2)}, ${y(p.f1)})`}
              onPointerEnter={() => setHover(p.id)}
              onPointerLeave={() => setHover(null)}
              onClick={() => choose(p, 'ref')}
              style={{ opacity: 0.4 + 0.6 * p.confidence }}
            >
              <circle r={5.5} />
              {hover === p.id || refPoints.length <= 12 ? (
                <text y={-9} textAnchor="middle">
                  {p.vowel ? `${p.label} /${p.vowel}/` : p.label}
                </text>
              ) : null}
            </g>
          ))}
          {takePoints.map((p) => (
            <g
              key={`take-${p.id}`}
              className="vowel-point take"
              transform={`translate(${x(p.f2)}, ${y(p.f1)})`}
              onPointerEnter={() => setHover(p.id)}
              onPointerLeave={() => setHover(null)}
              onClick={() => choose(p, 'take')}
              style={{ opacity: 0.4 + 0.6 * p.confidence }}
            >
              <rect x={-4.5} y={-4.5} width={9} height={9} rx={2} />
            </g>
          ))}
        </svg>
      </div>
      <div className="vowel-legend small">
        <span>
          <span className="legend-dot ref" /> Reference vowels
        </span>
        <span>
          <span className="legend-square take" /> Your vowels
        </span>
        <p className="faint tiny">
          Formants are normalised for vocal-tract size (log-mean normalisation), so only articulation
          differences remain. Lines join matching syllables. Faint points are low confidence.
        </p>
      </div>
    </div>
  )
}
