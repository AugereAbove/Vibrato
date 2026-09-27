import { useEffect, useRef, useState } from 'react'
import { micWarning, type Recorder } from '../../audio/recorder'
import { toDb } from '../../lib/wav'
import { Callout } from './Feedback'
import { Icon } from './Icon'

const GAIN_HELP =
  'On Windows: Settings › System › Sound › Input › Volume. On macOS: System Settings › Sound › Input › Input volume.'

function guidance(peakDb: number): { tone: 'good' | 'warn' | 'bad' | 'info'; text: string } {
  if (!Number.isFinite(peakDb) || peakDb < -50)
    return { tone: 'info', text: 'Sing a few notes to check your level.' }
  if (peakDb > -1)
    return { tone: 'bad', text: 'Clipping: turn the microphone volume down or move back a little.' }
  if (peakDb > -6)
    return { tone: 'warn', text: 'Hot: loud notes may clip. Turn the microphone volume down slightly.' }
  if (peakDb < -30)
    return {
      tone: 'warn',
      text: `Quiet: move closer or turn the microphone volume up so peaks reach about −12 dB. ${GAIN_HELP}`,
    }
  return { tone: 'good', text: 'Good level.' }
}

export function InputMeter({ recorder }: { recorder: Recorder | null }) {
  const bar = useRef<HTMLSpanElement>(null)
  const peakBar = useRef<HTMLSpanElement>(null)
  const [peakDb, setPeakDb] = useState(-Infinity)
  const [clipped, setClipped] = useState(false)
  useEffect(() => {
    if (!recorder) return
    let hold = -Infinity
    let holdTime = 0
    let lastUpdate = 0
    return recorder.onLevel((level) => {
      const rmsDb = toDb(level.rms)
      const pDb = toDb(level.peak)
      const now = performance.now()
      if (pDb > hold || now - holdTime > 1200) {
        hold = pDb
        holdTime = now
      }
      const toPct = (db: number) => `${Math.max(0, Math.min(100, ((db + 60) / 60) * 100))}%`
      if (bar.current) bar.current.style.width = toPct(rmsDb)
      if (peakBar.current) peakBar.current.style.left = toPct(hold)
      if (level.peak >= 0.99) setClipped(true)
      if (now - lastUpdate > 250) {
        lastUpdate = now
        setPeakDb(hold)
      }
    })
  }, [recorder])
  const hint = guidance(peakDb)
  return (
    <div className="stack" style={{ gap: 6 }}>
      <div
        className={`meter${clipped ? ' is-clipped' : ''}`}
        role="meter"
        aria-label="Input level"
        aria-valuemin={-60}
        aria-valuemax={0}
        aria-valuenow={Number.isFinite(peakDb) ? Math.round(peakDb) : -60}
      >
        <span ref={bar} className="meter-fill" />
        <span ref={peakBar} className="meter-peak" />
        <span className="meter-scale" aria-hidden>
          <span>−60</span>
          <span>−30</span>
          <span>−12</span>
          <span>0 dB</span>
        </span>
      </div>
      <div className="row small">
        <span className={`${hint.tone}-text`}>
          <Icon name={hint.tone === 'good' ? 'check' : hint.tone === 'info' ? 'info' : 'alert'} size={13} />{' '}
          {hint.text}
        </span>
        <span className="spacer" />
        {clipped ? (
          <button type="button" className="link-button bad-text" onClick={() => setClipped(false)}>
            Clipping detected · reset
          </button>
        ) : null}
      </div>
    </div>
  )
}

export function ActiveMic({ recorder }: { recorder: Recorder | null }) {
  if (!recorder?.isOpen) return null
  const warning = micWarning(recorder.deviceLabel, recorder.deviceSampleRate)
  return (
    <div className="stack" style={{ gap: 6 }}>
      <p className="tiny faint">
        Listening through: <strong>{recorder.deviceLabel || 'unnamed microphone'}</strong>
        {recorder.deviceSampleRate ? ` · ${Math.round(recorder.deviceSampleRate / 1000)} kHz` : ''}
      </p>
      {warning ? (
        <Callout tone="warn" title="Low-quality microphone">
          {warning}
        </Callout>
      ) : null}
    </div>
  )
}
