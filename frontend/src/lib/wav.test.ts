import { describe, expect, it } from 'vitest'
import { concatChunks, encodeWav, peakLevel, toDb } from './wav'

function text(view: DataView, offset: number, length: number): string {
  return String.fromCharCode(...new Uint8Array(view.buffer, offset, length))
}

describe('encodeWav', () => {
  it('writes a 16-bit mono PCM file with clipped samples', async () => {
    const blob = encodeWav(new Float32Array([0, 0.5, -1, 1.5]), 16000)
    expect(blob.type).toBe('audio/wav')
    expect(blob.size).toBe(52)
    const view = new DataView(await blob.arrayBuffer())
    expect(text(view, 0, 4)).toBe('RIFF')
    expect(view.getUint32(4, true)).toBe(44)
    expect(text(view, 8, 4)).toBe('WAVE')
    expect(view.getUint16(20, true)).toBe(1)
    expect(view.getUint16(22, true)).toBe(1)
    expect(view.getUint32(24, true)).toBe(16000)
    expect(view.getUint32(28, true)).toBe(32000)
    expect(view.getUint16(34, true)).toBe(16)
    expect(text(view, 36, 4)).toBe('data')
    expect(view.getUint32(40, true)).toBe(8)
    expect([0, 1, 2, 3].map((i) => view.getInt16(44 + i * 2, true))).toEqual([0, 16383, -32768, 32767])
  })
})

describe('sample helpers', () => {
  it('concatenates recorder chunks in order', () => {
    const joined = concatChunks([new Float32Array([1, 2]), new Float32Array([]), new Float32Array([3])])
    expect([...joined]).toEqual([1, 2, 3])
  })

  it('measures peaks in decibels', () => {
    expect(peakLevel(new Float32Array([0.1, -0.7, 0.3]))).toBeCloseTo(0.7, 6)
    expect(peakLevel(new Float32Array([]))).toBe(0)
    expect(toDb(1)).toBe(0)
    expect(toDb(0.5)).toBeCloseTo(-6.0206, 4)
    expect(toDb(0)).toBe(-Infinity)
  })
})
