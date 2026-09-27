import type { CategoryId, Coaching, Finding, Scores } from '../../../api/types'

export const FOCUS_COUNT = 3
export const GOOD_COUNT = 4

export const FRIENDLY_CATEGORY: Record<string, string> = {
  pitch: 'Hitting the notes',
  timing: 'Timing',
  vowel: 'Vowel shapes',
  vibrato: 'Vibrato',
  dynamics: 'Loud and soft',
  phonation: 'Clear tone',
  articulation: 'Clear words',
  breath: 'Breathing',
  timbre: 'Tone colour',
}

export interface Verdict {
  score: number | null
  phrase: string
  detail: string
  tone: 'great' | 'good' | 'ok' | 'low' | 'none'
}

export function verdict(score: number | null): Verdict {
  if (score === null || !Number.isFinite(score))
    return {
      score: null,
      phrase: 'We couldn’t score this take',
      detail: 'Sing the same part as the singer, close to the microphone, with no music playing in the room.',
      tone: 'none',
    }
  const rounded = Math.round(Math.max(0, Math.min(100, score)))
  if (rounded >= 90)
    return {
      score: rounded,
      phrase: 'Excellent!',
      detail: 'You sound very close to the original.',
      tone: 'great',
    }
  if (rounded >= 80)
    return {
      score: rounded,
      phrase: 'Really close!',
      detail: 'You sound a lot like the original.',
      tone: 'great',
    }
  if (rounded >= 70)
    return { score: rounded, phrase: 'Good job!', detail: 'You’re on the right track.', tone: 'good' }
  if (rounded >= 55)
    return {
      score: rounded,
      phrase: 'Getting there',
      detail: 'A few things to work on. Start with the first one below.',
      tone: 'ok',
    }
  return {
    score: rounded,
    phrase: 'Keep practising',
    detail: 'Focus on the first thing below, then try again.',
    tone: 'low',
  }
}

export function barLabel(score: number): string {
  if (score >= 90) return 'Great'
  if (score >= 75) return 'Good'
  if (score >= 60) return 'Okay'
  return 'Needs work'
}

export function focusFindings(coaching: Coaching): Finding[] {
  return [...coaching.primary, ...coaching.secondary, ...coaching.minor].slice(0, FOCUS_COUNT)
}

export function plainSentence(finding: Finding): string {
  return finding.texts.simple ?? finding.texts.beginner
}

export function plainTip(finding: Finding): string {
  return finding.texts.simple_tip ?? finding.texts.adjust
}

export function nailedIt(coaching: Coaching): string[] {
  const out: string[] = []
  for (const item of coaching.already_good) {
    const text = item.simple ?? item.name
    if (!out.includes(text)) out.push(text)
    if (out.length >= GOOD_COUNT) break
  }
  return out
}

export interface CategoryBar {
  id: CategoryId
  label: string
  score: number
  word: string
}

export function categoryBars(scores: Scores): CategoryBar[] {
  const bars: CategoryBar[] = []
  for (const [id, category] of Object.entries(scores.categories) as [
    CategoryId,
    Scores['categories'][CategoryId],
  ][]) {
    if (!category.enabled || category.score === null || category.confidence < 0.25) continue
    const score = Math.round(Math.max(0, Math.min(100, category.score)))
    bars.push({ id, label: FRIENDLY_CATEGORY[id] ?? category.label, score, word: barLabel(score) })
  }
  return bars
}
