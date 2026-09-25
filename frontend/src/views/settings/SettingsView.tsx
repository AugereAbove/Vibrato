import { useMemo, useState } from 'react'
import { systemApi } from '../../api/endpoints'
import type { PreferenceSchemaItem, PreferenceValue } from '../../api/types'
import { measureLatency } from '../../audio/latency'
import { listInputDevices, Recorder } from '../../audio/recorder'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Select, Slider, Switch, TextField, Checkbox } from '../../components/ui/Controls'
import { confirmAction } from '../../components/ui/confirm'
import { Callout, ErrorState, SkeletonLines } from '../../components/ui/Feedback'
import { Icon } from '../../components/ui/Icon'
import { formatBytes } from '../../lib/format'
import { keys, useModels, usePreferenceSchema, useSystemInfo } from '../../state/data'
import { attempt } from '../../state/errors'
import { getPref, resetPrefs, setPref, usePrefsStore } from '../../state/prefs'
import { invalidate, useResource } from '../../state/resource'
import { navigate } from '../../state/router'
import { pushToast } from '../../state/toasts'
import { resetLayout } from '../../state/ui'

const SECTIONS = [
  'Audio',
  'Analysis',
  'Models',
  'Display',
  'Training',
  'Storage',
  'Performance',
  'Privacy',
  'Advanced',
] as const
type Section = (typeof SECTIONS)[number]

const ICONS: Record<Section, string> = {
  Audio: 'mic',
  Analysis: 'activity',
  Models: 'cpu',
  Display: 'monitor',
  Training: 'dumbbell',
  Storage: 'database',
  Performance: 'gauge',
  Privacy: 'shield',
  Advanced: 'sliders',
}

function Field({ item, value }: { item: PreferenceSchemaItem; value: PreferenceValue }) {
  const label = (
    <span>
      {item.label}
      {item.key.startsWith('scoring.') ? null : (
        <span className="setting-key" aria-hidden>
          {item.key}
        </span>
      )}
    </span>
  )
  switch (item.type) {
    case 'boolean':
      return (
        <Switch
          checked={Boolean(value)}
          onChange={(v) => setPref(item.key, v)}
          label={label}
          description={item.help}
        />
      )
    case 'slider':
      return (
        <div className="setting-field">
          <Slider
            label={label}
            value={typeof value === 'number' ? value : Number(value ?? 0)}
            min={item.min ?? 0}
            max={item.max ?? 1}
            step={item.step ?? 0.05}
            format={(v) => (item.max && item.max <= 1 ? `${Math.round(v * 100)}%` : v.toFixed(2))}
            onChange={(v) => setPref(item.key, v)}
          />
          {item.help ? <span className="field-hint">{item.help}</span> : null}
        </div>
      )
    case 'select':
      return (
        <div className="setting-field">
          <Select
            label={label}
            value={String(value ?? '')}
            onChange={(v) => setPref(item.key, v)}
            options={(item.options ?? []).map((o) => ({
              value: o,
              label: o.charAt(0).toUpperCase() + o.slice(1),
            }))}
          />
          {item.help ? <span className="field-hint">{item.help}</span> : null}
        </div>
      )
    case 'multiselect': {
      const selected = Array.isArray(value) ? value : []
      return (
        <div className="setting-field">
          <span className="field-label">{label}</span>
          <div className="row-wrap">
            {(item.options ?? []).map((option) => (
              <Checkbox
                key={option}
                checked={selected.includes(option)}
                label={option}
                onChange={(checked) =>
                  setPref(item.key, checked ? [...selected, option] : selected.filter((o) => o !== option))
                }
              />
            ))}
          </div>
          {item.help ? <span className="field-hint">{item.help}</span> : null}
        </div>
      )
    }
    case 'number':
      return (
        <div className="setting-field">
          <TextField
            label={label}
            type="number"
            min={item.min}
            max={item.max}
            step={item.step ?? 1}
            value={value == null ? '' : String(value)}
            onChange={(e) => {
              const next = Number(e.target.value)
              if (Number.isFinite(next))
                setPref(item.key, Math.max(item.min ?? -Infinity, Math.min(item.max ?? Infinity, next)))
            }}
            hint={item.help}
          />
        </div>
      )
    default:
      return (
        <TextField
          label={label}
          value={String(value ?? '')}
          onChange={(e) => setPref(item.key, e.target.value)}
          hint={item.help}
        />
      )
  }
}

function LatencyTool() {
  const [state, setState] = useState<'idle' | 'running' | 'done' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const latency = usePrefsStore((s) => s.values['audio.latency_ms'])
  const calibrated = usePrefsStore((s) => s.values['audio.latency_calibrated'])
  const run = async () => {
    setState('running')
    const recorder = new Recorder()
    try {
      await recorder.open(getPref<string | null>('audio.input_device', null), 0)
      const result = await measureLatency(recorder)
      setPref('audio.latency_ms', result.latencyMs)
      setPref('audio.latency_calibrated', true)
      setMessage(
        `Measured ${result.latencyMs} ms round trip (spread ${result.spreadMs} ms, ${result.detections} of 8 clicks detected).`,
      )
      setState('done')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error))
      setState('error')
    } finally {
      recorder.close()
    }
  }
  return (
    <div className="setting-card card card-pad stack" style={{ gap: 8 }}>
      <div className="row">
        <Icon name="timer" size={16} />
        <strong className="grow">Recording latency</strong>
        {calibrated ? <Badge tone="good">measured</Badge> : <Badge>estimated</Badge>}
      </div>
      <p className="small muted">
        When you sing along with the reference, your voice reaches the recording a little late. Measuring the
        round trip lets Vibrato line takes up precisely. Turn your speakers up, unplug headphones, and keep
        quiet while eight clicks play.
      </p>
      <div className="row">
        <Button icon="activity" onClick={() => void run()} loading={state === 'running'}>
          Measure latency
        </Button>
        <span className="num">{typeof latency === 'number' ? `${latency} ms` : '–'}</span>
      </div>
      {state === 'done' ? <Callout tone="good">{message}</Callout> : null}
      {state === 'error' ? (
        <Callout tone="bad" title="Measurement failed">
          {message}
        </Callout>
      ) : null}
    </div>
  )
}

function DeviceTool() {
  const devices = useResource('input-devices', () => listInputDevices())
  const current = usePrefsStore((s) => s.values['audio.input_device'])
  return (
    <div className="setting-card card card-pad stack" style={{ gap: 8 }}>
      <div className="row">
        <Icon name="mic" size={16} />
        <strong className="grow">Microphone</strong>
        <Button size="xs" variant="ghost" icon="refresh" onClick={() => void devices.refresh()}>
          Refresh
        </Button>
      </div>
      <Select
        ariaLabel="Input device"
        value={typeof current === 'string' ? current : ''}
        onChange={(value) => setPref('audio.input_device', value || null)}
        options={[
          { value: '', label: 'System default' },
          ...(devices.data ?? []).map((d, i) => ({
            value: d.deviceId,
            label: d.label || `Input ${i + 1} (grant microphone access to see names)`,
          })),
        ]}
      />
      <p className="tiny faint">
        Echo cancellation, noise suppression and automatic gain are always disabled while recording so
        measurements stay accurate.
      </p>
    </div>
  )
}

function StorageTool() {
  const system = useSystemInfo()
  const cache = system.data?.cache
  return (
    <div className="setting-card card card-pad stack" style={{ gap: 8 }}>
      <div className="row">
        <Icon name="database" size={16} />
        <strong className="grow">Data folder</strong>
      </div>
      <code className="code-inline">{system.data?.data_dir ?? '…'}</code>
      {cache ? (
        <dl className="kv">
          {Object.entries(cache).map(([key, value]) => (
            <div key={key} style={{ display: 'contents' }}>
              <dt>{key.replace('_bytes', '').replace('_', ' ')}</dt>
              <dd>{formatBytes(value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      <div className="row-wrap">
        <Button
          variant="secondary"
          icon="trash"
          onClick={async () => {
            const ok = await confirmAction({
              title: 'Clear derived analysis data?',
              body: 'Features, spectrograms, alignments and previews are deleted and recomputed when needed. Your recordings and comparison history are kept.',
              confirmLabel: 'Clear cache',
            })
            if (!ok) return
            const result = await attempt(() => systemApi.clearCache(), 'Cache was not cleared')
            if (result) {
              pushToast({
                kind: 'success',
                title: `Freed ${formatBytes(result.freed_bytes)}`,
                body: result.note,
              })
              invalidate(keys.system)
              invalidate(() => true)
            }
          }}
        >
          Clear cache
        </Button>
      </div>
      <p className="tiny faint">
        Original files are never modified. Project backups (.zip) can be made from the projects page.
      </p>
    </div>
  )
}

function ModelsTool() {
  const models = useModels()
  return (
    <div className="setting-card card card-pad stack" style={{ gap: 8 }}>
      <div className="row">
        <Icon name="cpu" size={16} />
        <strong className="grow">Installed models and decoders</strong>
        <Button size="xs" variant="ghost" onClick={() => navigate({ name: 'diagnostics' })}>
          Details
        </Button>
      </div>
      <ul className="plain-list">
        {(models.data ?? []).map((model) => (
          <li key={model.id} className="row small">
            <Icon
              name={model.available ? 'check' : 'x'}
              size={13}
              className={model.available ? 'good-text' : 'faint'}
            />
            <span className="grow">{model.name}</span>
            <span className="faint">
              {model.available ? (model.version ?? 'available') : 'not installed'}
            </span>
          </li>
        ))}
      </ul>
      <p className="tiny faint">
        Nothing is downloaded automatically. Optional models are listed with install commands on the
        diagnostics page.
      </p>
    </div>
  )
}

function PrivacyTool() {
  return (
    <div className="setting-card card card-pad stack" style={{ gap: 6 }}>
      <div className="row">
        <Icon name="shield" size={16} />
        <strong>Privacy</strong>
      </div>
      <p className="small muted">
        Vibrato runs entirely on this computer. It has no accounts, sends no telemetry and makes no network
        requests. Recordings, analyses and settings live in the data folder shown under Storage.
      </p>
    </div>
  )
}

export function SettingsView({ section }: { section?: string }) {
  const schema = usePreferenceSchema()
  const values = usePrefsStore((s) => s.values)
  const [query, setQuery] = useState('')
  const active = (SECTIONS.find((s) => s.toLowerCase() === (section ?? '').toLowerCase()) ??
    'Audio') as Section
  const items = useMemo(() => schema.data?.schema ?? [], [schema.data])
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items.filter((item) => item.section === active)
    return items.filter((item) =>
      `${item.label} ${item.help ?? ''} ${item.key} ${item.section}`.toLowerCase().includes(q),
    )
  }, [items, active, query])
  return (
    <div className="page settings">
      <div className="page-inner settings-layout">
        <nav className="settings-nav" aria-label="Settings sections">
          <div style={{ marginBottom: 10 }}>
            <TextField
              icon="search"
              placeholder="Search settings"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search settings"
            />
          </div>
          {SECTIONS.map((name) => (
            <button
              key={name}
              type="button"
              className={`side-item${!query && name === active ? ' is-active' : ''}`}
              onClick={() => {
                setQuery('')
                navigate({ name: 'settings', section: name.toLowerCase() }, true)
              }}
            >
              <Icon name={ICONS[name]} size={14} />
              {name}
            </button>
          ))}
        </nav>
        <section className="settings-content">
          <div className="page-header">
            <div>
              <h1>{query ? 'Search results' : active}</h1>
              <p className="muted">Changes are saved immediately.</p>
            </div>
            {!query ? (
              <Button
                variant="ghost"
                icon="refresh"
                onClick={async () => {
                  const ok = await confirmAction({
                    title: `Restore default ${active.toLowerCase()} settings?`,
                    confirmLabel: 'Restore defaults',
                  })
                  if (ok) await resetPrefs(active)
                }}
              >
                Restore defaults
              </Button>
            ) : null}
          </div>
          {schema.loading ? <SkeletonLines lines={6} /> : null}
          {schema.error ? <ErrorState error={schema.error} onRetry={() => void schema.refresh()} /> : null}
          {!query && active === 'Audio' ? (
            <div className="setting-tools">
              <DeviceTool />
              <LatencyTool />
            </div>
          ) : null}
          {!query && active === 'Models' ? <ModelsTool /> : null}
          {!query && active === 'Storage' ? <StorageTool /> : null}
          {!query && active === 'Privacy' ? <PrivacyTool /> : null}
          <div className="setting-list">
            {filtered.map((item) => (
              <div key={item.key} className="setting-row">
                {query ? <span className="eyebrow">{item.section}</span> : null}
                <Field item={item} value={values[item.key] ?? schema.data?.defaults[item.key] ?? null} />
              </div>
            ))}
            {filtered.length === 0 && !schema.loading ? (
              <p className="muted">No settings match “{query}”.</p>
            ) : null}
          </div>
          {!query && active === 'Display' ? (
            <div className="setting-card card card-pad row">
              <Icon name="layers" size={16} />
              <span className="grow small">
                Panel sizes, collapsed panels and lane heights are remembered in this browser.
              </span>
              <Button size="sm" variant="ghost" onClick={() => resetLayout()}>
                Reset layout
              </Button>
            </div>
          ) : null}
          {!query && active === 'Advanced' ? (
            <div className="setting-card card card-pad row">
              <Icon name="cpu" size={16} />
              <span className="grow small">Analyzer registry, timings, logs, cache and debug bundle.</span>
              <Button size="sm" onClick={() => navigate({ name: 'diagnostics' })}>
                Open diagnostics
              </Button>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  )
}
