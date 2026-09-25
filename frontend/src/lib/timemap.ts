export interface TimeMapSource {
  ref_times: number[]
  user_times: number[]
  confidence: number[]
}

function search(values: Float64Array, target: number): number {
  let low = 0
  let high = values.length - 1
  while (low < high) {
    const mid = (low + high + 1) >> 1
    if (values[mid] <= target) low = mid
    else high = mid - 1
  }
  return low
}

function interpolate(xs: Float64Array, ys: Float64Array, x: number): number {
  const n = xs.length
  if (n === 0) return x
  if (n === 1) return ys[0] + (x - xs[0])
  if (x <= xs[0]) return ys[0] + (x - xs[0])
  if (x >= xs[n - 1]) return ys[n - 1] + (x - xs[n - 1])
  const i = search(xs, x)
  const j = Math.min(n - 1, i + 1)
  const span = xs[j] - xs[i]
  if (span <= 1e-9) return ys[i]
  return ys[i] + ((ys[j] - ys[i]) * (x - xs[i])) / span
}

function monotone(values: number[]): Float64Array {
  const out = new Float64Array(values.length)
  let last = -Infinity
  for (let i = 0; i < values.length; i += 1) {
    last = Math.max(last, values[i])
    out[i] = last
  }
  return out
}

export class TimeMap {
  private readonly ref: Float64Array
  private readonly user: Float64Array
  private readonly conf: Float64Array
  readonly identity: boolean

  constructor(source: TimeMapSource | null) {
    this.identity = !source || source.ref_times.length < 2
    this.ref = monotone(source?.ref_times ?? [])
    this.user = monotone(source?.user_times ?? [])
    this.conf = Float64Array.from(source?.confidence ?? [])
  }

  refToUser(t: number): number {
    return this.identity ? t : interpolate(this.ref, this.user, t)
  }

  userToRef(t: number): number {
    return this.identity ? t : interpolate(this.user, this.ref, t)
  }

  confidenceAt(refTime: number): number {
    if (this.identity || this.conf.length === 0) return 1
    const i = search(this.ref, refTime)
    return this.conf[Math.min(i, this.conf.length - 1)]
  }

  pairs(): { ref: Float64Array; user: Float64Array; confidence: Float64Array } {
    return { ref: this.ref, user: this.user, confidence: this.conf }
  }
}

export const IDENTITY_MAP = new TimeMap(null)
