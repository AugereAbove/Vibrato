import { scoreTone } from '../../lib/score'
import { useAnimatedValue } from './useAnimatedValue'

export function AnimatedNumber({
  value,
  decimals = 0,
  duration,
  fallback = '–',
}: {
  value: number | null | undefined
  decimals?: number
  duration?: number
  fallback?: string
}) {
  const animated = useAnimatedValue(value, duration)
  return <span className="num">{animated == null ? fallback : animated.toFixed(decimals)}</span>
}

export function ScoreRing({
  score,
  confidence,
  size = 64,
  label,
  previous,
}: {
  score: number | null | undefined
  confidence?: number
  size?: number
  label?: string
  previous?: number | null
}) {
  const animated = useAnimatedValue(score)
  const stroke = Math.max(3, size / 14)
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const fraction = animated == null ? 0 : Math.max(0, Math.min(1, animated / 100))
  const tone = scoreTone(score)
  const lowConfidence = confidence !== undefined && confidence < 0.5
  const delta = score != null && previous != null ? score - previous : null
  return (
    <div
      className={`score-ring tone-${tone}${lowConfidence ? ' is-uncertain' : ''}`}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${label ?? 'Score'} ${score == null ? 'not available' : score.toFixed(0)} out of 100${
        lowConfidence ? ', low confidence' : ''
      }`}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
        <circle className="score-ring-track" cx={size / 2} cy={size / 2} r={radius} strokeWidth={stroke} />
        <circle
          className="score-ring-value"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
          strokeDasharray={lowConfidence ? `${stroke * 1.2} ${stroke * 0.9}` : `${circumference}`}
          strokeDashoffset={lowConfidence ? 0 : circumference * (1 - fraction)}
          style={lowConfidence ? { opacity: 0.35 + 0.65 * fraction } : undefined}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span className="score-ring-label" style={{ fontSize: Math.max(11, size * 0.3) }}>
        {animated == null ? '–' : animated.toFixed(0)}
      </span>
      {delta != null && Math.abs(delta) >= 0.5 && size >= 56 ? (
        <span className={`score-ring-delta ${delta > 0 ? 'good-text' : 'bad-text'}`}>
          {delta > 0 ? '+' : '−'}
          {Math.abs(delta).toFixed(0)}
        </span>
      ) : null}
    </div>
  )
}
