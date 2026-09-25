import { test as base, expect, type APIRequestContext } from '@playwright/test'

const RATE = 22050

export type Note = [midi: number, seconds: number]

export const MELODY: Note[] = [
  [57, 0.55],
  [60, 0.55],
  [62, 0.8],
  [64, 0.55],
  [62, 0.55],
  [60, 1.1],
]

export interface Voice {
  notes?: Note[]
  detune?: number[]
  vibrato?: number
  delay?: number
  gain?: number
  breath?: number
}

function encodeWav(samples: Float32Array, rate: number): Buffer {
  const out = Buffer.alloc(44 + samples.length * 2)
  out.write('RIFF', 0, 'ascii')
  out.writeUInt32LE(36 + samples.length * 2, 4)
  out.write('WAVE', 8, 'ascii')
  out.write('fmt ', 12, 'ascii')
  out.writeUInt32LE(16, 16)
  out.writeUInt16LE(1, 20)
  out.writeUInt16LE(1, 22)
  out.writeUInt32LE(rate, 24)
  out.writeUInt32LE(rate * 2, 28)
  out.writeUInt16LE(2, 32)
  out.writeUInt16LE(16, 34)
  out.write('data', 36, 'ascii')
  out.writeUInt32LE(samples.length * 2, 40)
  samples.forEach((value, i) =>
    out.writeInt16LE(Math.round(Math.max(-1, Math.min(1, value)) * 32767), 44 + i * 2),
  )
  return out
}

export function sing(voice: Voice = {}): Buffer {
  const notes = voice.notes ?? MELODY
  const gap = 0.07
  const lead = 0.3 + (voice.delay ?? 0)
  const total = lead + notes.reduce((sum, [, seconds]) => sum + seconds + gap, 0) + 0.4
  const samples = new Float32Array(Math.ceil(total * RATE))
  let seed = 12345
  const noise = () => {
    seed = (seed * 1664525 + 1013904223) >>> 0
    return seed / 2 ** 32 - 0.5
  }
  let onset = lead
  notes.forEach(([midi, seconds], index) => {
    const start = Math.floor(onset * RATE)
    const length = Math.floor(seconds * RATE)
    const f0 = 440 * 2 ** ((midi - 69 + (voice.detune?.[index] ?? 0) / 100) / 12)
    let phase = 0
    for (let i = 0; i < length; i += 1) {
      const t = i / RATE
      const cents = (voice.vibrato ?? 0) * Math.min(1, t / 0.25) * Math.sin(2 * Math.PI * 5.5 * t)
      phase += (2 * Math.PI * f0 * 2 ** (cents / 1200)) / RATE
      const envelope = Math.min(1, t / 0.04) * Math.min(1, (seconds - t) / 0.06)
      let value = 0
      for (let k = 1; k <= 8; k += 1) value += Math.sin(k * phase) / k ** 1.3
      samples[start + i] += 0.25 * (voice.gain ?? 1) * envelope * (value + (voice.breath ?? 0.01) * noise())
    }
    onset += seconds + gap
  })
  return encodeWav(samples, RATE)
}

export const REFERENCE = () => sing({ vibrato: 35 })
export const TAKE = () => sing({ detune: [0, 0, 45, 0, -30, 0], delay: 0.12, gain: 0.8, breath: 0.03 })

export async function createProject(request: APIRequestContext, name: string): Promise<string> {
  const response = await request.post('/api/projects', { data: { name } })
  expect(response.ok()).toBe(true)
  return ((await response.json()) as { project: { id: string } }).project.id
}

export async function upload(
  request: APIRequestContext,
  projectId: string,
  kind: 'reference' | 'take',
  name: string,
  buffer: Buffer,
): Promise<{ recordingId: string; taskId: string | null }> {
  const response = await request.post(`/api/projects/${projectId}/recordings`, {
    multipart: {
      file: { name: `${name}.wav`, mimeType: 'audio/wav', buffer },
      kind,
      name,
      source: 'import',
      auto_analyze: 'true',
    },
  })
  expect(response.ok(), await response.text()).toBe(true)
  const body = (await response.json()) as { recording: { id: string }; task: { id: string } | null }
  return { recordingId: body.recording.id, taskId: body.task?.id ?? null }
}

export async function waitForTask(request: APIRequestContext, taskId: string | null, timeout = 180_000) {
  if (!taskId) return
  await expect
    .poll(
      async () => {
        const response = await request.get(`/api/tasks/${taskId}`)
        const { task } = (await response.json()) as { task: { status: string; error: unknown } }
        if (['failed', 'cancelled', 'interrupted'].includes(task.status))
          throw new Error(`task ${task.status}: ${JSON.stringify(task.error)}`)
        return task.status
      },
      { timeout, intervals: [500, 1000, 2000] },
    )
    .toBe('complete')
}

export const test = base.extend<{ consoleGuard: { allow: (pattern: RegExp) => void } }>({
  consoleGuard: [
    async ({ page }, use) => {
      const problems: string[] = []
      const allowed: RegExp[] = []
      page.on('console', (message) => {
        if (message.type() === 'error' || message.type() === 'warning')
          problems.push(`${message.type()}: ${message.text()}`)
      })
      page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`))
      await use({ allow: (pattern) => void allowed.push(pattern) })
      expect(problems.filter((problem) => !allowed.some((pattern) => pattern.test(problem)))).toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
