import { useEffect, useRef, useSyncExternalStore } from 'react'
import type { Recording } from '../../api/types'
import { engine, type ListenMode } from '../../audio/engine'
import { IconButton } from '../../components/ui/Button'
import { Segmented, Slider } from '../../components/ui/Controls'
import { Icon } from '../../components/ui/Icon'
import { scoreTone } from '../../lib/score'
import { Tooltip } from '../../components/ui/Tooltip'
import { formatTime } from '../../lib/format'
import { navigate } from '../../state/router'
import { useWorkspace } from '../../state/workspace'
import { loopRegion, toggleLoop } from './actions'
import { openRecorder, useRecordStore } from './recordStore'

const SPEEDS = [1, 0.9, 0.75, 0.6, 0.5]

function TimeDisplay({ duration }: { duration: number }) {
  const text = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    let frame = 0
    let last = ''
    const tick = () => {
      const value = `${formatTime(engine.position(), 2)}`
      if (value !== last && text.current) {
        last = value
        text.current.textContent = value
      }
      frame = window.requestAnimationFrame(tick)
    }
    frame = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(frame)
  }, [])
  return (
    <div className="transport-time num" aria-label="Playback position">
      <span ref={text}>0:00.00</span>
      <span className="faint"> / {formatTime(duration, 1)}</span>
    </div>
  )
}

export function TransportBar({
  projectId,
  takes,
  currentTake,
  hasReference,
  duration,
}: {
  projectId: string
  takes: Recording[]
  currentTake: Recording | null
  hasReference: boolean
  duration: number
}) {
  const state = useSyncExternalStore(engine.subscribe, engine.getState, engine.getState)
  const loop = useWorkspace((s) => s.loop)
  const loopEnabled = useWorkspace((s) => s.loopEnabled)
  const region = useWorkspace((s) => s.region)
  const recording = useRecordStore((s) => s.recording)
  const modeOptions: { value: ListenMode; label: string; title: string; disabled?: boolean }[] = [
    { value: 'ref', label: 'Ref', title: 'Reference only (A)' },
    { value: 'take', label: 'Take', title: 'Your take only (B)', disabled: !state.hasTake },
    { value: 'both', label: 'Both', title: 'Both together', disabled: !state.hasTake },
    { value: 'split', label: 'L / R', title: 'Reference left, take right', disabled: !state.hasTake },
  ]
  const recentTakes = takes.slice(-6)
  return (
    <footer className="transport" aria-label="Transport">
      <div className="transport-group">
        <IconButton
          icon="rewind"
          label="Back 5 seconds"
          shortcut="←"
          tooltipSide="top"
          onClick={() => engine.seek(engine.position() - 5)}
        />
        <Tooltip content={state.playing ? 'Pause (Space)' : 'Play (Space)'} side="top">
          <button
            type="button"
            className={`transport-play${state.playing ? ' is-playing' : ''}`}
            aria-label={state.playing ? 'Pause' : 'Play'}
            onClick={() => engine.toggle()}
            disabled={!state.hasRef && !state.hasTake}
          >
            {state.loading ? (
              <span className="spinner" />
            ) : (
              <Icon name={state.playing ? 'pause' : 'play'} size={18} />
            )}
          </button>
        </Tooltip>
        <IconButton
          icon="stop"
          label="Stop"
          tooltipSide="top"
          onClick={() => engine.stop(loopEnabled && loop ? loop.start : region ? region.start : 0)}
        />
        <IconButton
          icon="forward"
          label="Forward 5 seconds"
          shortcut="→"
          tooltipSide="top"
          onClick={() => engine.seek(engine.position() + 5)}
        />
        <TimeDisplay duration={duration} />
      </div>
      <div className="transport-group">
        <Segmented
          size="sm"
          ariaLabel="Listen to"
          value={state.mode === 'synthetic' ? 'take' : state.mode}
          onChange={(value) => engine.setMode(value)}
          options={modeOptions}
        />
        <IconButton
          icon="compare"
          label="Switch between reference and take at the same moment"
          shortcut="A"
          tooltipSide="top"
          onClick={() => engine.toggleAB()}
          disabled={!state.hasTake}
        />
        <Tooltip content="Alternate reference and take on every loop pass" side="top">
          <button
            type="button"
            className={`transport-toggle${state.alternate ? ' is-on' : ''}`}
            onClick={() => engine.setAlternate(!state.alternate)}
            aria-pressed={state.alternate}
            disabled={!state.hasTake}
          >
            A↔B
          </button>
        </Tooltip>
      </div>
      <div className="transport-group">
        <Tooltip
          content={
            loop ? `Loop ${formatTime(loop.start)} – ${formatTime(loop.end)} (L)` : 'Loop the selection (L)'
          }
          side="top"
        >
          <button
            type="button"
            className={`transport-toggle${loopEnabled ? ' is-on' : ''}`}
            onClick={() => toggleLoop()}
            aria-pressed={loopEnabled}
          >
            <Icon name="loop" size={14} />
            {loop ? (
              <span className="num">
                {formatTime(loop.start, 1)}–{formatTime(loop.end, 1)}
              </span>
            ) : (
              'Loop'
            )}
          </button>
        </Tooltip>
        {loop ? (
          <IconButton
            icon="x"
            label="Clear loop"
            size="xs"
            tooltipSide="top"
            onClick={() => loopRegion(null)}
          />
        ) : null}
        <label className="transport-select">
          <span className="sr-only">Playback speed</span>
          <select value={state.speed} onChange={(event) => engine.setSpeed(Number(event.target.value))}>
            {SPEEDS.map((speed) => (
              <option key={speed} value={speed}>
                {speed === 1 ? '1× speed' : `${Math.round(speed * 100)}% (pitch kept)`}
              </option>
            ))}
          </select>
        </label>
        <Tooltip content="Match loudness so the louder recording does not sound 'better'" side="top">
          <button
            type="button"
            className={`transport-toggle${state.gainMatch ? ' is-on' : ''}`}
            onClick={() => engine.setGainMatch(!state.gainMatch)}
            aria-pressed={state.gainMatch}
          >
            Gain match
          </button>
        </Tooltip>
        <Tooltip content="Three count-in clicks before playback starts" side="top">
          <button
            type="button"
            className={`transport-toggle${state.countIn ? ' is-on' : ''}`}
            onClick={() => engine.setCountIn(!state.countIn)}
            aria-pressed={state.countIn}
          >
            <Icon name="metronome" size={14} />
          </button>
        </Tooltip>
        <div className="transport-volume">
          <Icon name={state.volume === 0 ? 'volume-off' : 'volume'} size={15} />
          <Slider
            value={state.volume}
            min={0}
            max={1}
            step={0.01}
            onChange={(v) => engine.setVolume(v)}
            ariaLabel="Volume"
          />
        </div>
      </div>
      <div className="transport-group transport-takes" aria-label="Take history">
        {recentTakes.map((take) => (
          <Tooltip
            key={take.id}
            content={`${take.name}${take.overall_score != null ? ` · ${take.overall_score.toFixed(0)}` : ''}`}
            side="top"
          >
            <button
              type="button"
              className={`take-pill tone-${scoreTone(take.overall_score)}${take.id === currentTake?.id ? ' is-current' : ''}`}
              onClick={() => navigate({ name: 'project', projectId, tab: 'compare', take: take.id })}
            >
              <span className="take-pill-number">{take.take_number ?? '·'}</span>
              <span className="num">{take.overall_score != null ? take.overall_score.toFixed(0) : '–'}</span>
            </button>
          </Tooltip>
        ))}
        <Tooltip content={hasReference ? 'Record a new take (R)' : 'Import a reference first'} side="top">
          <button
            type="button"
            className={`transport-record${recording ? ' is-recording' : ''}`}
            onClick={() => openRecorder(loopEnabled ? loop : region)}
            aria-label="Record a take"
          >
            <Icon name="record" size={12} />
            Record
          </button>
        </Tooltip>
      </div>
    </footer>
  )
}
