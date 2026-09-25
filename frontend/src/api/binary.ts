export interface FeatureBundle {
  n: number
  hopS: number
  durationS: number
  meta: Record<string, unknown>
  tracks: Record<string, Float32Array>
}

export interface SpectrogramData {
  frames: number
  bins: number
  hopS: number
  fmin: number
  fmax: number
  dbTop: number
  dbRange: number
  data: Uint8Array
}

export interface PeakLevel {
  samplesPerPeak: number
  count: number
  data: Int16Array
}

export interface PeakPyramid {
  sampleRate: number
  nSamples: number
  durationS: number
  levels: PeakLevel[]
}

function readHeader<T>(buffer: ArrayBuffer): { header: T; offset: number } {
  if (buffer.byteLength < 4) throw new Error('Binary payload is truncated.')
  const length = new DataView(buffer).getUint32(0, true)
  if (4 + length > buffer.byteLength) throw new Error('Binary header is larger than the payload.')
  const text = new TextDecoder().decode(new Uint8Array(buffer, 4, length))
  return { header: JSON.parse(text) as T, offset: 4 + length }
}

interface FeatureHeader {
  n: number
  hop_s: number
  duration_s: number
  meta: Record<string, unknown>
  arrays: Record<string, { offset: number; length: number }>
}

export function parseFeatureBundle(buffer: ArrayBuffer): FeatureBundle {
  const { header, offset } = readHeader<FeatureHeader>(buffer)
  const tracks: Record<string, Float32Array> = {}
  for (const [name, span] of Object.entries(header.arrays)) {
    const start = offset + span.offset
    if (start % 4 === 0) {
      tracks[name] = new Float32Array(buffer, start, span.length)
    } else {
      tracks[name] = new Float32Array(buffer.slice(start, start + span.length * 4))
    }
  }
  return { n: header.n, hopS: header.hop_s, durationS: header.duration_s, meta: header.meta, tracks }
}

interface SpectrogramHeader {
  frames: number
  bins: number
  hop_s: number
  fmin: number
  fmax: number
  db_top: number
  db_range: number
}

export function parseSpectrogram(buffer: ArrayBuffer): SpectrogramData {
  const { header, offset } = readHeader<SpectrogramHeader>(buffer)
  return {
    frames: header.frames,
    bins: header.bins,
    hopS: header.hop_s,
    fmin: header.fmin,
    fmax: header.fmax,
    dbTop: header.db_top,
    dbRange: header.db_range,
    data: new Uint8Array(buffer, offset, header.frames * header.bins),
  }
}

interface PeakHeader {
  sample_rate: number
  n_samples: number
  levels: { samples_per_peak: number; count: number; offset: number }[]
}

export function parsePeaks(buffer: ArrayBuffer): PeakPyramid {
  const { header, offset } = readHeader<PeakHeader>(buffer)
  const levels = header.levels.map((level) => {
    const start = offset + level.offset
    const data =
      start % 2 === 0
        ? new Int16Array(buffer, start, level.count * 2)
        : new Int16Array(buffer.slice(start, start + level.count * 4))
    return { samplesPerPeak: level.samples_per_peak, count: level.count, data }
  })
  return {
    sampleRate: header.sample_rate,
    nSamples: header.n_samples,
    durationS: header.n_samples / header.sample_rate,
    levels,
  }
}

export function pickPeakLevel(pyramid: PeakPyramid, samplesPerPixel: number): PeakLevel {
  let chosen = pyramid.levels[0]
  for (const level of pyramid.levels) {
    if (level.samplesPerPeak <= samplesPerPixel) chosen = level
  }
  return chosen
}
