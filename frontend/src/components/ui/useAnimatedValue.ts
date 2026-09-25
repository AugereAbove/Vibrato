import { useEffect, useRef, useState } from 'react'
import { reducedMotionNow } from '../../state/prefs'

function easeOutCubic(t: number): number {
  return 1 - (1 - t) ** 3
}

export function useAnimatedValue(target: number | null | undefined, duration = 650): number | null {
  const [value, setValue] = useState<number | null>(target ?? null)
  const current = useRef<number | null>(target ?? null)

  useEffect(() => {
    if (target == null || !Number.isFinite(target)) {
      current.current = null
      const frame = window.requestAnimationFrame(() => setValue(null))
      return () => window.cancelAnimationFrame(frame)
    }
    const from = current.current
    if (from == null || reducedMotionNow() || Math.abs(from - target) < 1e-6) {
      current.current = target
      const frame = window.requestAnimationFrame(() => setValue(target))
      return () => window.cancelAnimationFrame(frame)
    }
    const start = performance.now()
    let frame = 0
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const next = from + (target - from) * easeOutCubic(t)
      current.current = next
      setValue(next)
      if (t < 1) frame = window.requestAnimationFrame(step)
    }
    frame = window.requestAnimationFrame(step)
    return () => window.cancelAnimationFrame(frame)
  }, [target, duration])

  return value
}
