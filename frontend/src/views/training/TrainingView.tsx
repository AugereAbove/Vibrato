import { useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { projectsApi } from '../../api/endpoints'
import type { Finding, Segment, Session } from '../../api/types'
import { engine } from '../../audio/engine'
import { Recorder } from '../../audio/recorder'
import { Badge, CategoryChip, ConfidenceBadge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Switch, TextArea } from '../../components/ui/Controls'
import { Callout, EmptyState } from '../../components/ui/Feedback'
import { Icon } from '../../components/ui/Icon'
import { ScoreRing } from '../../components/ui/Motion'
import { numberValue, resultFor } from '../../lib/analysis'
import { formatDuration, formatSigned, formatTime } from '../../lib/format'
import { describeMidi } from '../../lib/music'
import { useProgress } from '../../state/data'
import { attempt } from '../../state/errors'
import { getPref, setPref, usePref, type ViewMode } from '../../state/prefs'
import { useWorkspace } from '../../state/workspace'
import { loopRegion } from '../workstation/actions'
import { ImportDialog } from '../workstation/ImportDialog'
import { RecordDialog } from '../workstation/RecordDialog'
import { openRecorder } from '../workstation/recordStore'
import type { WorkstationData } from '../workstation/useWorkstation'
import { LivePitchCanvas, type LiveReading } from './LivePitchCanvas'

function useClock(): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  return now
}

function findingInPhrase(findings: Finding[], phrase: Segment): Finding[] {
  return findings.filter(
    (f) => f.practice && f.practice.ref_start < phrase.end_s && f.practice.ref_end > phrase.start_s,
  )
}

export function TrainingView({
  data,
  mode,
  theme,
}: {
  data: WorkstationData
  mode: ViewMode
  theme: 'dark' | 'light'
}) {
  const phrases = useMemo(() => data.refIndex?.byLevel.phrase ?? [], [data.refIndex])
  const nextFocus = data.comparison?.coaching.next_focus ?? null
  const focusPhrase = nextFocus?.loop?.phrase_id ?? null
  const [phraseId, setPhraseId] = useState<string | null>(null)
  const phrase = phrases.find((p) => p.id === (phraseId ?? focusPhrase)) ?? phrases[0] ?? null
  const findings = useMemo(
    () => (phrase && data.comparison ? findingInPhrase(data.comparison.coaching.findings, phrase) : []),
    [phrase, data.comparison],
  )
  const [targetKey, setTargetKey] = useState<string | null>(null)
  const target =
    findings.find((f) => f.key === targetKey) ??
    findings.find((f) => f.key === nextFocus?.finding_key) ??
    findings[0] ??
    null
  const autoLoop = usePref<boolean>('training.auto_loop', true)
  const slow = usePref<number>('training.slow_factor', 0.75)
  const alternate = usePref<boolean>('training.alternate_ab', false)
  const mastery = usePref<number>('training.mastery_threshold', 85)
  const minTakes = usePref<number>('training.min_takes_before_move_on', 3)
  const engineState = useSyncExternalStore(engine.subscribe, engine.getState, engine.getState)
  const progress = useProgress(data.projectId, data.reference?.id ?? null)
  const [session, setSession] = useState<Session | null>(null)
  const [notes, setNotes] = useState('')
  const [recorder, setRecorder] = useState<Recorder | null>(null)
  const [micError, setMicError] = useState<string | null>(null)
  const [reading, setReading] = useState<LiveReading>({ midi: null, target: null, cents: null, level: 0 })
  const now = useClock()

  useEffect(() => {
    let cancelled = false
    void projectsApi
      .activeSession(data.projectId)
      .then(({ session: active }) => {
        if (cancelled) return
        setSession(active)
        setNotes(active.notes)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [data.projectId])

  useEffect(() => {
    if (!phrase) return
    const region = { start: phrase.start_s, end: phrase.end_s }
    useWorkspace.setState({ region })
    if (getPref<boolean>('training.auto_loop', true)) loopRegion(region)
    engine.setAlternate(getPref<boolean>('training.alternate_ab', false))
  }, [phrase])

  useEffect(
    () => () => {
      recorder?.close()
    },
    [recorder],
  )

  const phraseNotes = useMemo(() => {
    if (!phrase || !data.refIndex) return []
    return data.refIndex.byLevel.note
      .filter((n) => n.start_s >= phrase.start_s - 0.01 && n.end_s <= phrase.end_s + 0.01)
      .map((segment) => ({
        segment,
        center:
          numberValue(resultFor(data.refIndex, 'pitch', segment.id), 'center_midi') ??
          (segment.props.center_midi as number),
      }))
      .filter((n) => typeof n.center === 'number')
  }, [phrase, data.refIndex])

  if (!data.reference) {
    return (
      <div className="page">
        <div className="page-inner">
          <EmptyState icon="dumbbell" title="Training needs a reference">
            Import a reference vocal first.
          </EmptyState>
        </div>
      </div>
    )
  }
  if (!phrase) {
    return (
      <div className="page">
        <div className="page-inner">
          <EmptyState icon="dumbbell" title="The reference is still being analysed">
            Phrases appear here once the reference analysis finishes.
          </EmptyState>
        </div>
      </div>
    )
  }

  const history = progress.data?.phrases.find((p) => p.label === phrase.label)?.history ?? []
  const scores = history.map((h) => h.score).filter((s): s is number => s != null)
  const latest = scores.length ? scores[scores.length - 1] : null
  const best = scores.length ? Math.max(...scores) : null
  let streak = 0
  for (let i = scores.length - 1; i >= 0 && scores[i] >= mastery; i -= 1) streak += 1
  const mastered = streak >= Math.min(2, minTakes)
  const phraseTakes = data.takes.filter(
    (t) =>
      t.region_start_s == null ||
      (t.region_start_s < phrase.end_s && (t.region_end_s ?? Infinity) > phrase.start_s),
  )
  const sessionTakes = session ? data.takes.filter((t) => t.session_id === session.id).length : 0
  const suggestion =
    scores.length < minTakes
      ? `Record ${minTakes - scores.length} more take${minTakes - scores.length === 1 ? '' : 's'} of this phrase before deciding.`
      : mastered
        ? 'This phrase is consistently at your mastery threshold. Move on to the next phrase.'
        : latest != null && best != null && latest < best - 5
          ? 'Your latest take was weaker than your best. Take a short break, listen to the reference once, then try again.'
          : 'Keep repeating this phrase: it is not yet consistently at your mastery threshold.'
  const elapsed = session ? Math.max(0, (now - Date.parse(session.started_at)) / 1000) : 0
  const openMic = async () => {
    setMicError(null)
    const next = new Recorder()
    try {
      await next.open(getPref<string | null>('audio.input_device', null), 0)
      setRecorder(next)
    } catch (error) {
      next.close()
      setMicError(error instanceof Error ? error.message : String(error))
    }
  }
  const phraseIndex = phrases.findIndex((p) => p.id === phrase.id)
  const takeFinding = target
  const lastTakeForPhrase = [...phraseTakes].reverse()[0] ?? null
  return (
    <div className="page training">
      <div className="page-inner wide training-layout">
        <aside className="training-phrases card">
          <div className="panel-header">
            <span className="panel-title">Phrases</span>
          </div>
          <div className="training-phrase-list">
            {phrases.map((p) => {
              const own = data.comparison ? findingInPhrase(data.comparison.coaching.findings, p).length : 0
              const phraseScores = progress.data?.phrases.find((ph) => ph.label === p.label)
              return (
                <button
                  key={p.id}
                  type="button"
                  className={`side-item${p.id === phrase.id ? ' is-active' : ''}`}
                  onClick={() => setPhraseId(p.id)}
                >
                  <span className="grow stack" style={{ gap: 0 }}>
                    <span className="truncate">{p.label}</span>
                    <span className="tiny faint">
                      {formatTime(p.start_s, 1)} · {own} issue{own === 1 ? '' : 's'}
                    </span>
                  </span>
                  {p.id === focusPhrase ? <Badge tone="accent">focus</Badge> : null}
                  <span className="num small">
                    {phraseScores?.latest != null ? phraseScores.latest.toFixed(0) : '–'}
                  </span>
                </button>
              )
            })}
          </div>
        </aside>
        <section className="training-main">
          <div className="training-header card card-pad">
            <div className="grow stack" style={{ gap: 4 }}>
              <span className="eyebrow">
                Phrase {phraseIndex + 1} of {phrases.length}
              </span>
              <h2>“{phrase.label}”</h2>
              <p className="muted small">
                {formatTime(phrase.start_s)} – {formatTime(phrase.end_s)} · {phraseTakes.length} take
                {phraseTakes.length === 1 ? '' : 's'} so far
              </p>
            </div>
            <div className="training-scores">
              <div className="stack" style={{ alignItems: 'center', gap: 2 }}>
                <ScoreRing
                  score={latest}
                  size={56}
                  label="Latest phrase score"
                  previous={scores.length > 1 ? scores[scores.length - 2] : null}
                />
                <span className="tiny faint">latest</span>
              </div>
              <div className="stack" style={{ alignItems: 'center', gap: 2 }}>
                <ScoreRing score={best} size={56} label="Best phrase score" />
                <span className="tiny faint">best</span>
              </div>
              <div className="stack" style={{ gap: 4 }}>
                <Badge tone={mastered ? 'good' : 'neutral'} icon={mastered ? 'check' : 'target'}>
                  {mastered ? 'Mastered' : `Mastery at ${mastery}`}
                </Badge>
                <span className="tiny faint">
                  {streak > 0
                    ? `${streak} take${streak === 1 ? '' : 's'} in a row at or above ${mastery}`
                    : 'No streak yet'}
                </span>
              </div>
            </div>
          </div>
          <div className="card card-pad stack" style={{ gap: 10 }}>
            <div className="row-wrap">
              <span className="eyebrow">Target</span>
              {findings.length === 0 ? (
                <span className="small muted">
                  No reliable difference in this phrase — polish it or move on.
                </span>
              ) : null}
              {findings.slice(0, 6).map((f) => (
                <button
                  key={f.key}
                  type="button"
                  className={`chip${target?.key === f.key ? ' is-active' : ''}`}
                  onClick={() => setTargetKey(f.key)}
                >
                  <span className="cat-dot" style={{ background: `var(--cat-${f.category})` }} />
                  {f.title}
                </button>
              ))}
            </div>
            {takeFinding ? (
              <div className="training-target">
                <div className="row">
                  <CategoryChip category={takeFinding.category} />
                  <strong className="grow">{takeFinding.title}</strong>
                  <ConfidenceBadge value={takeFinding.confidence} />
                </div>
                <p>{mode === 'coach' ? takeFinding.texts.beginner : takeFinding.texts.expert}</p>
                <p className="small">
                  <strong>Try: </strong>
                  {takeFinding.texts.adjust}
                </p>
                <p className="small muted">
                  <strong>Exercise: </strong>
                  {takeFinding.texts.exercise}
                </p>
              </div>
            ) : null}
          </div>
          <div className="card card-pad stack" style={{ gap: 10 }}>
            <div className="row-wrap">
              <Button
                variant="secondary"
                icon="play"
                onClick={() => {
                  engine.setSpeed(1)
                  engine.setMode('ref')
                  void engine.play(phrase.start_s)
                }}
              >
                Listen to the reference
              </Button>
              <Button
                variant="secondary"
                icon="play"
                disabled={!engineState.hasTake}
                onClick={() => {
                  engine.setSpeed(1)
                  engine.setMode('take')
                  void engine.play(phrase.start_s)
                }}
              >
                Listen to your last take
              </Button>
              <Button
                variant="ghost"
                icon="gauge"
                onClick={() => {
                  engine.setSpeed(slow)
                  engine.setMode('ref')
                  void engine.play(phrase.start_s)
                }}
              >
                Slowed reference ({Math.round(slow * 100)}%)
              </Button>
              {engineState.playing ? (
                <Button variant="ghost" icon="pause" onClick={() => engine.pause()}>
                  Pause
                </Button>
              ) : null}
              <span className="spacer" />
              <Button
                variant="primary"
                icon="record"
                onClick={() => openRecorder({ start: phrase.start_s, end: phrase.end_s })}
              >
                Record next attempt
              </Button>
            </div>
            <div className="row-wrap">
              <Switch
                checked={autoLoop}
                onChange={(v) => {
                  setPref('training.auto_loop', v)
                  loopRegion(v ? { start: phrase.start_s, end: phrase.end_s } : null)
                }}
                label="Loop the phrase"
              />
              <Switch
                checked={alternate}
                onChange={(v) => {
                  setPref('training.alternate_ab', v)
                  engine.setAlternate(v)
                }}
                label="Alternate reference and take each loop"
              />
            </div>
          </div>
          <div className="card card-pad stack" style={{ gap: 8 }}>
            <div className="row">
              <h3 className="grow">Live pitch</h3>
              {recorder ? (
                <Button
                  size="sm"
                  variant="ghost"
                  icon="x"
                  onClick={() => {
                    recorder.close()
                    setRecorder(null)
                  }}
                >
                  Stop microphone
                </Button>
              ) : (
                <Button size="sm" variant="secondary" icon="mic" onClick={() => void openMic()}>
                  Start live pitch
                </Button>
              )}
            </div>
            {micError ? (
              <Callout tone="bad" title="Microphone unavailable">
                {micError}
              </Callout>
            ) : null}
            <div className="live-readout">
              <div>
                <span className="eyebrow">You</span>
                <span className="live-value num">
                  {reading.midi !== null ? describeMidi(reading.midi) : '–'}
                </span>
              </div>
              <div>
                <span className="eyebrow">Target note</span>
                <span className="live-value num">
                  {reading.target !== null ? describeMidi(reading.target) : '–'}
                </span>
              </div>
              <div>
                <span className="eyebrow">Deviation</span>
                <span
                  className={`live-value num ${reading.cents === null ? '' : Math.abs(reading.cents) <= 15 ? 'good-text' : Math.abs(reading.cents) <= 35 ? 'warn-text' : 'bad-text'}`}
                >
                  {reading.cents !== null ? formatSigned(reading.cents, 0, '¢') : '–'}
                </span>
              </div>
              <div>
                <span className="eyebrow">Input level</span>
                <span className="live-level">
                  <span style={{ width: `${Math.min(100, reading.level * 140)}%` }} />
                </span>
              </div>
            </div>
            <LivePitchCanvas
              features={data.model.ref?.features ?? null}
              notes={phraseNotes}
              start={phrase.start_s}
              end={phrase.end_s}
              recorder={recorder}
              theme={theme}
              onReading={setReading}
            />
            <p className="tiny faint">
              Your pitch (blue) is drawn over the reference (gold) as the phrase loops. The shaded band on
              each note is ±25 cents. Use headphones so the reference is not picked up by the microphone.
            </p>
          </div>
        </section>
        <aside className="training-side stack" style={{ gap: 12 }}>
          <div className="card card-pad stack" style={{ gap: 6 }}>
            <span className="eyebrow">Session</span>
            <div className="row">
              <Icon name="timer" size={16} />
              <strong className="num">{formatDuration(elapsed)}</strong>
              <span className="spacer" />
              <span className="small muted">
                {sessionTakes} take{sessionTakes === 1 ? '' : 's'} this session
              </span>
            </div>
            <TextArea
              label="Session notes"
              value={notes}
              rows={4}
              onChange={(event) => setNotes(event.target.value)}
              onBlur={() =>
                session &&
                notes !== session.notes &&
                void attempt(() => projectsApi.updateSession(session.id, { notes }), 'Notes were not saved')
              }
              placeholder="What did you notice? What will you try next time?"
            />
            <Button
              size="sm"
              variant="ghost"
              disabled={!session}
              onClick={async () => {
                if (!session) return
                const result = await attempt(
                  () => projectsApi.updateSession(session.id, { notes, end: true }),
                  'Session was not ended',
                )
                if (result) setSession(result.session)
              }}
            >
              End session
            </Button>
          </div>
          <div className="card card-pad stack" style={{ gap: 6 }}>
            <span className="eyebrow">Next step</span>
            <p className="small">{suggestion}</p>
            {mastered && phraseIndex < phrases.length - 1 ? (
              <Button
                size="sm"
                variant="accent-soft"
                icon="chevron-right"
                onClick={() => setPhraseId(phrases[phraseIndex + 1].id)}
              >
                Next phrase
              </Button>
            ) : null}
          </div>
          <div className="card card-pad stack" style={{ gap: 6 }}>
            <span className="eyebrow">This phrase over time</span>
            {scores.length === 0 ? (
              <p className="small muted">No compared takes cover this phrase yet.</p>
            ) : (
              <ol className="attempts">
                {scores.map((score, index) => (
                  <li key={index} className={score >= mastery ? 'good-text' : undefined}>
                    <span className="faint">#{index + 1}</span>{' '}
                    <span className="num">{score.toFixed(0)}</span>
                    {index > 0 ? (
                      <span className={`tiny ${score - scores[index - 1] >= 0 ? 'good-text' : 'bad-text'}`}>
                        {' '}
                        {formatSigned(score - scores[index - 1], 0)}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ol>
            )}
            {lastTakeForPhrase ? <p className="tiny faint">Latest: {lastTakeForPhrase.name}</p> : null}
          </div>
        </aside>
      </div>
      <ImportDialog projectId={data.projectId} reference={data.reference} />
      <RecordDialog projectId={data.projectId} reference={data.reference} takes={data.takes} tab="train" />
    </div>
  )
}
