import { describe, expect, it } from 'vitest'
import { parseFeatureBundle, parsePeaks, parseSpectrogram, pickPeakLevel } from './binary'

function pack(header: object, payload: ArrayBufferView, remainder = 0): ArrayBuffer {
  let json = JSON.stringify(header)
  while ((4 + json.length) % 4 !== remainder) json += ' '
  const text = new TextEncoder().encode(json)
  const bytes = new Uint8Array(payload.buffer, payload.byteOffset, payload.byteLength)
  const out = new Uint8Array(4 + text.length + bytes.length)
  new DataView(out.buffer).setUint32(0, text.length, true)
  out.set(text, 4)
  out.set(bytes, 4 + text.length)
  return out.buffer
}

function featureBuffer(remainder: number): ArrayBuffer {
  return pack(
    {
      n: 3,
      hop_s: 0.01,
      duration_s: 0.03,
      meta: { sample_rate: 44100 },
      arrays: { f0_hz: { offset: 0, length: 3 }, voiced: { offset: 12, length: 3 } },
    },
    new Float32Array([220, 0, 230, 1, 0, 1]),
    remainder,
  )
}

describe('parseFeatureBundle', () => {
  it('reads the header and every track', () => {
    const bundle = parseFeatureBundle(featureBuffer(0))
    expect(bundle.n).toBe(3)
    expect(bundle.hopS).toBe(0.01)
    expect(bundle.durationS).toBe(0.03)
    expect(bundle.meta).toEqual({ sample_rate: 44100 })
    expect([...bundle.tracks.f0_hz]).toEqual([220, 0, 230])
    expect([...bundle.tracks.voiced]).toEqual([1, 0, 1])
  })

  it('copies tracks that are not four-byte aligned', () => {
    const buffer = featureBuffer(2)
    const bundle = parseFeatureBundle(buffer)
    expect(bundle.tracks.f0_hz.buffer).not.toBe(buffer)
    expect([...bundle.tracks.f0_hz]).toEqual([220, 0, 230])
    expect([...bundle.tracks.voiced]).toEqual([1, 0, 1])
  })

  it('rejects truncated payloads', () => {
    expect(() => parseFeatureBundle(new ArrayBuffer(2))).toThrow(/truncated/)
    const lying = new Uint8Array(10)
    new DataView(lying.buffer).setUint32(0, 100, true)
    expect(() => parseFeatureBundle(lying.buffer)).toThrow(/larger than the payload/)
  })
})

describe('parseSpectrogram', () => {
  it('exposes the byte matrix with its scale', () => {
    const buffer = pack(
      { frames: 2, bins: 3, hop_s: 0.02, fmin: 50, fmax: 8000, db_top: -10, db_range: 80 },
      new Uint8Array([0, 1, 2, 253, 254, 255]),
    )
    const spectrogram = parseSpectrogram(buffer)
    expect(spectrogram).toMatchObject({
      frames: 2,
      bins: 3,
      hopS: 0.02,
      fmin: 50,
      fmax: 8000,
      dbTop: -10,
      dbRange: 80,
    })
    expect([...spectrogram.data]).toEqual([0, 1, 2, 253, 254, 255])
  })
})

describe('parsePeaks', () => {
  const buffer = pack(
    {
      sample_rate: 1000,
      n_samples: 2000,
      levels: [
        { samples_per_peak: 256, count: 2, offset: 0 },
        { samples_per_peak: 512, count: 1, offset: 8 },
      ],
    },
    new Int16Array([-100, 200, -300, 400, -300, 400]),
    2,
  )

  it('reads interleaved min and max pairs for each level', () => {
    const pyramid = parsePeaks(buffer)
    expect(pyramid.sampleRate).toBe(1000)
    expect(pyramid.durationS).toBe(2)
    expect(pyramid.levels.map((level) => level.samplesPerPeak)).toEqual([256, 512])
    expect([...pyramid.levels[0].data]).toEqual([-100, 200, -300, 400])
    expect([...pyramid.levels[1].data]).toEqual([-300, 400])
  })

  it('picks the coarsest level that still resolves a pixel', () => {
    const pyramid = parsePeaks(buffer)
    expect(pickPeakLevel(pyramid, 10).samplesPerPeak).toBe(256)
    expect(pickPeakLevel(pyramid, 300).samplesPerPeak).toBe(256)
    expect(pickPeakLevel(pyramid, 1000).samplesPerPeak).toBe(512)
  })
})
