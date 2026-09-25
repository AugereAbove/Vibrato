export interface PitchReading {
  f0: number | null
  clarity: number
}

export function yin(
  buffer: Float32Array,
  sampleRate: number,
  fmin = 65,
  fmax = 1400,
  threshold = 0.15,
): PitchReading {
  const tauMin = Math.max(2, Math.floor(sampleRate / fmax))
  const tauMax = Math.min(Math.floor(buffer.length / 2), Math.ceil(sampleRate / fmin))
  if (tauMax <= tauMin + 2) return { f0: null, clarity: 0 }
  const window = buffer.length - tauMax
  let energy = 0
  for (let i = 0; i < window; i += 1) energy += buffer[i] * buffer[i]
  if (energy / window < 1e-7) return { f0: null, clarity: 0 }
  const diff = new Float32Array(tauMax + 1)
  for (let tau = 1; tau <= tauMax; tau += 1) {
    let sum = 0
    for (let i = 0; i < window; i += 1) {
      const d = buffer[i] - buffer[i + tau]
      sum += d * d
    }
    diff[tau] = sum
  }
  const cmnd = new Float32Array(tauMax + 1)
  cmnd[0] = 1
  let running = 0
  for (let tau = 1; tau <= tauMax; tau += 1) {
    running += diff[tau]
    cmnd[tau] = running > 0 ? (diff[tau] * tau) / running : 1
  }
  let best = -1
  for (let tau = tauMin; tau <= tauMax; tau += 1) {
    if (cmnd[tau] < threshold) {
      while (tau + 1 <= tauMax && cmnd[tau + 1] < cmnd[tau]) tau += 1
      best = tau
      break
    }
  }
  if (best < 0) {
    let minimum = Infinity
    for (let tau = tauMin; tau <= tauMax; tau += 1) {
      if (cmnd[tau] < minimum) {
        minimum = cmnd[tau]
        best = tau
      }
    }
    if (minimum > 0.35) return { f0: null, clarity: Math.max(0, 1 - minimum) }
  }
  let refined = best
  if (best > 1 && best < tauMax) {
    const a = cmnd[best - 1]
    const b = cmnd[best]
    const c = cmnd[best + 1]
    const denominator = a + c - 2 * b
    if (Math.abs(denominator) > 1e-9) refined = best + (a - c) / (2 * denominator)
  }
  return { f0: sampleRate / refined, clarity: Math.max(0, Math.min(1, 1 - cmnd[best])) }
}

export class PitchTracker {
  private readonly analyser: AnalyserNode
  private readonly buffer: Float32Array<ArrayBuffer>
  private history: number[] = []

  constructor(analyser: AnalyserNode) {
    this.analyser = analyser
    this.buffer = new Float32Array(analyser.fftSize)
  }

  read(): PitchReading & { level: number } {
    this.analyser.getFloatTimeDomainData(this.buffer)
    let peak = 0
    for (let i = 0; i < this.buffer.length; i += 1) peak = Math.max(peak, Math.abs(this.buffer[i]))
    const reading = yin(this.buffer, this.analyser.context.sampleRate)
    if (reading.f0 !== null && reading.clarity > 0.6) {
      this.history = [...this.history.slice(-4), reading.f0]
      const sorted = [...this.history].sort((a, b) => a - b)
      return { f0: sorted[Math.floor(sorted.length / 2)], clarity: reading.clarity, level: peak }
    }
    this.history = []
    return { f0: null, clarity: reading.clarity, level: peak }
  }
}
