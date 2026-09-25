import type { FeatureBundle, PeakPyramid, SpectrogramData } from '../../api/binary'
import type { Comparison, Recording } from '../../api/types'
import type { AnalysisIndex, ComparisonIndex } from '../../lib/analysis'
import { IDENTITY_MAP, type TimeMap } from '../../lib/timemap'

export interface TrackData {
  recording: Recording
  analysis: AnalysisIndex | null
  features: FeatureBundle | null
  peaks: PeakPyramid | null
  spectrogram: SpectrogramData | null
}

export interface TimelineModel {
  ref: TrackData | null
  take: TrackData | null
  map: TimeMap
  aligned: boolean
  comparison: Comparison | null
  cindex: ComparisonIndex | null
  transposition: number
  duration: number
  spectrogramSide: 'ref' | 'take'
}

export function emptyModel(): TimelineModel {
  return {
    ref: null,
    take: null,
    map: IDENTITY_MAP,
    aligned: true,
    comparison: null,
    cindex: null,
    transposition: 0,
    duration: 10,
    spectrogramSide: 'ref',
  }
}

export function takeTime(model: TimelineModel, t: number): number {
  return model.aligned ? model.map.refToUser(t) : t
}

export function takeToTimeline(model: TimelineModel, u: number): number {
  return model.aligned ? model.map.userToRef(u) : u
}
