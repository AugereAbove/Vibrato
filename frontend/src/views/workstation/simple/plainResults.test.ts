import { describe, expect, it } from 'vitest'
import type { Coaching, Finding, Scores } from '../../../api/types'
import {
  barLabel,
  categoryBars,
  focusFindings,
  nailedIt,
  plainSentence,
  plainTip,
  verdict,
} from './plainResults'

function finding(key: string, texts: Partial<Finding['texts']> = {}): Finding {
  return {
    key,
    texts: { beginner: `beginner ${key}`, adjust: `adjust ${key}`, ...texts },
  } as unknown as Finding
}

function coaching(parts: Partial<Coaching>): Coaching {
  return {
    primary: [],
    secondary: [],
    minor: [],
    uncertain: [],
    already_good: [],
    ...parts,
  } as unknown as Coaching
}

describe('verdict', () => {
  it('rounds the score and picks a phrase', () => {
    expect(verdict(88.4)).toMatchObject({ score: 88, phrase: 'Really close!' })
    expect(verdict(94)).toMatchObject({ phrase: 'Excellent!' })
    expect(verdict(72)).toMatchObject({ phrase: 'Good job!' })
    expect(verdict(60)).toMatchObject({ phrase: 'Getting there' })
    expect(verdict(31)).toMatchObject({ phrase: 'Keep practising' })
  })

  it('handles a missing score', () => {
    expect(verdict(null)).toMatchObject({ score: null, tone: 'none' })
  })

  it('clamps out-of-range scores', () => {
    expect(verdict(104).score).toBe(100)
  })
})

describe('focusFindings', () => {
  it('takes the top three in tier order, filling from minor', () => {
    const result = focusFindings(
      coaching({ primary: [finding('a')], secondary: [finding('b')], minor: [finding('c'), finding('d')] }),
    )
    expect(result.map((f) => f.key)).toEqual(['a', 'b', 'c'])
  })

  it('never includes uncertain findings', () => {
    expect(focusFindings(coaching({ uncertain: [finding('u')] }))).toEqual([])
  })
})

describe('plain wording', () => {
  it('prefers the simple text and falls back to the beginner text', () => {
    expect(plainSentence(finding('a', { simple: 'Plain.' }))).toBe('Plain.')
    expect(plainSentence(finding('a'))).toBe('beginner a')
    expect(plainTip(finding('a', { simple_tip: 'Tip.' }))).toBe('Tip.')
    expect(plainTip(finding('a'))).toBe('adjust a')
  })
})

describe('nailedIt', () => {
  it('de-duplicates and caps the list', () => {
    const good = ['A', 'A', 'B', 'C', 'D', 'E'].map((simple, i) => ({
      metric_id: `m${i}`,
      name: simple,
      simple,
    }))
    expect(nailedIt(coaching({ already_good: good as Coaching['already_good'] }))).toEqual([
      'A',
      'B',
      'C',
      'D',
    ])
  })
})

describe('categoryBars', () => {
  it('uses friendly labels and skips unscored or unreliable categories', () => {
    const scores = {
      categories: {
        pitch: { label: 'Pitch', score: 97.6, confidence: 0.9, enabled: true },
        timing: { label: 'Timing', score: null, confidence: 0.9, enabled: true },
        timbre: { label: 'Timbre', score: 50, confidence: 0.1, enabled: true },
        vowel: { label: 'Vowel', score: 70, confidence: 0.9, enabled: false },
      },
    } as unknown as Scores
    expect(categoryBars(scores)).toEqual([
      { id: 'pitch', label: 'Hitting the notes', score: 98, word: 'Great' },
    ])
  })

  it('maps scores to words', () => {
    expect(barLabel(76)).toBe('Good')
    expect(barLabel(61)).toBe('Okay')
    expect(barLabel(40)).toBe('Needs work')
  })
})
