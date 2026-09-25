export type ScoreTone = 'good' | 'warn' | 'bad' | 'neutral'

export function scoreTone(score: number | null | undefined): ScoreTone {
  if (score == null || !Number.isFinite(score)) return 'neutral'
  if (score >= 85) return 'good'
  if (score >= 65) return 'warn'
  return 'bad'
}
