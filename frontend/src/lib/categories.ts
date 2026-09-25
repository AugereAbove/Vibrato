import type { CategoryId } from '../api/types'

export const CATEGORY_ORDER: CategoryId[] = [
  'pitch',
  'timing',
  'vowel',
  'vibrato',
  'dynamics',
  'phonation',
  'articulation',
  'breath',
  'timbre',
]

export const CATEGORY_LABELS: Record<CategoryId, string> = {
  pitch: 'Pitch',
  timing: 'Timing',
  vowel: 'Vowels',
  vibrato: 'Vibrato',
  dynamics: 'Dynamics',
  phonation: 'Phonation',
  articulation: 'Articulation',
  breath: 'Breath',
  timbre: 'Timbre',
}

export const CATEGORY_ICONS: Record<CategoryId, string> = {
  pitch: 'pitch',
  timing: 'clock',
  vowel: 'vowel',
  vibrato: 'vibrato',
  dynamics: 'dynamics',
  phonation: 'phonation',
  articulation: 'articulation',
  breath: 'breath',
  timbre: 'timbre',
}

export const CATEGORY_LAYERS: Record<CategoryId, LayerId[]> = {
  pitch: ['pitch'],
  timing: ['waveform', 'lyrics'],
  vowel: ['formants', 'spectrogram', 'lyrics'],
  vibrato: ['pitch'],
  dynamics: ['loudness', 'waveform'],
  phonation: ['voice', 'spectrogram'],
  articulation: ['phonemes', 'waveform'],
  breath: ['events', 'waveform'],
  timbre: ['spectrogram'],
}

export function categoryLabel(id: string): string {
  return CATEGORY_LABELS[id as CategoryId] ?? id.charAt(0).toUpperCase() + id.slice(1)
}

export type LayerId =
  | 'lyrics'
  | 'phonemes'
  | 'waveform'
  | 'pitch'
  | 'spectrogram'
  | 'formants'
  | 'loudness'
  | 'voice'
  | 'events'
  | 'heatmap'
  | 'alignment'
  | 'confidence'

export interface LayerInfo {
  id: LayerId
  label: string
  description: string
  modes: ('coach' | 'analyst' | 'research')[]
}

export const LAYERS: LayerInfo[] = [
  {
    id: 'lyrics',
    label: 'Lyrics',
    description: 'Words and syllables of both performances',
    modes: ['coach', 'analyst', 'research'],
  },
  {
    id: 'phonemes',
    label: 'Phonemes',
    description: 'Phoneme and acoustic-class lane',
    modes: ['analyst', 'research'],
  },
  {
    id: 'waveform',
    label: 'Waveform',
    description: 'Reference and take waveforms',
    modes: ['coach', 'analyst', 'research'],
  },
  {
    id: 'pitch',
    label: 'Pitch',
    description: 'Pitch contours on a piano roll with notes and vibrato',
    modes: ['coach', 'analyst', 'research'],
  },
  {
    id: 'spectrogram',
    label: 'Spectrogram',
    description: 'Time–frequency energy of the selected recording',
    modes: ['analyst', 'research'],
  },
  {
    id: 'formants',
    label: 'Formants',
    description: 'F1–F3 tracks drawn over the spectrogram',
    modes: ['analyst', 'research'],
  },
  {
    id: 'loudness',
    label: 'Loudness',
    description: 'Loudness envelopes of both performances',
    modes: ['analyst', 'research'],
  },
  { id: 'voice', label: 'Voice quality', description: 'CPPS and harmonicity tracks', modes: ['research'] },
  {
    id: 'events',
    label: 'Events',
    description: 'Breaths, vibrato, scoops, onsets and consonants',
    modes: ['analyst', 'research'],
  },
  {
    id: 'heatmap',
    label: 'Difference heatmap',
    description: 'Where each category differs most',
    modes: ['coach', 'analyst', 'research'],
  },
  {
    id: 'alignment',
    label: 'Alignment',
    description: 'Alignment confidence and anchors',
    modes: ['research'],
  },
  {
    id: 'confidence',
    label: 'Confidence overlay',
    description: 'Dim regions where measurements are unreliable',
    modes: ['analyst', 'research'],
  },
]

export function defaultLayers(mode: 'coach' | 'analyst' | 'research'): Record<LayerId, boolean> {
  const result = {} as Record<LayerId, boolean>
  for (const layer of LAYERS) result[layer.id] = layer.modes.includes(mode)
  return result
}

export const BACKEND_LAYER_MAP: Record<string, LayerId[]> = {
  waveform: ['waveform'],
  pitch: ['pitch'],
  vibrato: ['pitch'],
  formants: ['formants', 'spectrogram'],
  spectrogram: ['spectrogram'],
  loudness: ['loudness'],
  phonetic: ['phonemes', 'lyrics'],
  breath: ['events'],
  confidence: ['confidence'],
  vowel_space: [],
}

export const BASIS_LABELS: Record<string, string> = {
  measured: 'Measured',
  derived: 'Derived',
  inferred: 'Inferred',
  experimental: 'Experimental',
  stylistic: 'Stylistic suggestion',
}

export const BASIS_HELP: Record<string, string> = {
  measured: 'Read directly from the audio signal.',
  derived: 'Calculated from measured values (for example a normalised or combined quantity).',
  inferred:
    'A likely physical or perceptual interpretation of the measurements. It is not directly observed.',
  experimental: 'Produced by an experimental method; treat it as a hint.',
  stylistic: 'A practice suggestion based on common vocal pedagogy, not a measurement.',
}
