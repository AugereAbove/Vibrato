import { useEffect, useState, useSyncExternalStore } from 'react'
import { counterfactualApi } from '../../../api/endpoints'
import type { Recording, Render, Transform } from '../../../api/types'
import { engine } from '../../../audio/engine'
import { Badge } from '../../../components/ui/Badge'
import { Button } from '../../../components/ui/Button'
import { Callout, EmptyState, ErrorState, ProgressBar, SkeletonLines } from '../../../components/ui/Feedback'
import { Icon } from '../../../components/ui/Icon'
import { keys, useRenders, useTransforms } from '../../../state/data'
import { attempt } from '../../../state/errors'
import type { ViewMode } from '../../../state/prefs'
import { invalidate } from '../../../state/resource'
import { trackTask, useTaskStore } from '../../../state/tasks'
import { useWorkspace } from '../../../state/workspace'

function useSynthetic(render: Render) {
  useEffect(() => {
    engine.setTracks({
      synthetic: {
        id: render.id,
        url: counterfactualApi.audioUrl(render.id),
        lufs: null,
        timeline: render.description.output_timeline === 'reference' ? 'reference' : 'own',
      },
    })
    return () => engine.setTracks({ synthetic: null })
  }, [render])
}

function Player({ render }: { render: Render }) {
  useSynthetic(render)
  const state = useSyncExternalStore(engine.subscribe, engine.getState, engine.getState)
  const region = useWorkspace((s) => s.region)
  const loop = useWorkspace((s) => s.loop)
  const range = region ?? loop
  const play = (mode: 'ref' | 'take' | 'synthetic') => {
    if (range) void engine.playRange(mode, range.start, range.end)
    else {
      engine.setMode(mode)
      void engine.play()
    }
  }
  return (
    <div className="abc-player">
      <div
        className="abc-buttons"
        role="group"
        aria-label="Compare reference, your take and the synthetic preview"
      >
        <button
          type="button"
          className={`abc-button ref${state.mode === 'ref' && state.playing ? ' is-playing' : ''}`}
          onClick={() => play('ref')}
        >
          <span className="abc-key">A</span>
          <span>Reference</span>
        </button>
        <button
          type="button"
          className={`abc-button take${state.mode === 'take' && state.playing ? ' is-playing' : ''}`}
          onClick={() => play('take')}
        >
          <span className="abc-key">B</span>
          <span>Your take</span>
        </button>
        <button
          type="button"
          className={`abc-button synthetic${state.mode === 'synthetic' && state.playing ? ' is-playing' : ''}`}
          onClick={() => play('synthetic')}
          disabled={!state.hasSynthetic}
        >
          <span className="abc-key">C</span>
          <span>
            Modified you <Badge tone="synthetic">SYNTHETIC</Badge>
          </span>
        </button>
        <Button size="sm" variant="ghost" icon="compare" onClick={() => engine.toggleAB(true)}>
          Cycle A → B → C
        </Button>
        {state.playing ? (
          <Button size="sm" variant="ghost" icon="pause" onClick={() => engine.pause()}>
            Pause
          </Button>
        ) : null}
      </div>
      <p className="tiny faint">
        {range ? 'Plays the selected region.' : 'Select a region on the timeline to compare a short passage.'}{' '}
        Loudness is matched between all three.
      </p>
    </div>
  )
}

function TransformCard({
  transform,
  render,
  active,
  busy,
  progress,
  onRender,
  onUse,
  mode,
}: {
  transform: Transform
  render: Render | null
  active: boolean
  busy: boolean
  progress: number
  onRender: () => void
  onUse: () => void
  mode: ViewMode
}) {
  return (
    <div
      className={`transform-card card${active ? ' is-active' : ''}${transform.available ? '' : ' is-unavailable'}`}
    >
      <div className="row">
        <strong className="grow">{transform.label}</strong>
        {transform.experimental ? (
          <Badge tone="synthetic" icon="flask">
            experimental
          </Badge>
        ) : null}
      </div>
      <p className="small muted">{transform.description}</p>
      {mode !== 'coach' ? <p className="tiny faint">Method: {transform.method}</p> : null}
      {!transform.available ? <p className="tiny warn-text">{transform.unavailable_reason}</p> : null}
      {busy ? <ProgressBar value={progress} label={`Rendering ${transform.label}`} /> : null}
      <div className="row">
        {render ? (
          <>
            <Button
              size="sm"
              variant={active ? 'accent-soft' : 'secondary'}
              icon={active ? 'check' : 'headphones'}
              onClick={onUse}
            >
              {active ? 'Loaded as C' : 'Listen'}
            </Button>
            <a className="btn btn-ghost btn-sm" href={counterfactualApi.audioUrl(render.id, true)} download>
              <Icon name="download" size={14} /> WAV
            </a>
          </>
        ) : (
          <Button
            size="sm"
            variant="secondary"
            icon="wand"
            onClick={onRender}
            disabled={!transform.available || busy}
            loading={busy}
          >
            Render preview
          </Button>
        )}
      </div>
    </div>
  )
}

export function PreviewsPanel({
  take,
  hasComparison,
  mode,
}: {
  take: Recording | null
  hasComparison: boolean
  mode: ViewMode
}) {
  const transforms = useTransforms()
  const renders = useRenders(take?.id ?? null)
  const [selected, setSelected] = useState<string | null>(null)
  const [pending, setPending] = useState<Record<string, string>>({})
  const tasks = useTaskStore((s) => s.tasks)
  if (!take || !hasComparison) {
    return (
      <EmptyState compact icon="wand" title="Previews need a compared take">
        Counterfactual previews modify your own take toward the reference in one respect at a time. Compare a
        take first.
      </EmptyState>
    )
  }
  if (transforms.loading || renders.loading) return <SkeletonLines lines={4} />
  if (transforms.error)
    return <ErrorState error={transforms.error} onRetry={() => void transforms.refresh()} compact />
  const byTransform = new Map<string, Render>()
  for (const render of renders.data ?? []) {
    const existing = byTransform.get(render.transform)
    if (!existing || existing.created_at < render.created_at) byTransform.set(render.transform, render)
  }
  const current = selected ? ([...byTransform.values()].find((r) => r.id === selected) ?? null) : null
  const start = async (transform: Transform) => {
    const result = await attempt(
      () => counterfactualApi.render(take.id, transform.id),
      'Preview could not start',
    )
    if (!result) return
    setPending((p) => ({ ...p, [transform.id]: result.task.id }))
    trackTask(result.task, {
      onComplete: (task) => {
        setPending((p) => {
          const next = { ...p }
          delete next[transform.id]
          return next
        })
        invalidate(keys.renders(take.id))
        const render = task.result as Render | null
        if (render?.id) setSelected(render.id)
      },
      onFailed: () =>
        setPending((p) => {
          const next = { ...p }
          delete next[transform.id]
          return next
        }),
    })
  }
  return (
    <div className="previews-panel">
      <Callout tone="synthetic" title="Educational previews made from your own recording">
        Each preview changes one aspect of your take toward the reference (pitch, timing, vibrato, loudness…)
        and keeps everything else. It is synthetic audio, not a prediction of how your voice would produce it,
        and it never imitates the reference singer’s voice.
      </Callout>
      {current ? (
        <div className="card card-pad stack" style={{ gap: 8 }}>
          <div className="row">
            <Badge tone="synthetic">SYNTHETIC</Badge>
            <strong>{current.description.label}</strong>
            <span className="spacer" />
            <Button size="xs" variant="ghost" icon="x" onClick={() => setSelected(null)}>
              Reset to original
            </Button>
          </div>
          <Player render={current} />
          {current.warnings.length ? (
            <Callout tone="warn" title={current.approximate ? 'Approximate transformation' : 'Notes'}>
              {current.warnings.join(' ')}
            </Callout>
          ) : current.approximate ? (
            <p className="tiny faint">Approximate transformation: small artefacts are expected.</p>
          ) : null}
          {mode === 'research' ? (
            <details className="raw-result">
              <summary>Transformation parameters</summary>
              <pre className="code-block">{JSON.stringify(current.description.parameters, null, 2)}</pre>
            </details>
          ) : null}
          <p className="tiny faint">{current.description.disclaimer}</p>
        </div>
      ) : null}
      <div className="transform-grid">
        {(transforms.data ?? []).map((transform) => {
          const render = byTransform.get(transform.id) ?? null
          const taskId = pending[transform.id]
          const task = taskId ? tasks[taskId] : null
          return (
            <TransformCard
              key={transform.id}
              transform={transform}
              render={render}
              active={Boolean(render && current?.id === render.id)}
              busy={Boolean(taskId)}
              progress={task?.progress ?? 0}
              onRender={() => void start(transform)}
              onUse={() => render && setSelected(render.id)}
              mode={mode}
            />
          )
        })}
      </div>
    </div>
  )
}
