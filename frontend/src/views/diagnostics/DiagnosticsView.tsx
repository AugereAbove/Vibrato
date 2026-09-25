import { useMemo, useState } from 'react'
import { systemApi, tasksApi } from '../../api/endpoints'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { TextField } from '../../components/ui/Controls'
import { ErrorState, ProgressBar, SkeletonLines } from '../../components/ui/Feedback'
import { Icon } from '../../components/ui/Icon'
import { Tabs } from '../../components/ui/Tabs'
import { formatBytes, formatDate, formatNumber, humanize } from '../../lib/format'
import { keys, useModels, useSystemInfo } from '../../state/data'
import { attempt } from '../../state/errors'
import { useResource, invalidate } from '../../state/resource'
import { cancelTask, trackTask, useTaskStore } from '../../state/tasks'

type Tab = 'system' | 'models' | 'analyzers' | 'performance' | 'logs' | 'tasks'

function SystemTab() {
  const system = useSystemInfo()
  if (system.loading) return <SkeletonLines lines={6} />
  if (system.error || !system.data)
    return <ErrorState error={system.error} onRetry={() => void system.refresh()} />
  const s = system.data
  return (
    <div className="diag-grid">
      <div className="card card-pad">
        <h3>Application</h3>
        <dl className="kv">
          <dt>Version</dt>
          <dd>{s.app_version}</dd>
          <dt>Database schema</dt>
          <dd>
            {s.schema_version} / {s.latest_schema_version}
          </dd>
          <dt>Analysis pipeline</dt>
          <dd className="mono tiny">{s.pipeline_version}</dd>
          <dt>Comparison</dt>
          <dd className="mono tiny">{s.comparison_version}</dd>
          <dt>Coaching</dt>
          <dd className="mono tiny">{s.coaching_version}</dd>
          <dt>Workers</dt>
          <dd>{s.workers}</dd>
          <dt>Data folder</dt>
          <dd className="mono tiny" style={{ wordBreak: 'break-all' }}>
            {s.data_dir}
          </dd>
        </dl>
        {s.recovery.recovered ? <p className="warn-text small">{s.recovery.message}</p> : null}
      </div>
      <div className="card card-pad">
        <h3>Hardware</h3>
        <dl className="kv">
          <dt>Platform</dt>
          <dd className="tiny">{s.platform}</dd>
          <dt>Python</dt>
          <dd>{s.python}</dd>
          <dt>CPU</dt>
          <dd>
            {s.cpu.physical_cores} cores ({s.cpu.logical_cores} threads) ·{' '}
            {formatNumber(s.cpu.load_percent, 0)}% load
          </dd>
          <dt>Memory</dt>
          <dd>
            {s.memory.available_gb.toFixed(1)} of {s.memory.total_gb.toFixed(1)} GB free · app{' '}
            {s.memory.process_rss_mb.toFixed(0)} MB
          </dd>
          <dt>GPU</dt>
          <dd>{s.gpu.cuda_available ? `${s.gpu.name} (${s.gpu.memory_gb?.toFixed(1)} GB)` : 'not used'}</dd>
          <dt>PyTorch</dt>
          <dd>{s.gpu.torch ?? 'not installed'}</dd>
        </dl>
        <p className="tiny faint">{s.gpu.note}</p>
      </div>
      <div className="card card-pad">
        <h3>Libraries</h3>
        <dl className="kv">
          {Object.entries(s.libraries).map(([name, version]) => (
            <div key={name} style={{ display: 'contents' }}>
              <dt>{name}</dt>
              <dd className={version ? undefined : 'faint'}>{version ?? 'not installed'}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="card card-pad">
        <h3>Storage</h3>
        <dl className="kv">
          {Object.entries(s.cache).map(([key, value]) => (
            <div key={key} style={{ display: 'contents' }}>
              <dt>{humanize(key.replace('_bytes', ''))}</dt>
              <dd>{formatBytes(value)}</dd>
            </div>
          ))}
        </dl>
        <p className="small muted" style={{ marginTop: 8 }}>
          <Icon name="shield" size={12} /> {s.privacy.note}
        </p>
      </div>
    </div>
  )
}

function ModelsTab() {
  const models = useModels()
  if (models.loading) return <SkeletonLines lines={5} />
  if (models.error) return <ErrorState error={models.error} onRetry={() => void models.refresh()} />
  return (
    <div className="card">
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">Component</th>
            <th scope="col">Type</th>
            <th scope="col">Status</th>
            <th scope="col">Used for</th>
            <th scope="col">How to install</th>
          </tr>
        </thead>
        <tbody>
          {(models.data ?? []).map((model) => (
            <tr key={model.id}>
              <th scope="row">{model.name}</th>
              <td>{model.kind}</td>
              <td>
                {model.available ? (
                  <Badge tone="good">{model.version ?? 'available'}</Badge>
                ) : (
                  <Badge>not installed</Badge>
                )}
              </td>
              <td className="small">{model.used_for}</td>
              <td className="small mono">{model.available ? '–' : (model.install ?? '–')}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="tiny faint" style={{ padding: 12 }}>
        Optional components are loaded only when installed. Everything essential runs on the CPU with NumPy,
        SciPy and Praat; missing models reduce what can be measured and are reported as “model unavailable”,
        never replaced with guesses.
      </p>
    </div>
  )
}

function AnalyzersTab() {
  const analyzers = useResource(keys.analyzers, () => systemApi.analyzers())
  if (analyzers.loading) return <SkeletonLines lines={6} />
  if (analyzers.error || !analyzers.data)
    return <ErrorState error={analyzers.error} onRetry={() => void analyzers.refresh()} />
  return (
    <div className="stack" style={{ gap: 10 }}>
      <p className="small muted">
        Pipeline <span className="mono">{analyzers.data.pipeline_version}</span>. Results record the analyzer
        version that produced them, so older analyses are detected and can be recomputed.
      </p>
      {analyzers.data.analyzers.map((a) => (
        <details key={a.id} className="card card-pad analyzer-card">
          <summary className="row">
            <strong className="grow">{a.label}</strong>
            <Badge>{a.category}</Badge>
            <span className="mono tiny faint">
              {a.id}@{a.version}
            </span>
            {a.available ? <Badge tone="good">available</Badge> : <Badge tone="warn">unavailable</Badge>}
            {a.experimental ? <Badge tone="synthetic">experimental</Badge> : null}
          </summary>
          <p className="small">{a.description}</p>
          <p className="small muted">{a.method}</p>
          {a.assumptions?.length ? (
            <>
              <span className="eyebrow">Assumptions</span>
              <ul className="small">
                {a.assumptions.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          ) : null}
          {a.limitations?.length ? (
            <>
              <span className="eyebrow">Limitations</span>
              <ul className="small">
                {a.limitations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          ) : null}
          <span className="eyebrow">Parameters</span>
          <pre className="code-block">{JSON.stringify(a.parameters, null, 2)}</pre>
          <p className="tiny faint">
            Depends on: {a.dependencies.join(', ') || '–'} · segments: {a.supported_segment_types.join(', ')}
            {a.unavailable_reason ? ` · ${a.unavailable_reason}` : ''}
          </p>
        </details>
      ))}
    </div>
  )
}

function PerformanceTab() {
  const timing = useResource(keys.timing, () => systemApi.timing())
  const outdated = useResource(keys.outdated, () => systemApi.outdated())
  const [taskId, setTaskId] = useState<string | null>(null)
  const task = useTaskStore((s) => (taskId ? s.tasks[taskId] : undefined))
  const start = async (onlyOutdated: boolean) => {
    const result = await attempt(() => systemApi.reanalyze(onlyOutdated), 'Re-analysis could not start')
    if (!result) return
    setTaskId(result.task.id)
    trackTask(result.task, {
      onComplete: () => {
        invalidate(keys.outdated)
        invalidate(keys.timing)
        invalidate((key) => key.startsWith('analysis:') || key.startsWith('project:'))
      },
    })
  }
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="card card-pad stack" style={{ gap: 8 }}>
        <h3>Recompute analyses</h3>
        <p className="small muted">
          {outdated.data
            ? outdated.data.recordings.length
              ? `${outdated.data.recordings.length} recording(s) were analysed by an older pipeline version.`
              : 'All analyses are up to date.'
            : 'Checking…'}
        </p>
        <div className="row">
          <Button
            icon="refresh"
            onClick={() => void start(true)}
            disabled={!outdated.data?.recordings.length || Boolean(task && task.status === 'running')}
          >
            Re-analyse outdated
          </Button>
          <Button
            variant="ghost"
            icon="refresh"
            onClick={() => void start(false)}
            disabled={Boolean(task && task.status === 'running')}
          >
            Re-analyse everything
          </Button>
        </div>
        {task && (task.status === 'running' || task.status === 'queued') ? (
          <div className="stack" style={{ gap: 4 }}>
            <ProgressBar value={task.progress} label="Re-analysis" />
            <div className="row small">
              <span className="grow faint">{task.message}</span>
              <Button size="xs" variant="ghost" onClick={() => void cancelTask(task.id)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : null}
      </div>
      <div className="card">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Analyzer</th>
              <th scope="col">Version</th>
              <th scope="col">Runs</th>
              <th scope="col">Mean</th>
              <th scope="col">Slowest</th>
              <th scope="col">Failures</th>
            </tr>
          </thead>
          <tbody>
            {(timing.data?.analyzers ?? []).map((row) => (
              <tr key={`${row.analyzer_id}@${row.analyzer_version}`}>
                <th scope="row">{row.analyzer_id}</th>
                <td className="mono tiny">{row.analyzer_version}</td>
                <td className="num">{row.runs}</td>
                <td className="num">{formatNumber(row.mean_ms, 1)} ms</td>
                <td className="num">{formatNumber(row.max_ms, 1)} ms</td>
                <td className={`num ${row.failures ? 'bad-text' : ''}`}>{row.failures}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function LogsTab() {
  const logs = useResource('logs', () => systemApi.logs(400))
  const [filter, setFilter] = useState('')
  const lines = useMemo(() => {
    const all = logs.data?.lines ?? []
    const q = filter.trim().toLowerCase()
    return q ? all.filter((line) => line.toLowerCase().includes(q)) : all
  }, [logs.data, filter])
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row">
        <div style={{ width: 280 }}>
          <TextField
            icon="search"
            placeholder="Filter log lines"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            aria-label="Filter logs"
          />
        </div>
        <Button size="sm" variant="ghost" icon="refresh" onClick={() => void logs.refresh()}>
          Refresh
        </Button>
        <span className="spacer" />
        <a className="btn btn-secondary btn-sm" href={systemApi.debugBundleUrl()} download>
          <Icon name="download" size={14} /> Export debug bundle
        </a>
      </div>
      <pre className="log-view" aria-label="Recent log lines">
        {lines.length ? lines.join('\n') : 'No log lines yet.'}
      </pre>
      <p className="tiny faint">
        Logs are stored locally and scrubbed of anything that looks like a secret. The debug bundle contains
        logs, versions, tasks and analyzer runs, but no audio.
      </p>
    </div>
  )
}

function TasksTab() {
  const tasks = useResource('tasks:all', () => tasksApi.list(false))
  return (
    <div className="card">
      <div className="row" style={{ padding: 10 }}>
        <span className="grow small muted">Recent background work (newest first).</span>
        <Button size="sm" variant="ghost" icon="refresh" onClick={() => void tasks.refresh()}>
          Refresh
        </Button>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">Task</th>
            <th scope="col">Status</th>
            <th scope="col">Started</th>
            <th scope="col">Message</th>
          </tr>
        </thead>
        <tbody>
          {(tasks.data?.tasks ?? []).map((task) => (
            <tr key={task.id}>
              <th scope="row">{task.kind}</th>
              <td>
                <Badge
                  tone={
                    task.status === 'complete'
                      ? 'good'
                      : task.status === 'failed'
                        ? 'bad'
                        : task.status === 'running'
                          ? 'info'
                          : 'neutral'
                  }
                >
                  {task.status}
                </Badge>
              </td>
              <td className="faint">{formatDate(task.created_at)}</td>
              <td className="small">
                {task.error ? `${task.error.what} ${task.error.why ?? ''}` : task.message}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function DiagnosticsView() {
  const [tab, setTab] = useState<Tab>('system')
  return (
    <div className="page diagnostics">
      <div className="page-inner wide">
        <div className="page-header">
          <div>
            <h1>Diagnostics</h1>
            <p className="muted">Versions, hardware, optional models, analyzer registry, timings and logs.</p>
          </div>
        </div>
        <Tabs<Tab>
          ariaLabel="Diagnostics sections"
          value={tab}
          onChange={setTab}
          items={[
            { id: 'system', label: 'System', icon: 'cpu' },
            { id: 'models', label: 'Models', icon: 'database' },
            { id: 'analyzers', label: 'Analyzers', icon: 'activity' },
            { id: 'performance', label: 'Performance', icon: 'gauge' },
            { id: 'logs', label: 'Logs', icon: 'list' },
            { id: 'tasks', label: 'Tasks', icon: 'clock' },
          ]}
        />
        <div className="diag-body" key={tab}>
          {tab === 'system' ? <SystemTab /> : null}
          {tab === 'models' ? <ModelsTab /> : null}
          {tab === 'analyzers' ? <AnalyzersTab /> : null}
          {tab === 'performance' ? <PerformanceTab /> : null}
          {tab === 'logs' ? <LogsTab /> : null}
          {tab === 'tasks' ? <TasksTab /> : null}
        </div>
      </div>
    </div>
  )
}
