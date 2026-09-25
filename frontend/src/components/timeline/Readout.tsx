import { segmentAt } from '../../lib/analysis'
import { formatSigned, formatTime } from '../../lib/format'
import { describeHz, hzToMidi } from '../../lib/music'
import { useWorkspace } from '../../state/workspace'
import { sampleTrack } from './lanes/curves'
import { takeTime, type TimelineModel } from './model'

export function HoverReadout({ model }: { model: TimelineModel }) {
  const hover = useWorkspace((s) => s.hover)
  const selection = useWorkspace((s) => s.selection)
  const region = useWorkspace((s) => s.region)
  if (hover === null) {
    if (region) {
      return (
        <div className="readout">
          <span className="readout-label">Selection</span>
          <span className="num">
            {formatTime(region.start)} – {formatTime(region.end)}
          </span>
          <span className="faint num">{(region.end - region.start).toFixed(2)} s</span>
        </div>
      )
    }
    if (selection) {
      return (
        <div className="readout">
          <span className="readout-label">Selected</span>
          <span className="truncate">{selection.label}</span>
          <span className="faint num">{formatTime(selection.start)}</span>
        </div>
      )
    }
    return (
      <div className="readout faint">
        Hover the timeline to read values · drag to select · right-click for actions
      </div>
    )
  }
  const u = takeTime(model, hover)
  const refHz = sampleTrack(model.ref?.features, 'f0_hz', hover)
  const takeHz = sampleTrack(model.take?.features, 'f0_hz', u)
  const refLevel = sampleTrack(model.ref?.features, 'level_rel_db', hover)
  const takeLevel = sampleTrack(model.take?.features, 'level_rel_db', u)
  const cents =
    refHz && takeHz && refHz > 30 && takeHz > 30
      ? (hzToMidi(takeHz) - model.transposition - hzToMidi(refHz)) * 100
      : null
  const word = model.ref?.analysis ? segmentAt(model.ref.analysis.byLevel.word, hover) : null
  const confidence = model.map.identity ? null : model.map.confidenceAt(hover)
  return (
    <div className="readout" aria-live="off">
      <span className="num readout-time">{formatTime(hover, 2)}</span>
      {word ? <span className="readout-word">“{word.label}”</span> : null}
      {refHz && refHz > 30 ? (
        <span>
          <span className="ref-text">Ref</span> <span className="num">{describeHz(refHz)}</span>
        </span>
      ) : null}
      {model.take && takeHz && takeHz > 30 ? (
        <span>
          <span className="take-text">Take</span> <span className="num">{describeHz(takeHz)}</span>
        </span>
      ) : null}
      {cents !== null ? <span className="num">Δ {formatSigned(cents, 0, '¢')}</span> : null}
      {refLevel !== null && takeLevel !== null && model.take ? (
        <span className="num faint">level Δ {formatSigned(takeLevel - refLevel, 1, 'dB')}</span>
      ) : null}
      {confidence !== null ? <span className="num faint">align {(confidence * 100).toFixed(0)}%</span> : null}
    </div>
  )
}
