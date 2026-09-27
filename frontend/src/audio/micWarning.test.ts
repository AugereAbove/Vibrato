import { describe, expect, it } from 'vitest'
import { micWarning } from './recorder'

describe('micWarning', () => {
  it.each([
    'Headset Microphone (WH-1000XM4 Hands-Free AG Audio)',
    'Default - Headset (AirPods Pro)',
    'Galaxy Buds2 Pro',
    'Bluetooth Microphone',
    'Microphone (JBL BT HFP)',
  ])('flags headset/Bluetooth mic %s', (label) => {
    expect(micWarning(label)).not.toBeNull()
  })

  it.each([
    'Microphone Array (Realtek(R) Audio)',
    'Communications - Microphone Array (Intel® Smart Sound Technology)',
    'MacBook Pro Microphone',
    'Blue Yeti Stereo Microphone',
    'Focusrite USB Audio',
    '',
  ])('does not flag %s', (label) => {
    expect(micWarning(label, 48000)).toBeNull()
  })

  it('flags narrowband sample rates regardless of name', () => {
    expect(micWarning('Microphone', 16000)).not.toBeNull()
    expect(micWarning('Microphone', 44100)).toBeNull()
  })
})
