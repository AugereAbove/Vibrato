import { useEffect, useMemo, useRef, useState } from 'react'
import { authApi, systemApi } from '../../api/endpoints'
import type { PreferenceSchemaItem, PreferenceValue } from '../../api/types'
import { measureLatency } from '../../audio/latency'
import {
  deviceNamesHidden,
  listInputDevices,
  onInputDevicesChanged,
  Recorder,
  requestInputDevices,
} from '../../audio/recorder'
import { ActiveMic, InputMeter } from '../../components/ui/InputMeter'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Select, Slider, Switch, TextField, Checkbox } from '../../components/ui/Controls'
import { confirmAction } from '../../components/ui/confirm'
import { Callout, ErrorState, SkeletonLines } from '../../components/ui/Feedback'
import { Icon } from '../../components/ui/Icon'
import { formatBytes } from '../../lib/format'
import { keys, useModels, usePreferenceSchema, useSystemInfo } from '../../state/data'
import { signOut, useAuth } from '../../state/auth'
import { attempt } from '../../state/errors'
import { getPref, resetPrefs, setPref, usePrefsStore, useSystemTheme } from '../../state/prefs'
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
  'Access',
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
  Access: 'users',
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
  const selected = typeof current === 'string' ? current : ''
  const [testing, setTesting] = useState<Recorder | null>(null)
  const [error, setError] = useState<string | null>(null)
  const hidden = deviceNamesHidden(devices.data ?? [])
  const refreshDevices = useRef(devices.refresh)

  useEffect(() => {
    refreshDevices.current = devices.refresh
  })

  useEffect(() => onInputDevicesChanged(() => void refreshDevices.current()), [])

  useEffect(() => () => testing?.close(), [testing])

  const allow = async () => {
    setError(null)
    try {
      await requestInputDevices()
      await devices.refresh()
    } catch {
      setError(
        'Microphone access was blocked. Allow it in your browser’s site settings (the icon next to the address bar), then try again.',
      )
    }
  }

  const startTest = async (deviceId: string) => {
    setError(null)
    testing?.close()
    const recorder = new Recorder()
    try {
      await recorder.open(deviceId || null, 0)
      setTesting(recorder)
      await devices.refresh()
    } catch {
      recorder.close()
      setTesting(null)
      setError('That microphone could not be opened. It may be in use by another app or unplugged.')
    }
  }

  const choose = (value: string) => {
    setPref('audio.input_device', value || null)
    if (testing) void startTest(value)
  }

  return (
    <div className="setting-card card card-pad stack" style={{ gap: 8 }}>
      <div className="row">
        <Icon name="mic" size={16} />
        <strong className="grow">Microphone</strong>
        {testing ? (
          <Button size="xs" variant="ghost" icon="stop" onClick={() => setTesting(null)}>
            Stop test
          </Button>
        ) : (
          <Button size="xs" variant="secondary" icon="mic" onClick={() => void startTest(selected)}>
            Test microphone
          </Button>
        )}
      </div>
      {hidden ? (
        <Callout tone="info" title="Your browser is hiding microphone names">
          Browsers only show which microphones you have after you allow access.
          <div style={{ marginTop: 8 }}>
            <Button size="sm" icon="mic" onClick={() => void allow()}>
              Allow microphone access
            </Button>
          </div>
        </Callout>
      ) : null}
      <Select
        ariaLabel="Input device"
        value={selected}
        onChange={choose}
        options={[
          { value: '', label: 'System default (whatever your computer is set to use)' },
          ...(devices.data ?? [])
            .filter((d) => d.deviceId !== 'default')
            .map((d, i) => ({ value: d.deviceId, label: d.label || `Microphone ${i + 1}` })),
        ]}
      />
      {error ? (
        <Callout tone="bad" title="Microphone problem">
          {error}
        </Callout>
      ) : null}
      {testing ? (
        <>
          <InputMeter recorder={testing} />
          <ActiveMic recorder={testing} />
        </>
      ) : null}
      <p className="tiny faint">
        Tip: plugging in headphones can silently switch “System default” to the headset’s microphone. Pick
        your microphone by name to be sure. Echo cancellation, noise suppression and automatic gain stay off
        while recording so the measurements are accurate.
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
  const user = useAuth((s) => s.user)
  return (
    <div className="setting-card card card-pad stack" style={{ gap: 6 }}>
      <div className="row">
        <Icon name="shield" size={16} />
        <strong className="grow">Privacy and account</strong>
        <Button size="sm" variant="ghost" onClick={() => void signOut()}>
          Sign out
        </Button>
      </div>
      <p className="small muted">
        Signed in as <strong>{user?.display_name ?? '…'}</strong>. Your projects and recordings are private to
        your account; other testers can't see them. Vibrato sends no telemetry, and all processing happens on
        this server.
      </p>
    </div>
  )
}

function ThemeHint() {
  const theme = usePrefsStore((s) => s.values['display.theme'])
  const system = useSystemTheme()
  return (
    <div className="setting-card card card-pad row">
      <Icon name={system === 'dark' ? 'moon' : 'sun'} size={16} />
      <span className="grow small">
        Your browser currently reports a <strong>{system}</strong> system theme
        {theme === 'system' ? ', so Vibrato is using that.' : '.'} If that doesn’t match your computer,
        Windows and browsers have separate settings: on Windows check Settings › Personalization › Colors ›
        “Choose your default app mode”, and in Chrome or Edge check the Appearance settings.
      </span>
    </div>
  )
}

function inviteLink(code: string): string {
  return `${window.location.origin}${authApi.claimUrl(code)}`
}

async function copyLink(code: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(inviteLink(code))
    pushToast({ kind: 'success', title: 'Link copied' })
  } catch {
    pushToast({ kind: 'error', title: 'Could not copy', body: inviteLink(code) })
  }
}

function LinkRow({ code }: { code: string }) {
  return (
    <div className="row" style={{ gap: 6 }}>
      <code className="code-inline grow" style={{ overflowWrap: 'anywhere' }}>
        {inviteLink(code)}
      </code>
      <Button size="xs" variant="ghost" icon="copy" onClick={() => void copyLink(code)}>
        Copy
      </Button>
    </div>
  )
}

function AccessTool() {
  const me = useAuth((s) => s.user)
  const users = useResource('auth-users', async () => (await authApi.listUsers()).users)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [ownerLink, setOwnerLink] = useState<string | null>(null)

  const create = async () => {
    setBusy(true)
    const result = await attempt(
      () => authApi.createInvite(name.trim() || 'Tester'),
      'Could not create invite',
    )
    setBusy(false)
    if (result) {
      setName('')
      await users.refresh()
    }
  }

  const newLink = async (id: string, label: string) => {
    const ok = await confirmAction({
      title: `Issue a new link for ${label}?`,
      body: 'Their old link stops working and they are signed out on every device. Send them the new link to get back in.',
      confirmLabel: 'Issue new link',
    })
    if (!ok) return
    if (await attempt(() => authApi.newLink(id), 'Could not issue a new link')) await users.refresh()
  }

  const revoke = async (id: string, label: string) => {
    const ok = await confirmAction({
      title: `Revoke ${label}?`,
      body: 'They are signed out everywhere and their links stop working. Their projects are kept; you can restore access later by issuing a new link.',
      confirmLabel: 'Revoke access',
      danger: true,
    })
    if (!ok) return
    if (await attempt(() => authApi.revoke(id), 'Could not revoke access')) await users.refresh()
  }

  const rotateOwner = async () => {
    if (!me) return
    const ok = await confirmAction({
      title: 'Issue a new owner link?',
      body: 'Any old owner link stops working and you are signed out on every other device. This browser stays signed in.',
      confirmLabel: 'Issue new owner link',
    })
    if (!ok) return
    const result = await attempt(() => authApi.newLink(me.id), 'Could not issue a new owner link')
    if (result) setOwnerLink(result.invite.code)
  }

  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="setting-card card card-pad stack" style={{ gap: 8 }}>
        <div className="row">
          <Icon name="users" size={16} />
          <strong className="grow">Testers</strong>
          <Button size="xs" variant="ghost" icon="refresh" onClick={() => void users.refresh()}>
            Refresh
          </Button>
        </div>
        <p className="small muted">
          Each tester has their own private projects. Links work once and expire after 14 days; if a tester
          needs to sign in on another device, issue them a new link.
        </p>
        <div className="row">
          <TextField
            placeholder="Tester name"
            value={name}
            maxLength={60}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void create()
            }}
          />
          <Button icon="plus" onClick={() => void create()} loading={busy}>
            Add tester
          </Button>
        </div>
        {users.loading && !users.data ? <SkeletonLines lines={3} /> : null}
        {users.error ? <ErrorState error={users.error} onRetry={() => void users.refresh()} /> : null}
        <ul className="plain-list stack" style={{ gap: 10 }}>
          {(users.data ?? []).map((u) => (
            <li key={u.id} className="stack" style={{ gap: 4 }}>
              <div className="row small" style={{ gap: 8 }}>
                <strong className="grow">{u.display_name}</strong>
                {u.disabled ? (
                  <Badge tone="bad">revoked</Badge>
                ) : u.active_sessions > 0 ? (
                  <Badge tone="good">signed in</Badge>
                ) : u.pending_code ? (
                  <Badge>link not used yet</Badge>
                ) : (
                  <Badge>no active link</Badge>
                )}
                <span className="faint">
                  {u.projects} project{u.projects === 1 ? '' : 's'}
                </span>
                <Button
                  size="xs"
                  variant="ghost"
                  icon="refresh"
                  onClick={() => void newLink(u.id, u.display_name)}
                >
                  New link
                </Button>
                {!u.disabled ? (
                  <Button
                    size="xs"
                    variant="ghost"
                    icon="x"
                    onClick={() => void revoke(u.id, u.display_name)}
                  >
                    Revoke
                  </Button>
                ) : null}
              </div>
              {u.pending_code && !u.disabled ? <LinkRow code={u.pending_code} /> : null}
            </li>
          ))}
          {(users.data ?? []).length === 0 && !users.loading ? (
            <p className="muted">No testers yet.</p>
          ) : null}
        </ul>
      </div>
      <div className="setting-card card card-pad stack" style={{ gap: 8 }}>
        <div className="row">
          <Icon name="shield" size={16} />
          <strong className="grow">Owner access</strong>
          <Button size="sm" variant="secondary" onClick={() => void rotateOwner()}>
            Issue new owner link
          </Button>
        </div>
        <p className="small muted">
          Use this if an owner link may have been shared or seen by someone else. It only works once, so open
          it on the device you want to sign in on.
        </p>
        {ownerLink ? <LinkRow code={ownerLink} /> : null}
      </div>
    </div>
  )
}

export function SettingsView({ section }: { section?: string }) {
  const schema = usePreferenceSchema()
  const isOwner = useAuth((s) => s.user?.is_owner ?? false)
  const values = usePrefsStore((s) => s.values)
  const models = useModels()
  const crepeMissing = models.data?.find((model) => model.id === 'crepe')?.available === false
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
          {SECTIONS.filter((name) => name !== 'Access' || isOwner).map((name) => (
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
            {!query && active !== 'Access' ? (
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
          {!query && active === 'Access' && isOwner ? <AccessTool /> : null}
          <div className="setting-list">
            {filtered.map((item) => (
              <div key={item.key} className="setting-row">
                {query ? <span className="eyebrow">{item.section}</span> : null}
                <Field item={item} value={values[item.key] ?? schema.data?.defaults[item.key] ?? null} />
                {item.key === 'analysis.use_crepe' && values[item.key] === true && crepeMissing ? (
                  <p className="small warn-text">
                    CREPE is not installed, so pitch still uses Praat and YIN and each analysis lists CREPE as
                    unavailable. Install it with pip install torch torchcrepe, then re-analyse.
                  </p>
                ) : null}
              </div>
            ))}
            {filtered.length === 0 && !schema.loading && active !== 'Access' ? (
              <p className="muted">No settings match “{query}”.</p>
            ) : null}
          </div>
          {!query && active === 'Display' ? <ThemeHint /> : null}
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
