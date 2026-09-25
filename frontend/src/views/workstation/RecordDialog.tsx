import { useCallback, useEffect, useRef, useState } from 'react'
import type { Recording } from '../../api/types'
import { engine } from '../../audio/engine'
import { PitchTracker } from '../../audio/pitch'
import {
  listInputDevices,
  Recorder,
  scheduleClick,
  trimCapture,
  type CapturedAudio,
} from '../../audio/recorder'
import { cssVar } from '../../components/timeline/useCanvas'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Segmented, Select, Slider, Switch, TextField } from '../../components/ui/Controls'
import { Dialog } from '../../components/ui/Dialog'
import { Callout } from '../../components/ui/Feedback'
import { Icon } from '../../components/ui/Icon'
import { formatSeconds, formatTime } from '../../lib/format'
import { describeHz } from '../../lib/music'
import { encodeWav, peakLevel, toDb } from '../../lib/wav'
import { getPref, setPref, usePref } from '../../state/prefs'
import { navigate, type ProjectTab } from '../../state/router'
import { pushToast } from '../../state/toasts'
import { useWorkspace } from '../../state/workspace'
import { importFile } from './actions'
import { closeRecorder, useRecordStore } from './recordStore'

type Phase = 'setup' | 'countdown' | 'recording' | 'review' | 'saving'

interface Pass {
  samples: Float32Array
  sampleRate: number
  peak: number
  keep: boolean
}

function guidance(peakDb: number): { tone: 'good' | 'warn' | 'bad' | 'info'; text: string } {
  if (!Number.isFinite(peakDb) || peakDb < -50)
    return { tone: 'info', text: 'Sing a few notes to check your level.' }
  if (peakDb > -1)
    return { tone: 'bad', text: 'Clipping: lower the input gain or move back from the microphone.' }
  if (peakDb > -6) return { tone: 'warn', text: 'Hot: loud notes may clip. Lower the gain slightly.' }
  if (peakDb < -30)
    return { tone: 'warn', text: 'Quiet: move closer or raise the input gain so peaks reach about −12 dB.' }
  return { tone: 'good', text: 'Good level.' }
}

function Meter({ recorder }: { recorder: Recorder | null }) {
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

function LivePitch({ recorder }: { recorder: Recorder | null }) {
  const [text, setText] = useState('–')
  useEffect(() => {
    if (!recorder?.analyser) return
    const tracker = new PitchTracker(recorder.analyser)
    const timer = window.setInterval(() => {
      const reading = tracker.read()
      setText(reading.f0 ? describeHz(reading.f0) : '–')
    }, 80)
    return () => window.clearInterval(timer)
  }, [recorder])
  return (
    <div className="live-pitch" aria-live="off">
      <span className="eyebrow">Live pitch</span>
      <span className="num live-pitch-value">{text}</span>
    </div>
  )
}

function Waveform({ samples }: { samples: Float32Array }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const element = canvas.current
    if (!element) return
    const width = element.clientWidth
    const height = element.clientHeight
    const dpr = window.devicePixelRatio || 1
    element.width = width * dpr
    element.height = height * dpr
    const ctx = element.getContext('2d')
    if (!ctx) return
    ctx.scale(dpr, dpr)
    ctx.fillStyle = cssVar('--take')
    const step = Math.max(1, Math.floor(samples.length / width))
    for (let x = 0; x < width; x += 1) {
      let lo = 0
      let hi = 0
      const start = x * step
      for (let i = start; i < Math.min(samples.length, start + step); i += 1) {
        const v = samples[i]
        if (v < lo) lo = v
        if (v > hi) hi = v
      }
      ctx.fillRect(x, height / 2 - hi * (height / 2), 1, Math.max(1, (hi - lo) * (height / 2)))
    }
  }, [samples])
  return <canvas ref={canvas} className="review-wave" aria-label="Recorded waveform" />
}

function trimSuggestion(samples: Float32Array, sampleRate: number): { start: number; end: number } | null {
  const peak = peakLevel(samples)
  if (peak <= 0) return null
  const threshold = peak * 0.02
  let first = 0
  while (first < samples.length && Math.abs(samples[first]) < threshold) first += 1
  let last = samples.length - 1
  while (last > first && Math.abs(samples[last]) < threshold) last -= 1
  const pad = Math.round(0.25 * sampleRate)
  const start = Math.max(0, first - pad) / sampleRate
  const end = Math.min(samples.length, last + pad) / sampleRate
  if (start < 0.6 && samples.length / sampleRate - end < 0.6) return null
  return { start, end }
}

export function RecordDialog({
  projectId,
  reference,
  takes,
  onSaved,
  tab = 'compare',
}: {
  projectId: string
  reference: Recording | null
  takes: Recording[]
  onSaved?: (recording: Recording) => void
  tab?: ProjectTab
}) {
  const open = useRecordStore((s) => s.open)
  const initialRegion = useRecordStore((s) => s.region)
  const [phase, setPhase] = useState<Phase>('setup')
  const [recorder, setRecorder] = useState<Recorder | null>(null)
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([])
  const [error, setError] = useState<string | null>(null)
  const [countdown, setCountdown] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [passes, setPasses] = useState<Pass[]>([])
  const [name, setName] = useState('')
  const [scope, setScope] = useState<'song' | 'region' | 'playhead'>('song')
  const [autoStop, setAutoStop] = useState(false)
  const deviceId = usePref<string | null>('audio.input_device', null)
  const preroll = usePref<number>('audio.preroll_s', 3)
  const metronome = usePref<boolean>('audio.metronome', false)
  const bpm = usePref<number>('audio.metronome_bpm', 84)
  const withReference = usePref<boolean>('audio.reference_during_recording', true)
  const referenceLevel = usePref<number>('audio.reference_level', 0.8)
  const monitorLevel = usePref<number>('audio.monitor_level', 0)
  const loopRecording = usePref<boolean>('audio.loop_recording', false)
  const session = useRef<{
    t0: number
    region: { start: number; end: number } | null
    volume: number
    timer: number
    stopAt: number | null
  } | null>(null)
  const recorderRef = useRef<Recorder | null>(null)

  const region = initialRegion
  const effectiveRegion =
    scope === 'region' && region
      ? region
      : scope === 'playhead'
        ? { start: engine.position(), end: reference?.duration_s ?? engine.timelineDuration() }
        : null

  const openMic = useCallback(async (id: string | null) => {
    setError(null)
    recorderRef.current?.close()
    const next = new Recorder()
    try {
      await next.open(id, getPref<number>('audio.monitor_level', 0))
      recorderRef.current = next
      setRecorder(next)
      setDevices(await listInputDevices())
    } catch (reason) {
      next.close()
      const err = reason as DOMException
      if (err?.name === 'NotAllowedError')
        setError(
          'Microphone access was blocked. Allow microphone access for this page in your browser, then try again.',
        )
      else if (err?.name === 'NotFoundError' || err?.name === 'OverconstrainedError')
        setError('No microphone was found. Connect one, or choose another input device.')
      else setError(err?.message || String(reason))
    }
  }, [])

  useEffect(() => {
    if (!open) return
    const frame = window.requestAnimationFrame(() => {
      setPhase('setup')
      setPasses([])
      setError(null)
      setScope(initialRegion ? 'region' : 'song')
      setName(`Take ${takes.reduce((max, t) => Math.max(max, t.take_number ?? 0), 0) + 1}`)
      void openMic(getPref<string | null>('audio.input_device', null))
    })
    return () => {
      window.cancelAnimationFrame(frame)
      recorderRef.current?.close()
      recorderRef.current = null
      setRecorder(null)
    }
  }, [open, initialRegion, takes, openMic])

  useEffect(() => {
    recorder?.setMonitorLevel(monitorLevel)
  }, [recorder, monitorLevel])

  const finish = useCallback(async () => {
    const current = session.current
    const rec = recorderRef.current
    if (!current || !rec) return
    session.current = null
    window.clearInterval(current.timer)
    let capture: CapturedAudio
    try {
      capture = await rec.stop()
    } catch (reason) {
      setError(String(reason))
      setPhase('setup')
      return
    }
    engine.stop(current.region?.start ?? 0)
    engine.setVolume(current.volume)
    engine.setLoop(useWorkspace.getState().loopEnabled ? useWorkspace.getState().loop : null)
    useRecordStore.setState({ recording: false })
    const body = trimCapture(capture, current.t0)
    const list: Pass[] = []
    if (current.region && getPref<boolean>('audio.loop_recording', false) && withReference) {
      const length = Math.round((current.region.end - current.region.start) * capture.sampleRate)
      for (let offset = 0; offset + length * 0.5 < body.length; offset += length) {
        const samples = body.slice(offset, Math.min(body.length, offset + length))
        list.push({ samples, sampleRate: capture.sampleRate, peak: peakLevel(samples), keep: true })
      }
    } else {
      list.push({ samples: body, sampleRate: capture.sampleRate, peak: peakLevel(body), keep: true })
    }
    const kept = list.filter((p) => p.samples.length > capture.sampleRate * 0.3)
    if (kept.length === 0) {
      pushToast({
        kind: 'warning',
        title: 'Nothing was recorded',
        body: 'Recording stopped during the count-in or lasted less than a third of a second.',
      })
      setPhase('setup')
      return
    }
    setPasses(kept)
    setPhase('review')
  }, [withReference])

  const start = async () => {
    const rec = recorderRef.current
    if (!rec) return
    const ctx = rec.context
    if (ctx.state === 'suspended') await ctx.resume()
    const volume = engine.state.volume
    const target = effectiveRegion
    const lead = Math.max(0, preroll) + 0.15
    rec.start()
    const t0 = ctx.currentTime + lead
    if (metronome) {
      const beat = 60 / Math.max(30, bpm)
      for (let k = 1; t0 - k * beat > ctx.currentTime + 0.05; k += 1)
        scheduleClick(ctx, t0 - k * beat, k % 4 === 0)
    }
    engine.setSpeed(1)
    engine.setAlternate(false)
    if (withReference && reference) {
      engine.setVolume(referenceLevel)
      engine.setMode('ref')
      engine.setLoop(target && loopRecording ? target : null)
      await engine.play(target?.start ?? 0, false, t0)
    }
    const stopAt =
      withReference && reference && !(target && loopRecording)
        ? t0 + ((target ? target.end : reference.duration_s) - (target?.start ?? 0)) + 1.0
        : null
    const timer = window.setInterval(() => {
      const now = ctx.currentTime
      if (now < t0) {
        setPhase('countdown')
        setCountdown(Math.ceil(t0 - now))
      } else {
        setPhase('recording')
        setElapsed(now - t0)
        if (stopAt !== null && now >= stopAt) void finish()
      }
    }, 50)
    session.current = { t0, region: target, volume, timer, stopAt }
    setAutoStop(stopAt !== null)
    useRecordStore.setState({ recording: true })
    setPhase('countdown')
    setCountdown(Math.ceil(lead))
  }

  const cancelRecording = async () => {
    const current = session.current
    if (current) {
      window.clearInterval(current.timer)
      session.current = null
      engine.stop(current.region?.start ?? 0)
      engine.setVolume(current.volume)
      await recorderRef.current?.stop().catch(() => undefined)
    }
    useRecordStore.setState({ recording: false })
    setPhase('setup')
  }

  const save = async () => {
    const chosen = passes.filter((p) => p.keep)
    if (chosen.length === 0) return
    setPhase('saving')
    const target = session.current?.region ?? effectiveRegion
    const latencyCalibrated = getPref<boolean>('audio.latency_calibrated', false)
    const ctx = recorderRef.current?.context
    const estimated = ctx
      ? ((ctx.baseLatency ?? 0) + (ctx.outputLatency ?? 0) + (recorderRef.current?.inputLatency ?? 0)) * 1000
      : 0
    const latencyMs = latencyCalibrated ? getPref<number>('audio.latency_ms', 0) : Math.round(estimated)
    const synced = withReference && Boolean(reference) && (!target || target.start < 0.01)
    let last: Recording | null = null
    for (const [index, pass] of chosen.entries()) {
      const blob = encodeWav(pass.samples, pass.sampleRate)
      const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
      const takeName = chosen.length > 1 ? `${name} (${index + 1})` : name
      last = await importFile(
        projectId,
        blob,
        `take-${stamp}.wav`,
        {
          kind: 'take',
          name: takeName,
          referenceId: reference?.id ?? null,
          synced,
          latencyMs: withReference ? latencyMs : 0,
          regionStart: target && !synced ? target.start : null,
          regionEnd: target && !synced ? target.end : null,
          source: 'record',
        },
        (recording) => {
          onSaved?.(recording)
        },
      )
    }
    closeRecorder()
    if (last) {
      pushToast({
        kind: 'info',
        title: `${last.name} saved`,
        body: 'Analysing and comparing with the reference…',
      })
      navigate({ name: 'project', projectId, tab, take: last.id })
    }
  }

  const close = () => {
    if (phase === 'recording' || phase === 'countdown') void cancelRecording()
    closeRecorder()
  }

  const playPass = (pass: Pass) => {
    const ctx = engine.audioContext()
    const buffer = ctx.createBuffer(1, pass.samples.length, pass.sampleRate)
    buffer.copyToChannel(new Float32Array(pass.samples), 0)
    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.connect(ctx.destination)
    source.start()
  }

  const recordingActive = phase === 'countdown' || phase === 'recording'
  return (
    <Dialog
      open={open}
      onClose={close}
      width={620}
      title={phase === 'review' ? 'Review your take' : 'Record a take'}
      description={
        reference
          ? `Compared with “${reference.name}” when you keep it.`
          : 'No reference yet: the take will only be analysed.'
      }
      footer={
        phase === 'review' || phase === 'saving' ? (
          <>
            <Button variant="ghost" icon="trash" onClick={close}>
              Discard
            </Button>
            <Button variant="secondary" icon="refresh" onClick={() => setPhase('setup')}>
              Retry
            </Button>
            <Button
              variant="primary"
              icon="check"
              onClick={() => void save()}
              loading={phase === 'saving'}
              disabled={!passes.some((p) => p.keep)}
            >
              Keep and analyse
            </Button>
          </>
        ) : recordingActive ? (
          <>
            <Button variant="ghost" onClick={() => void cancelRecording()}>
              Cancel
            </Button>
            <Button variant="danger" icon="stop" onClick={() => void finish()} data-autofocus>
              Stop recording
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={close}>
              Close
            </Button>
            <Button
              variant="primary"
              icon="record"
              onClick={() => void start()}
              disabled={!recorder}
              data-autofocus
            >
              Start recording
            </Button>
          </>
        )
      }
    >
      {error ? (
        <Callout tone="bad" title="The microphone is not available">
          {error}
          <div style={{ marginTop: 8 }}>
            <Button size="sm" icon="refresh" onClick={() => void openMic(deviceId)}>
              Try again
            </Button>
          </div>
        </Callout>
      ) : null}
      {phase === 'setup' ? (
        <div className="record-setup">
          <div className="record-grid">
            <Select
              label="Microphone"
              value={deviceId ?? ''}
              onChange={(value) => {
                setPref('audio.input_device', value || null)
                void openMic(value || null)
              }}
              options={[
                { value: '', label: 'System default' },
                ...devices.map((d, i) => ({ value: d.deviceId, label: d.label || `Input ${i + 1}` })),
              ]}
            />
            <LivePitch recorder={recorder} />
          </div>
          <Meter recorder={recorder} />
          <Segmented
            ariaLabel="What to record"
            value={scope}
            onChange={setScope}
            options={[
              { value: 'song', label: 'Whole song' },
              {
                value: 'region',
                label: region
                  ? `Loop ${formatTime(region.start, 1)}–${formatTime(region.end, 1)}`
                  : 'Loop region',
                disabled: !region,
              },
              { value: 'playhead', label: 'From playhead' },
            ]}
          />
          <div className="record-options">
            <Switch
              checked={withReference}
              onChange={(v) => setPref('audio.reference_during_recording', v)}
              label="Play the reference while recording"
              description="Use headphones so the reference is not recorded."
              disabled={!reference}
            />
            {withReference && reference ? (
              <Slider
                label="Reference level"
                value={referenceLevel}
                min={0}
                max={1}
                step={0.05}
                format={(v) => `${Math.round(v * 100)}%`}
                onChange={(v) => setPref('audio.reference_level', v)}
              />
            ) : null}
            <Slider
              label="Hear yourself (monitor)"
              value={monitorLevel}
              min={0}
              max={1}
              step={0.05}
              format={(v) => (v === 0 ? 'off' : `${Math.round(v * 100)}%`)}
              onChange={(v) => setPref('audio.monitor_level', v)}
            />
            <div className="row">
              <div style={{ width: 150 }}>
                <Slider
                  label="Count-in"
                  value={preroll}
                  min={0}
                  max={8}
                  step={1}
                  format={(v) => `${v} s`}
                  onChange={(v) => setPref('audio.preroll_s', v)}
                />
              </div>
              <Switch
                checked={metronome}
                onChange={(v) => setPref('audio.metronome', v)}
                label={`Metronome clicks (${bpm} BPM)`}
              />
            </div>
            {scope === 'region' ? (
              <Switch
                checked={loopRecording}
                onChange={(v) => setPref('audio.loop_recording', v)}
                label="Loop recording"
                description="Keep singing: each pass through the loop becomes its own take."
              />
            ) : null}
          </div>
          {monitorLevel > 0 ? (
            <Callout tone="warn" title="Use headphones while monitoring">
              Monitoring through speakers causes feedback and puts the reference into your take.
            </Callout>
          ) : null}
          <p className="tiny faint">
            Latency compensation:{' '}
            {getPref<boolean>('audio.latency_calibrated', false)
              ? `${getPref<number>('audio.latency_ms', 0)} ms (measured)`
              : 'estimated automatically'}{' '}
            — measure it in Settings › Audio for tighter timing.
          </p>
        </div>
      ) : null}
      {recordingActive ? (
        <div className="record-live">
          {phase === 'countdown' ? (
            <div className="countdown" aria-live="assertive">
              <span key={countdown} className="countdown-number">
                {countdown}
              </span>
              <span className="muted">Get ready…</span>
            </div>
          ) : (
            <div className="recording-status" aria-live="polite">
              <span className="rec-dot" aria-hidden />
              <strong>Recording</strong>
              <span className="num">{formatSeconds(elapsed, 1)}</span>
              {autoStop ? <span className="faint small">stops automatically at the end</span> : null}
            </div>
          )}
          <Meter recorder={recorder} />
          <LivePitch recorder={recorder} />
        </div>
      ) : null}
      {phase === 'review' || phase === 'saving' ? (
        <div className="record-review">
          <TextField label="Name" value={name} onChange={(event) => setName(event.target.value)} />
          {passes.map((pass, index) => {
            const suggestion = trimSuggestion(pass.samples, pass.sampleRate)
            const peakDb = toDb(pass.peak)
            return (
              <div key={index} className="review-pass card card-pad">
                <div className="row">
                  {passes.length > 1 ? (
                    <Switch
                      checked={pass.keep}
                      onChange={(keep) =>
                        setPasses((list) => list.map((p, i) => (i === index ? { ...p, keep } : p)))
                      }
                      label={`Pass ${index + 1}`}
                    />
                  ) : null}
                  <span className="num small">{formatSeconds(pass.samples.length / pass.sampleRate, 1)}</span>
                  <Badge tone={peakDb > -1 ? 'bad' : peakDb < -30 ? 'warn' : 'good'}>
                    peak {peakDb.toFixed(1)} dBFS
                  </Badge>
                  <span className="spacer" />
                  <Button size="sm" variant="ghost" icon="play" onClick={() => playPass(pass)}>
                    Listen
                  </Button>
                </div>
                <Waveform samples={pass.samples} />
                {suggestion ? (
                  <p className="tiny faint">
                    Suggested trim: {formatSeconds(suggestion.start, 1)} – {formatSeconds(suggestion.end, 1)}{' '}
                    (silence at the edges is ignored by the analysis).
                  </p>
                ) : null}
                {peakDb > -1 ? (
                  <p className="tiny bad-text">
                    This take clipped. Pitch and voice-quality measurements will have lower confidence.
                  </p>
                ) : null}
              </div>
            )
          })}
        </div>
      ) : null}
    </Dialog>
  )
}
