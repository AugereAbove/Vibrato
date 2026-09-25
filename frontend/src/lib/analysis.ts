import type {
  AnalysisEvent,
  AnalysisPayload,
  AnalysisResult,
  Comparison,
  Finding,
  MetricComparison,
  Segment,
  SegmentLevel,
} from '../api/types'

export interface AnalysisIndex {
  payload: AnalysisPayload
  segments: Map<string, Segment>
  byLevel: Record<SegmentLevel, Segment[]>
  children: Map<string, Segment[]>
  results: Map<string, AnalysisResult[]>
  recordingResults: AnalysisResult[]
  events: AnalysisEvent[]
}

const LEVELS: SegmentLevel[] = ['section', 'phrase', 'word', 'syllable', 'note', 'phoneme']

export function indexAnalysis(payload: AnalysisPayload): AnalysisIndex {
  const segments = new Map<string, Segment>()
  const byLevel = Object.fromEntries(LEVELS.map((level) => [level, [] as Segment[]])) as Record<
    SegmentLevel,
    Segment[]
  >
  const children = new Map<string, Segment[]>()
  for (const segment of payload.segments) {
    segments.set(segment.id, segment)
    byLevel[segment.level]?.push(segment)
    if (segment.parent_id) {
      const list = children.get(segment.parent_id) ?? []
      list.push(segment)
      children.set(segment.parent_id, list)
    }
  }
  for (const level of LEVELS) byLevel[level].sort((a, b) => a.start_s - b.start_s)
  const results = new Map<string, AnalysisResult[]>()
  const recordingResults: AnalysisResult[] = []
  for (const result of payload.results) {
    if (!result.segment_id) {
      recordingResults.push(result)
      continue
    }
    const list = results.get(result.segment_id) ?? []
    list.push(result)
    results.set(result.segment_id, list)
  }
  const events = [...payload.events].sort((a, b) => a.start_s - b.start_s)
  return { payload, segments, byLevel, children, results, recordingResults, events }
}

export function resultFor(
  index: AnalysisIndex | null,
  analyzer: string,
  segmentId: string | null | undefined,
): AnalysisResult | null {
  if (!index || !segmentId) return null
  return index.results.get(segmentId)?.find((r) => r.analyzer_id === analyzer) ?? null
}

export function recordingResult(index: AnalysisIndex | null, analyzer: string): AnalysisResult | null {
  return index?.recordingResults.find((r) => r.analyzer_id === analyzer) ?? null
}

export function numberValue(result: AnalysisResult | null | undefined, key: string): number | null {
  const value = result?.values[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function segmentAt(list: Segment[], time: number): Segment | null {
  let low = 0
  let high = list.length - 1
  while (low <= high) {
    const mid = (low + high) >> 1
    const segment = list[mid]
    if (time < segment.start_s) high = mid - 1
    else if (time > segment.end_s) low = mid + 1
    else return segment
  }
  return null
}

export function nearestSegment(list: Segment[], time: number, maxDistance = Infinity): Segment | null {
  let best: Segment | null = null
  let distance = maxDistance
  for (const segment of list) {
    const d =
      time < segment.start_s ? segment.start_s - time : time > segment.end_s ? time - segment.end_s : 0
    if (d < distance) {
      distance = d
      best = segment
    }
  }
  return best
}

export function segmentsIn(list: Segment[], start: number, end: number): Segment[] {
  return list.filter((segment) => segment.end_s > start && segment.start_s < end)
}

export function ancestor(index: AnalysisIndex, segment: Segment, level: SegmentLevel): Segment | null {
  let current: Segment | undefined = segment
  let guard = 0
  while (current && guard < 8) {
    if (current.level === level) return current
    current = current.parent_id ? index.segments.get(current.parent_id) : undefined
    guard += 1
  }
  return null
}

export function descendants(index: AnalysisIndex, segment: Segment, level: SegmentLevel): Segment[] {
  return index.byLevel[level].filter(
    (s) => s.start_s >= segment.start_s - 1e-3 && s.end_s <= segment.end_s + 1e-3,
  )
}

export function wordFor(index: AnalysisIndex, segment: Segment): string | null {
  const word = ancestor(index, segment, 'word')
  if (word) return word.label
  const syllable = ancestor(index, segment, 'syllable')
  return syllable?.label ?? null
}

export interface ComparisonIndex {
  comparison: Comparison
  byRefSegment: Map<string, MetricComparison[]>
  byUserSegment: Map<string, MetricComparison[]>
  refToUser: Map<string, string>
  userToRef: Map<string, string>
  findingsBySegment: Map<string, Finding[]>
  findings: Map<string, Finding>
}

export function indexComparison(comparison: Comparison): ComparisonIndex {
  const byRefSegment = new Map<string, MetricComparison[]>()
  const byUserSegment = new Map<string, MetricComparison[]>()
  const refToUser = new Map<string, string>()
  const userToRef = new Map<string, string>()
  for (const metric of comparison.metrics) {
    if (metric.ref_segment_id) {
      const list = byRefSegment.get(metric.ref_segment_id) ?? []
      list.push(metric)
      byRefSegment.set(metric.ref_segment_id, list)
      if (metric.user_segment_id && !refToUser.has(metric.ref_segment_id)) {
        refToUser.set(metric.ref_segment_id, metric.user_segment_id)
      }
    }
    if (metric.user_segment_id) {
      const list = byUserSegment.get(metric.user_segment_id) ?? []
      list.push(metric)
      byUserSegment.set(metric.user_segment_id, list)
      if (metric.ref_segment_id && !userToRef.has(metric.user_segment_id)) {
        userToRef.set(metric.user_segment_id, metric.ref_segment_id)
      }
    }
  }
  const findingsBySegment = new Map<string, Finding[]>()
  const findings = new Map<string, Finding>()
  for (const finding of comparison.coaching.findings) {
    findings.set(finding.key, finding)
    const ids = new Set<string>([
      ...finding.instances,
      ...finding.evidence.map((e) => e.segment_id ?? '').filter(Boolean),
    ])
    for (const id of ids) {
      const list = findingsBySegment.get(id) ?? []
      list.push(finding)
      findingsBySegment.set(id, list)
    }
  }
  return { comparison, byRefSegment, byUserSegment, refToUser, userToRef, findingsBySegment, findings }
}

export function metricsInRange(comparison: Comparison, start: number, end: number): MetricComparison[] {
  return comparison.metrics.filter((m) => m.ref_end > start && m.ref_start < end)
}

export function magnitude(metric: MetricComparison): number {
  return Math.abs(metric.normalized ?? 0)
}

export function isFlagged(metric: MetricComparison): boolean {
  return magnitude(metric) >= 1 && metric.confidence >= 0.45 && metric.weight > 0
}

export function sortByImportance(metrics: MetricComparison[]): MetricComparison[] {
  return [...metrics].sort(
    (a, b) =>
      magnitude(b) * b.confidence * (b.importance || 1) - magnitude(a) * a.confidence * (a.importance || 1),
  )
}

export function metricUnit(comparison: Comparison | null | undefined, metric: MetricComparison): string {
  if (metric.unit) return metric.unit
  return comparison?.scores.categories[metric.category]?.metrics[metric.metric_id]?.unit ?? ''
}

export function metricName(comparison: Comparison | null | undefined, metric: MetricComparison): string {
  return comparison?.scores.categories[metric.category]?.metrics[metric.metric_id]?.name ?? metric.metric_id
}
