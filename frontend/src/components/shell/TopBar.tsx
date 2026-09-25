import { useSyncExternalStore } from 'react'
import { Segmented } from '../ui/Controls'
import { IconButton } from '../ui/Button'
import { Icon } from '../ui/Icon'
import { ProgressBar } from '../ui/Feedback'
import { MenuButton } from '../ui/Menu'
import { Tooltip } from '../ui/Tooltip'
import { useProject, useSystemInfo } from '../../state/data'
import { redo, undo, useHistory } from '../../state/history'
import { setPref, usePref, useViewMode, type ViewMode } from '../../state/prefs'
import { navigate, type ProjectTab, type Route } from '../../state/router'
import { activeTasks, cancelTask, savingCount, subscribeSaving, useTaskStore } from '../../state/tasks'
import { setUi } from '../../state/ui'

function SaveState() {
  const saving = useSyncExternalStore(subscribeSaving, savingCount, savingCount)
  return (
    <span className={`save-state${saving ? ' is-saving' : ''}`} role="status" aria-live="polite">
      {saving ? <span className="spinner spinner-inline" /> : <Icon name="check" size={13} />}
      {saving ? 'Saving…' : 'Saved'}
    </span>
  )
}

function TaskIndicator() {
  const state = useTaskStore()
  const running = activeTasks(state)
  if (running.length === 0) {
    return (
      <span className="task-indicator is-idle" title="No background work">
        <Icon name="activity" size={14} />
        Idle
      </span>
    )
  }
  const overall = running.reduce((sum, t) => sum + t.progress, 0) / running.length
  return (
    <MenuButton
      label="Background tasks"
      icon="activity"
      text={
        <span className="task-indicator-text">
          {running.length === 1 ? running[0].message || 'Working…' : `${running.length} tasks`}
          <span className="task-indicator-bar">
            <ProgressBar value={overall} label="Overall progress" />
          </span>
        </span>
      }
      variant="subtle"
      size="sm"
      align="start"
      items={[
        { heading: 'Background tasks' },
        ...running.map((task) => ({
          label: `${task.message || task.kind} · ${Math.round(task.progress * 100)}%`,
          hint: 'Cancel',
          icon: 'x',
          onSelect: () => void cancelTask(task.id),
        })),
      ]}
    />
  )
}

function ComputeChip() {
  const system = useSystemInfo()
  const gpu = system.data?.gpu
  const label = gpu?.cuda_available ? 'GPU' : 'CPU'
  return (
    <Tooltip
      content={
        system.data ? (
          <div className="stack" style={{ gap: 2 }}>
            <strong>{gpu?.cuda_available ? `GPU: ${gpu.name}` : 'CPU analysis'}</strong>
            <span className="muted">{gpu?.note}</span>
            <span className="faint">
              {system.data.cpu.logical_cores} cores · {system.data.memory.available_gb.toFixed(1)} GB free ·
              workers {system.data.workers}
            </span>
          </div>
        ) : (
          'Checking hardware…'
        )
      }
    >
      <button type="button" className="compute-chip" onClick={() => navigate({ name: 'diagnostics' })}>
        <Icon name="cpu" size={13} />
        {label}
      </button>
    </Tooltip>
  )
}

const TABS: { id: ProjectTab; label: string; icon: string }[] = [
  { id: 'compare', label: 'Compare', icon: 'compare' },
  { id: 'train', label: 'Train', icon: 'dumbbell' },
  { id: 'progress', label: 'Progress', icon: 'trend-up' },
]

export function TopBar({ route }: { route: Route }) {
  const mode = useViewMode()
  const theme = usePref<string>('display.theme', 'system')
  const canUndo = useHistory((s) => s.past.length > 0)
  const canRedo = useHistory((s) => s.future.length > 0)
  const undoLabel = useHistory((s) => s.past[s.past.length - 1]?.label)
  const redoLabel = useHistory((s) => s.future[s.future.length - 1]?.label)
  const projectId = route.name === 'project' ? route.projectId : null
  const project = useProject(projectId)
  const nextTheme = theme === 'system' ? 'dark' : theme === 'dark' ? 'light' : 'system'
  return (
    <header className="topbar">
      <div className="topbar-left">
        <button
          type="button"
          className="brand"
          onClick={() => navigate({ name: 'home' })}
          aria-label="Vibrato — all projects"
        >
          <span className="brand-mark">
            <Icon name="logo" size={16} />
          </span>
          <span className="brand-name">Vibrato</span>
        </button>
        {route.name === 'project' ? (
          <>
            <Icon name="chevron-right" size={12} className="faint" />
            <span className="topbar-project truncate" title={project.data?.project.name}>
              {project.data?.project.name ?? '…'}
            </span>
            <nav className="topbar-tabs" aria-label="Project views">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  className={`topbar-tab${route.tab === tab.id ? ' is-active' : ''}`}
                  aria-current={route.tab === tab.id ? 'page' : undefined}
                  onClick={() => navigate({ ...route, tab: tab.id })}
                >
                  <Icon name={tab.icon} size={14} />
                  {tab.label}
                </button>
              ))}
            </nav>
          </>
        ) : (
          <span className="topbar-section faint">
            {route.name === 'home'
              ? 'Projects'
              : route.name === 'settings'
                ? 'Settings'
                : route.name === 'calibration'
                  ? 'Voice calibration'
                  : route.name === 'profiles'
                    ? 'Reference library'
                    : route.name === 'diagnostics'
                      ? 'Diagnostics'
                      : 'Help'}
          </span>
        )}
      </div>
      <div className="topbar-center">
        <TaskIndicator />
      </div>
      <div className="topbar-right">
        <SaveState />
        <div className="row" style={{ gap: 0 }}>
          <IconButton
            icon="undo"
            label={canUndo ? `Undo ${undoLabel}` : 'Nothing to undo'}
            shortcut="Ctrl+Z"
            disabled={!canUndo}
            onClick={() => void undo()}
          />
          <IconButton
            icon="redo"
            label={canRedo ? `Redo ${redoLabel}` : 'Nothing to redo'}
            shortcut="Ctrl+Shift+Z"
            disabled={!canRedo}
            onClick={() => void redo()}
          />
        </div>
        <ComputeChip />
        <Tooltip content="Coach: plain-language advice. Analyst: measurements and explanations. Research: raw graphs, confidence and analyzer details.">
          <Segmented<ViewMode>
            size="sm"
            ariaLabel="Detail level"
            value={mode}
            onChange={(value) => setPref('display.view_mode', value)}
            options={[
              { value: 'coach', label: 'Coach' },
              { value: 'analyst', label: 'Analyst' },
              { value: 'research', label: 'Research' },
            ]}
          />
        </Tooltip>
        <button
          type="button"
          className="palette-trigger"
          onClick={() => setUi({ paletteOpen: true })}
          aria-label="Open command palette"
        >
          <Icon name="search" size={13} />
          <span>Commands</span>
          <kbd className="kbd">⌘K</kbd>
        </button>
        <IconButton
          icon={theme === 'dark' ? 'moon' : theme === 'light' ? 'sun' : 'monitor'}
          label={`Theme: ${theme} (switch to ${nextTheme})`}
          onClick={() => setPref('display.theme', nextTheme)}
        />
        <IconButton icon="sliders" label="Settings" onClick={() => navigate({ name: 'settings' })} />
        <IconButton
          icon="help"
          label="Help, methods and glossary"
          onClick={() => navigate({ name: 'help' })}
        />
      </div>
    </header>
  )
}
