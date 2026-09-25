import { useMemo } from 'react'
import type { Comparison, HeatCell } from '../../../api/types'
import { engine } from '../../../audio/engine'
import { fitRange } from '../../../components/timeline/viewport'
import { Segmented, Switch } from '../../../components/ui/Controls'
import { Tooltip } from '../../../components/ui/Tooltip'
import { categoryLabel } from '../../../lib/categories'
import { formatPercent, formatTime } from '../../../lib/format'
import { setUi, useUi } from '../../../state/ui'
import { select, useWorkspace } from '../../../state/workspace'
import type { AnalysisIndex, ComparisonIndex } from '../../../lib/analysis'
import { heatColor, palette } from '../../../components/timeline/lanes/palette'
import { useResolvedTheme } from '../../../state/prefs'

function cellStyle(cell: HeatCell | null, row: string, mask: boolean, theme: string): React.CSSProperties {
  if (!cell) return {}
  if (row === 'confidence') {
    return { ['--cell' as string]: `rgba(128, 138, 160, ${0.12 + 0.6 * cell.value})` }
  }
  const low = cell.confidence < 0.45
  const value = mask && low ? cell.value * 0.35 : cell.value
  return { ['--cell' as string]: heatColor(palette(theme), value) }
}

export function HeatmapPanel({
  comparison,
  refIndex,
  cindex,
}: {
  comparison: Comparison
  refIndex: AnalysisIndex | null
  cindex: ComparisonIndex | null
}) {
  const view = useUi((s) => s.heatmapView)
  const mask = useUi((s) => s.heatmapMask)
  const selection = useWorkspace((s) => s.selection)
  const theme = useResolvedTheme()
  const heat = comparison.heatmap.views[view]
  const rows = comparison.heatmap.rows
  const template = useMemo(() => {
    const total = heat.columns.reduce((sum, c) => sum + Math.max(0.05, c.end_s - c.start_s), 0)
    return heat.columns
      .map(
        (c) =>
          `minmax(${view === 'fine' ? 6 : 18}px, ${(Math.max(0.05, c.end_s - c.start_s) / total) * 100}fr)`,
      )
      .join(' ')
  }, [heat, view])

  const choose = (cell: HeatCell | null, start: number, end: number) => {
    const segment = cell?.segment_id ? refIndex?.segments.get(cell.segment_id) : null
    if (segment) {
      select({
        kind: 'segment',
        level: segment.level,
        refId: segment.id,
        takeId: cindex?.refToUser.get(segment.id) ?? null,
        start: segment.start_s,
        end: segment.end_s,
        label: segment.label,
      })
    }
    const s = cell?.ref_start ?? start
    const e = cell?.ref_end ?? end
    useWorkspace.setState({ region: { start: s, end: e } })
    fitRange(s, e, 0.5)
    engine.seek(s)
  }

  return (
    <div className="heatmap-panel">
      <div className="panel-toolbar">
        <Segmented
          size="sm"
          ariaLabel="Heatmap resolution"
          value={view}
          onChange={(value) => setUi({ heatmapView: value })}
          options={[
            { value: 'phrase', label: 'Phrases' },
            { value: 'word', label: 'Words' },
            { value: 'fine', label: 'Fine time' },
          ]}
        />
        <Switch
          checked={mask}
          onChange={(value) => setUi({ heatmapMask: value })}
          label="Mask low confidence"
        />
        <span className="spacer" />
        <div className="heat-legend" aria-hidden>
          <span>close</span>
          <span className="heat-legend-ramp" />
          <span>very different</span>
          <span className="heat-legend-hatch" />
          <span>uncertain</span>
        </div>
      </div>
      <div className="heatmap-grid" role="grid" aria-label="Differences by category and time">
        {rows.map((row) => (
          <div key={row} className="heatmap-row" role="row">
            <div className="heatmap-label" role="rowheader">
              <span className="cat-dot" style={{ background: `var(--cat-${row})` }} />
              {row === 'confidence' ? 'Confidence' : categoryLabel(row)}
            </div>
            <div className="heatmap-cells" style={{ gridTemplateColumns: template }}>
              {heat.columns.map((column, c) => {
                const cell = heat.rows[row]?.[c] ?? null
                const low = cell ? (row === 'confidence' ? cell.value < 0.45 : cell.confidence < 0.45) : false
                const selected =
                  selection?.kind === 'segment' && cell?.segment_id && cell.segment_id === selection.refId
                return (
                  <Tooltip
                    key={column.id}
                    block
                    content={
                      <div className="stack" style={{ gap: 2 }}>
                        <strong>
                          {row === 'confidence' ? 'Confidence' : categoryLabel(row)} · {column.label}
                        </strong>
                        {cell ? (
                          row === 'confidence' ? (
                            <span>Measurement confidence {formatPercent(cell.value)}</span>
                          ) : (
                            <>
                              <span>
                                {cell.label}: {cell.direction} (z = {cell.z?.toFixed(1)})
                              </span>
                              <span className="faint">
                                {cell.count} measurements · confidence {formatPercent(cell.confidence)}
                              </span>
                            </>
                          )
                        ) : (
                          <span className="faint">Nothing measured here</span>
                        )}
                        <span className="faint">
                          {formatTime(column.start_s)} – {formatTime(column.end_s)}
                        </span>
                      </div>
                    }
                  >
                    <button
                      type="button"
                      role="gridcell"
                      className={`heat-cell${cell ? '' : ' is-empty'}${low && mask ? ' is-masked' : ''}${selected ? ' is-selected' : ''}`}
                      style={cellStyle(cell, row, mask, theme)}
                      aria-label={`${categoryLabel(row)} ${column.label}: ${cell ? `${Math.round(cell.value * 100)}%` : 'no data'}`}
                      onClick={() => choose(cell, column.start_s, column.end_s)}
                    />
                  </Tooltip>
                )
              })}
            </div>
          </div>
        ))}
        {view !== 'fine' ? (
          <div className="heatmap-row heatmap-axis" aria-hidden>
            <div className="heatmap-label" />
            <div className="heatmap-cells" style={{ gridTemplateColumns: template }}>
              {heat.columns.map((column) => (
                <span key={column.id} className="heat-column-label truncate">
                  {column.label}
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
