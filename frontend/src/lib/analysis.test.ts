import { describe, expect, it } from 'vitest'
import type { AnalysisPayload, MetricComparison, Segment } from '../api/types'
import {
  ancestor,
  indexAnalysis,
  isFlagged,
  nearestSegment,
  segmentAt,
  segmentsIn,
  sortByImportance,
  wordFor,
} from './analysis'

function segment(
  id: string,
  level: Segment['level'],
  start: number,
  end: number,
  parent: string | null = null,
): Segment {
  return {
    id,
    level,
    ordinal: 0,
    start_s: start,
    end_s: end,
    label: id,
    confidence: 1,
    parent_id: parent,
    props: {},
  }
}

const segments = [
  segment('phrase', 'phrase', 0, 3),
  segment('love', 'word', 1, 2, 'phrase'),
  segment('hello', 'word', 0, 1, 'phrase'),
  segment('n2', 'note', 1.2, 1.8, 'love'),
  segment('n1', 'note', 0.1, 0.9, 'hello'),
]

const index = indexAnalysis({ segments, results: [], events: [] } as unknown as AnalysisPayload)

describe('indexAnalysis', () => {
  it('groups and sorts segments by level', () => {
    expect(index.byLevel.word.map((s) => s.id)).toEqual(['hello', 'love'])
    expect(index.byLevel.note.map((s) => s.id)).toEqual(['n1', 'n2'])
    expect(
      index.children
        .get('phrase')
        ?.map((s) => s.id)
        .sort(),
    ).toEqual(['hello', 'love'])
  })

  it('walks up to ancestors', () => {
    const note = index.segments.get('n2') as Segment
    expect(ancestor(index, note, 'phrase')?.id).toBe('phrase')
    expect(wordFor(index, note)).toBe('love')
  })
})

describe('segment lookup', () => {
  it('finds the segment under a time', () => {
    expect(segmentAt(index.byLevel.note, 0.5)?.id).toBe('n1')
    expect(segmentAt(index.byLevel.note, 1.5)?.id).toBe('n2')
    expect(segmentAt(index.byLevel.note, 1.0)).toBeNull()
  })

  it('finds the nearest segment within a distance', () => {
    expect(nearestSegment(index.byLevel.note, 1.0)?.id).toBe('n1')
    expect(nearestSegment(index.byLevel.note, 1.15)?.id).toBe('n2')
    expect(nearestSegment(index.byLevel.note, 5, 0.5)).toBeNull()
  })

  it('lists overlapping segments', () => {
    expect(segmentsIn(index.byLevel.note, 0.8, 1.3).map((s) => s.id)).toEqual(['n1', 'n2'])
    expect(segmentsIn(index.byLevel.note, 2, 3)).toEqual([])
  })
})

describe('metric ranking', () => {
  const base = { confidence: 0.9, weight: 1, importance: 1 } as MetricComparison
  const small = { ...base, metric_id: 'small', normalized: 0.5 }
  const big = { ...base, metric_id: 'big', normalized: -3 }
  const unsure = { ...base, metric_id: 'unsure', normalized: 5, confidence: 0.2 }

  it('flags only confident, meaningful differences', () => {
    expect(isFlagged(small)).toBe(false)
    expect(isFlagged(big)).toBe(true)
    expect(isFlagged(unsure)).toBe(false)
  })

  it('ranks by size, confidence and importance', () => {
    expect(sortByImportance([small, unsure, big]).map((m) => m.metric_id)).toEqual(['big', 'unsure', 'small'])
  })
})
