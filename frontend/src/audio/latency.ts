import type { Recorder } from './recorder'

export interface LatencyResult {
  latencyMs: number
  spreadMs: number
  detections: number
  confidence: number
}

const CLICKS = 8
const SPACING_S = 0.45
const LEAD_S = 0.6

function scheduleBurst(ctx: AudioContext, at: number): void {
  const length = Math.round(ctx.sampleRate * 0.004)
  const buffer = ctx.createBuffer(1, length, ctx.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < length; i += 1) {
    const envelope = Math.sin((Math.PI * i) / length)
    data[i] = envelope * Math.sin((2 * Math.PI * 2500 * i) / ctx.sampleRate)
  }
  const source = ctx.createBufferSource()
  source.buffer = buffer
  const gain = ctx.createGain()
  gain.gain.value = 0.9
  source.connect(gain)
  gain.connect(ctx.destination)
  source.start(at)
}

export async function measureLatency(recorder: Recorder): Promise<LatencyResult> {
  const ctx = recorder.context
  if (ctx.state === 'suspended') await ctx.resume()
  recorder.start()
  const base = ctx.currentTime + LEAD_S
  const times: number[] = []
  for (let i = 0; i < CLICKS; i += 1) {
    const at = base + i * SPACING_S
    times.push(at)
    scheduleBurst(ctx, at)
  }
  const total = LEAD_S + CLICKS * SPACING_S + 0.5
  await new Promise((resolve) => window.setTimeout(resolve, total * 1000))
  const capture = await recorder.stop()
  const sr = capture.sampleRate
  const x = capture.samples
  let noise = 0
  const noiseEnd = Math.max(0, Math.min(x.length, Math.round((times[0] - capture.startTime - 0.1) * sr)))
  for (let i = 0; i < noiseEnd; i += 1) noise = Math.max(noise, Math.abs(x[i]))
  const delays: number[] = []
  for (const at of times) {
    const from = Math.round((at - capture.startTime) * sr)
    const to = Math.min(x.length, from + Math.round(0.4 * sr))
    if (from < 0 || from >= x.length) continue
    let peak = 0
    for (let i = from; i < to; i += 1) peak = Math.max(peak, Math.abs(x[i]))
    if (peak < Math.max(noise * 4, 0.01)) continue
    const threshold = Math.max(noise * 3, peak * 0.35)
    for (let i = from; i < to; i += 1) {
      if (Math.abs(x[i]) >= threshold) {
        delays.push(((i - from) / sr) * 1000)
        break
      }
    }
  }
  if (delays.length < 3) {
    throw new Error(
      'The test clicks were not picked up by the microphone. Turn the speaker volume up, use speakers rather than headphones, and try again.',
    )
  }
  const sorted = [...delays].sort((a, b) => a - b)
  const median = sorted[Math.floor(sorted.length / 2)]
  const q1 = sorted[Math.floor(sorted.length * 0.25)]
  const q3 = sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.75))]
  const spread = q3 - q1
  const confidence = Math.max(0, Math.min(1, (delays.length / CLICKS) * (1 - spread / 20)))
  return {
    latencyMs: Math.round(median * 10) / 10,
    spreadMs: Math.round(spread * 10) / 10,
    detections: delays.length,
    confidence,
  }
}
