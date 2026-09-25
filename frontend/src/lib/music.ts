export const NOTE_NAMES = ['C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B'] as const

export function hzToMidi(hz: number, a4 = 440): number {
  return 69 + 12 * Math.log2(hz / a4)
}

export function midiToHz(midi: number, a4 = 440): number {
  return a4 * 2 ** ((midi - 69) / 12)
}

export function noteName(midi: number, withOctave = true): string {
  const rounded = Math.round(midi)
  const name = NOTE_NAMES[((rounded % 12) + 12) % 12]
  if (!withOctave) return name
  return `${name}${Math.floor(rounded / 12) - 1}`
}

export function isBlackKey(midi: number): boolean {
  const pitchClass = ((Math.round(midi) % 12) + 12) % 12
  return pitchClass === 1 || pitchClass === 3 || pitchClass === 6 || pitchClass === 8 || pitchClass === 10
}

export function centsOff(midi: number): number {
  return (midi - Math.round(midi)) * 100
}

export function describeMidi(midi: number): string {
  const cents = Math.round(centsOff(midi))
  const sign = cents > 0 ? '+' : cents < 0 ? '−' : '±'
  return `${noteName(midi)} ${sign}${Math.abs(cents)}¢`
}

export function describeHz(hz: number, a4 = 440): string {
  return describeMidi(hzToMidi(hz, a4))
}
