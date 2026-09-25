import { useEffect, useRef, useState } from 'react'
import { calibrationApi } from '../../api/endpoints'
import type { CalibrationProfile, CalibrationStep } from '../../api/types'
import { Recorder, trimCapture } from '../../audio/recorder'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { confirmAction } from '../../components/ui/confirm'
import { Callout, EmptyState, ErrorState, ProgressBar, SkeletonLines } from '../../components/ui/Feedback'
import { Icon } from '../../components/ui/Icon'
import { describeApi } from './describe'
import { formatDate, formatNumber } from '../../lib/format'
import { describeHz } from '../../lib/music'
import { encodeWav } from '../../lib/wav'
import { keys, useCalibrations, useCalibrationSteps } from '../../state/data'
import { attempt, reportError } from '../../state/errors'
import { getPref } from '../../state/prefs'
import { invalidate, useResource } from '../../state/resource'

function StepResult({ results }: { results: Record<string, unknown> }) {
  const entries: [string, string][] = []
  const num = (key: string) => (typeof results[key] === 'number' ? (results[key] as number) : null)
  if (num('noise_floor_dbfs') !== null)
    entries.push(['Noise floor', `${formatNumber(num('noise_floor_dbfs'), 1)} dBFS`])
  if (num('median_f0_hz') !== null) entries.push(['Pitch', describeHz(num('median_f0_hz') as number)])
  for (const k of [1, 2, 3])
    if (num(`f${k}_hz`) !== null) entries.push([`F${k}`, `${formatNumber(num(`f${k}_hz`), 0)} Hz`])
  if (num('cpps_db') !== null) entries.push(['CPPS', `${formatNumber(num('cpps_db'), 1)} dB`])
  if (num('breathiness_index') !== null)
    entries.push(['Breathiness', formatNumber(num('breathiness_index'), 0)])
  if (results.vibrato_present !== undefined)
    entries.push([
      'Vibrato',
      results.vibrato_present
        ? `${formatNumber(num('vibrato_rate_hz'), 2)} Hz, ±${formatNumber(num('vibrato_extent_cents'), 0)}¢`
        : 'none',
    ])
  if (num('pitch_std_cents') !== null)
    entries.push(['Pitch spread', `${formatNumber(num('pitch_std_cents'), 1)}¢`])
  return (
    <dl className="kv step-result">
      {entries.map(([k, v]) => (
        <div key={k} style={{ display: 'contents' }}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  )
}

function StepCard({
  step,
  index,
  profile,
  onDone,
}: {
  step: CalibrationStep
  index: number
  profile: CalibrationProfile
  onDone: () => void
}) {
  const sample = profile.samples?.find((s) => s.step === step.id)
  const [state, setState] = useState<'idle' | 'countdown' | 'recording' | 'uploading'>('idle')
  const [count, setCount] = useState(0)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const recorder = useRef<Recorder | null>(null)
  useEffect(
    () => () => {
      recorder.current?.close()
    },
    [],
  )
  const record = async () => {
    setError(null)
    const rec = new Recorder()
    recorder.current = rec
    try {
      await rec.open(getPref<string | null>('audio.input_device', null), 0)
    } catch (reason) {
      rec.close()
      setError(reason instanceof Error ? reason.message : String(reason))
      return
    }
    const ctx = rec.context
    rec.start()
    const t0 = ctx.currentTime + 2.2
    const t1 = t0 + step.seconds + 0.3
    setState('countdown')
    await new Promise<void>((resolve) => {
      const timer = window.setInterval(() => {
        const now = ctx.currentTime
        if (now < t0) {
          setState('countdown')
          setCount(Math.ceil(t0 - now))
        } else if (now < t1) {
          setState('recording')
          setProgress((now - t0) / (t1 - t0))
        } else {
          window.clearInterval(timer)
          resolve()
        }
      }, 50)
    })
    const capture = await rec.stop()
    rec.close()
    recorder.current = null
    setState('uploading')
    const samples = trimCapture(capture, t0, t1)
    try {
      await calibrationApi.addSample(profile.id, step.id, encodeWav(samples, capture.sampleRate))
      onDone()
    } catch (reason) {
      setError(describeApi(reason))
    } finally {
      setState('idle')
    }
  }
  return (
    <div className={`step-card card${sample ? ' is-done' : ''}`}>
      <div className="row">
        <span className="step-number">{sample ? <Icon name="check" size={12} /> : index + 1}</span>
        <strong className="grow">{step.title}</strong>
        {step.optional ? <Badge>optional</Badge> : null}
        <Badge>{step.group}</Badge>
      </div>
      <p className="small muted">{step.instruction}</p>
      {state === 'countdown' ? <div className="step-countdown">Starting in {count}…</div> : null}
      {state === 'recording' ? (
        <div className="stack" style={{ gap: 4 }}>
          <span className="small">
            <span className="rec-dot" /> Recording {step.seconds} s
          </span>
          <ProgressBar value={progress} tone="bad" label="Recording progress" />
        </div>
      ) : null}
      {state === 'uploading' ? <ProgressBar indeterminate label="Measuring" /> : null}
      {error ? <Callout tone="bad">{error}</Callout> : null}
      {sample?.results ? <StepResult results={sample.results} /> : null}
      <div className="row">
        <Button
          size="sm"
          variant={sample ? 'ghost' : 'secondary'}
          icon="record"
          onClick={() => void record()}
          disabled={state !== 'idle' || profile.status === 'complete'}
        >
          {sample ? 'Record again' : 'Record'}
        </Button>
      </div>
    </div>
  )
}

function VowelMap({ map }: { map: Record<string, { f1: number; f2: number; f3: number }> }) {
  const entries = Object.entries(map)
  if (entries.length === 0) return null
  const f1s = entries.map(([, v]) => v.f1)
  const f2s = entries.map(([, v]) => v.f2)
  const W = 300
  const H = 200
  const f1lo = Math.min(...f1s) * 0.85
  const f1hi = Math.max(...f1s) * 1.15
  const f2lo = Math.min(...f2s) * 0.85
  const f2hi = Math.max(...f2s) * 1.15
  const x = (f2: number) => 20 + ((f2hi - f2) / (f2hi - f2lo)) * (W - 40)
  const y = (f1: number) => 15 + ((f1 - f1lo) / (f1hi - f1lo)) * (H - 35)
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="vowel-chart small-chart"
      role="img"
      aria-label="Your vowel map (F1 against F2)"
    >
      {entries.map(([vowel, v]) => (
        <g key={vowel} transform={`translate(${x(v.f2)}, ${y(v.f1)})`} className="vowel-point take">
          <circle r={5} />
          <text y={-8} textAnchor="middle">
            {vowel}
          </text>
        </g>
      ))}
      <text x={W / 2} y={H - 4} textAnchor="middle" className="chart-title">
        F2 front ← → back · F1 ↓ open
      </text>
    </svg>
  )
}

function Results({ profile }: { profile: CalibrationProfile }) {
  const r = profile.results ?? {}
  return (
    <div className="calibration-results">
      <div className="card card-pad stack" style={{ gap: 6 }}>
        <span className="eyebrow">Range</span>
        <p className="num">
          {r.range?.low_hz ? describeHz(r.range.low_hz) : '–'} →{' '}
          {r.range?.high_hz ? describeHz(r.range.high_hz) : '–'}
        </p>
        <p className="small muted">
          {r.range?.semitones
            ? `${r.range.semitones.toFixed(1)} semitones measured`
            : 'Record both range steps to measure it.'}
        </p>
      </div>
      <div className="card card-pad stack" style={{ gap: 6 }}>
        <span className="eyebrow">Vibrato tendency</span>
        <p className="num">
          {r.vibrato?.present
            ? `${formatNumber(r.vibrato.rate_hz, 2)} Hz · ±${formatNumber(r.vibrato.extent_cents, 0)}¢`
            : r.vibrato
              ? 'No regular vibrato detected'
              : '–'}
        </p>
        <p className="small muted">
          Straight tone spread {formatNumber(r.straight_tone?.pitch_std_cents, 1)}¢
          {r.straight_tone?.vibrato_leak ? ' (some vibrato crept in)' : ''}
        </p>
      </div>
      <div className="card card-pad stack" style={{ gap: 6 }}>
        <span className="eyebrow">Breathy vs clear</span>
        <table className="data-table compact">
          <thead>
            <tr>
              <th scope="col" />
              <th scope="col">Breathy</th>
              <th scope="col">Clear</th>
            </tr>
          </thead>
          <tbody>
            {['cpps_db', 'hnr_db', 'h1h2_db', 'breathiness_index'].map((key) => (
              <tr key={key}>
                <th scope="row">{key.replace('_db', '').replace('_', ' ').toUpperCase()}</th>
                <td className="num">{formatNumber(r.phonation?.breathy?.[key] ?? null, 1)}</td>
                <td className="num">{formatNumber(r.phonation?.modal?.[key] ?? null, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card card-pad stack" style={{ gap: 6 }}>
        <span className="eyebrow">Vowel map</span>
        {r.vowel_map && Object.keys(r.vowel_map).length ? (
          <VowelMap map={r.vowel_map} />
        ) : (
          <p className="small muted">Record the vowel steps to build it.</p>
        )}
        <p className="small muted">Noise floor {formatNumber(r.noise_floor_dbfs ?? null, 1)} dBFS</p>
      </div>
      {r.note ? (
        <p className="tiny faint" style={{ gridColumn: '1 / -1' }}>
          {r.note}
        </p>
      ) : null}
    </div>
  )
}

export function CalibrationView() {
  const calibrations = useCalibrations()
  const steps = useCalibrationSteps()
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [compare, setCompare] = useState<string[]>([])
  const list = calibrations.data?.calibrations ?? []
  const active = calibrations.data?.active ?? null
  const selectedId =
    currentId ?? list.find((c) => c.status === 'in_progress')?.id ?? active?.id ?? list[0]?.id ?? null
  const detail = useResource(selectedId ? `calibration:${selectedId}` : null, () =>
    calibrationApi.get(selectedId as string).then((r) => r.calibration),
  )
  const comparison = useResource(
    compare.length === 2 ? `calibration-compare:${compare.join(',')}` : null,
    () => calibrationApi.compare(compare).then((r) => r.profiles),
  )
  const refresh = () => {
    invalidate(keys.calibrations)
    if (selectedId) invalidate(`calibration:${selectedId}`)
  }
  const profile = detail.data
  const required = (steps.data ?? []).filter((s) => !s.optional)
  const done = profile?.samples?.map((s) => s.step) ?? []
  const missing = required.filter((s) => !done.includes(s.id))
  return (
    <div className="page calibration">
      <div className="page-inner wide">
        <div className="page-header">
          <div>
            <h1>Voice calibration</h1>
            <p className="muted">
              A short set of sustained sounds that describes how your voice behaves today: vowel positions,
              range, vibrato and breathy versus clear tone. Vibrato uses it to normalise vowel comparisons.
              Recalibrate whenever your voice, room or microphone changes — a baseline is not a fixed
              description of your anatomy.
            </p>
          </div>
          <Button
            variant="primary"
            icon="plus"
            onClick={async () => {
              const created = await attempt(
                () => calibrationApi.create(`Calibration ${new Date().toLocaleDateString()}`),
                'Calibration could not start',
              )
              if (created) {
                setCurrentId(created.calibration.id)
                refresh()
              }
            }}
          >
            New calibration
          </Button>
        </div>
        {calibrations.error ? (
          <ErrorState error={calibrations.error} onRetry={() => void calibrations.refresh()} />
        ) : null}
        <div className="calibration-layout">
          <aside className="card calibration-list">
            <div className="panel-header">
              <span className="panel-title">Sessions</span>
            </div>
            {list.length === 0 ? <p className="side-hint">No calibrations yet.</p> : null}
            {list.map((c) => (
              <div key={c.id} className="row" style={{ paddingRight: 8 }}>
                <input
                  type="checkbox"
                  aria-label={`Select ${c.name} for comparison`}
                  checked={compare.includes(c.id)}
                  disabled={c.status !== 'complete'}
                  onChange={(e) =>
                    setCompare((current) =>
                      e.target.checked ? [...current, c.id].slice(-2) : current.filter((id) => id !== c.id),
                    )
                  }
                />
                <button
                  type="button"
                  className={`side-item grow${c.id === selectedId ? ' is-active' : ''}`}
                  onClick={() => setCurrentId(c.id)}
                >
                  <span className="grow stack" style={{ gap: 0 }}>
                    <span className="truncate">{c.name}</span>
                    <span className="tiny faint">
                      {c.status === 'complete' ? `finished ${formatDate(c.finalized_at)}` : 'in progress'}
                    </span>
                  </span>
                  {c.is_active ? <Badge tone="good">active</Badge> : null}
                </button>
              </div>
            ))}
            <p className="tiny faint" style={{ padding: 10 }}>
              Tick two finished sessions to compare them.
            </p>
          </aside>
          <section className="stack" style={{ gap: 12, minWidth: 0 }}>
            {comparison.data && compare.length === 2 ? (
              <div className="card card-pad">
                <h3>Comparing two calibrations</h3>
                <table className="data-table compact">
                  <thead>
                    <tr>
                      <th scope="col">Measure</th>
                      {comparison.data.map((p) => (
                        <th key={String(p.id)} scope="col">
                          {String(p.name)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      [
                        'Vibrato rate (Hz)',
                        (p: Record<string, unknown>) =>
                          formatNumber((p.vibrato as { rate_hz?: number } | null)?.rate_hz ?? null, 2),
                      ],
                      [
                        'Vibrato width (¢)',
                        (p: Record<string, unknown>) =>
                          formatNumber(
                            (p.vibrato as { extent_cents?: number } | null)?.extent_cents ?? null,
                            0,
                          ),
                      ],
                      [
                        'Range (semitones)',
                        (p: Record<string, unknown>) =>
                          formatNumber((p.range as { semitones?: number } | null)?.semitones ?? null, 1),
                      ],
                      [
                        'Noise floor (dBFS)',
                        (p: Record<string, unknown>) =>
                          formatNumber((p.noise_floor_dbfs as number | null) ?? null, 1),
                      ],
                    ].map(([label, get]) => (
                      <tr key={label as string}>
                        <th scope="row">{label as string}</th>
                        {comparison.data!.map((p) => (
                          <td key={String(p.id)} className="num">
                            {(get as (p: Record<string, unknown>) => string)(p)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            {!selectedId ? (
              <EmptyState icon="gauge" title="No calibration yet">
                Start a calibration: it takes about three minutes and needs a quiet room.
              </EmptyState>
            ) : detail.loading || steps.loading ? (
              <SkeletonLines lines={6} />
            ) : profile ? (
              <>
                <div className="card card-pad row-wrap">
                  <div className="grow">
                    <h3>{profile.name}</h3>
                    <p className="small muted">
                      {profile.status === 'complete'
                        ? `Finished ${formatDate(profile.finalized_at)}`
                        : `${done.length} of ${(steps.data ?? []).length} steps recorded${missing.length ? ` · ${missing.length} required step${missing.length === 1 ? '' : 's'} left` : ''}`}
                    </p>
                  </div>
                  {profile.status !== 'complete' ? (
                    <Button
                      variant="primary"
                      icon="check"
                      disabled={missing.length > 0}
                      onClick={async () => {
                        const result = await attempt(
                          () => calibrationApi.finalize(profile.id),
                          'Calibration could not be finished',
                        )
                        if (result) refresh()
                      }}
                    >
                      Finish calibration
                    </Button>
                  ) : profile.is_active ? (
                    <Button
                      variant="ghost"
                      onClick={async () => {
                        await attempt(() => calibrationApi.deactivate(), 'Could not deactivate')
                        refresh()
                      }}
                    >
                      Stop using as baseline
                    </Button>
                  ) : (
                    <Button
                      variant="primary"
                      icon="check"
                      onClick={async () => {
                        await attempt(() => calibrationApi.activate(profile.id), 'Could not activate')
                        refresh()
                      }}
                    >
                      Use as my baseline
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    icon="trash"
                    onClick={async () => {
                      const ok = await confirmAction({
                        title: `Delete “${profile.name}”?`,
                        body: 'Its sample recordings are deleted too.',
                        danger: true,
                        confirmLabel: 'Delete',
                      })
                      if (!ok) return
                      try {
                        await calibrationApi.remove(profile.id)
                        setCurrentId(null)
                        refresh()
                      } catch (error) {
                        reportError(error, 'Delete failed')
                      }
                    }}
                  >
                    Delete
                  </Button>
                </div>
                {profile.status === 'complete' ? <Results profile={profile} /> : null}
                <div className="step-grid">
                  {(steps.data ?? []).map((step, index) => (
                    <StepCard key={step.id} step={step} index={index} profile={profile} onDone={refresh} />
                  ))}
                </div>
              </>
            ) : null}
          </section>
        </div>
      </div>
    </div>
  )
}
