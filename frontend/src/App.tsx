import { useEffect, useMemo, useState } from 'react'
import { systemApi } from './api/endpoints'
import { CommandPalette } from './components/shell/CommandPalette'
import { useRegisterCommands, type Command } from './components/shell/commands'
import { ShortcutsDialog } from './components/shell/ShortcutsDialog'
import { TopBar } from './components/shell/TopBar'
import { resetPalette } from './components/timeline/lanes/palette'
import { Button } from './components/ui/Button'
import { ConfirmHost } from './components/ui/Dialog'
import { ErrorBoundary } from './components/ui/ErrorBoundary'
import { Icon } from './components/ui/Icon'
import { ContextMenuHost } from './components/ui/Menu'
import { Toaster } from './components/ui/Toaster'
import { redo, undo } from './state/history'
import { loadPrefs, setPref, useReducedMotion, useResolvedTheme, usePref } from './state/prefs'
import { navigate, useRoute } from './state/router'
import { resumeActiveTasks } from './state/tasks'
import { setUi, useUi } from './state/ui'
import { CalibrationView } from './views/calibration/CalibrationView'
import { DiagnosticsView } from './views/diagnostics/DiagnosticsView'
import { HelpView } from './views/help/HelpView'
import { HomeView } from './views/home/HomeView'
import { startDemo } from './views/home/projectActions'
import { ProfilesView } from './views/profiles/ProfilesView'
import { ProjectView } from './views/project/ProjectView'
import { SettingsView } from './views/settings/SettingsView'
import { isTyping } from './views/workstation/shortcuts'

function useBackendStatus(): 'checking' | 'online' | 'offline' {
  const [status, setStatus] = useState<'checking' | 'online' | 'offline'>('checking')
  useEffect(() => {
    let cancelled = false
    let timer = 0
    const check = async () => {
      try {
        await systemApi.health()
        if (!cancelled) setStatus('online')
        timer = window.setTimeout(check, 15000)
      } catch {
        if (!cancelled) setStatus('offline')
        timer = window.setTimeout(check, 2500)
      }
    }
    void check()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [])
  return status
}

function useGlobalKeys(): void {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const mod = event.ctrlKey || event.metaKey
      if (mod && (event.key === 'k' || event.key === 'K')) {
        event.preventDefault()
        setUi({ paletteOpen: !useUi.getState().paletteOpen })
        return
      }
      if (isTyping(event.target)) return
      if (mod && !event.altKey && (event.key === 'z' || event.key === 'Z')) {
        event.preventDefault()
        if (event.shiftKey) void redo()
        else void undo()
        return
      }
      if (mod && (event.key === 'y' || event.key === 'Y')) {
        event.preventDefault()
        void redo()
        return
      }
      if (!mod && event.key === '?') {
        event.preventDefault()
        setUi({ shortcutsOpen: true })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}

export function App() {
  const route = useRoute()
  const theme = useResolvedTheme()
  const reduced = useReducedMotion()
  const backend = useBackendStatus()
  const lastProjectId = useUi((s) => s.lastProjectId)
  const themePref = usePref<string>('display.theme', 'system')
  useGlobalKeys()

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    resetPalette()
  }, [theme])

  useEffect(() => {
    document.documentElement.dataset.motion = reduced ? 'reduced' : 'full'
  }, [reduced])

  useEffect(() => {
    if (backend !== 'online') return
    void loadPrefs()
    void resumeActiveTasks()
  }, [backend])

  const globalCommands: Command[] = useMemo(
    () => [
      {
        id: 'home',
        title: 'Go to projects',
        group: 'Navigate',
        icon: 'home',
        run: () => navigate({ name: 'home' }),
      },
      {
        id: 'last-project',
        title: 'Open last project',
        group: 'Navigate',
        icon: 'folder',
        disabled: !lastProjectId,
        run: () => lastProjectId && navigate({ name: 'project', projectId: lastProjectId, tab: 'compare' }),
      },
      {
        id: 'new-project',
        title: 'New project',
        group: 'Project',
        icon: 'plus',
        run: () => navigate({ name: 'home' }),
      },
      { id: 'demo', title: 'Open the demo project', group: 'Project', icon: 'flask', run: startDemo },
      {
        id: 'calibration',
        title: 'Open calibration',
        group: 'Navigate',
        icon: 'gauge',
        run: () => navigate({ name: 'calibration' }),
      },
      {
        id: 'profiles',
        title: 'Reference library',
        group: 'Navigate',
        icon: 'users',
        run: () => navigate({ name: 'profiles' }),
      },
      {
        id: 'settings',
        title: 'Open settings',
        group: 'Navigate',
        icon: 'sliders',
        run: () => navigate({ name: 'settings' }),
      },
      {
        id: 'diagnostics',
        title: 'Diagnostics and models',
        group: 'Navigate',
        icon: 'cpu',
        run: () => navigate({ name: 'diagnostics' }),
      },
      {
        id: 'help',
        title: 'Help, methods and glossary',
        group: 'Navigate',
        icon: 'help',
        run: () => navigate({ name: 'help' }),
      },
      {
        id: 'shortcuts',
        title: 'Keyboard shortcuts',
        group: 'Help',
        icon: 'keyboard',
        shortcut: '?',
        run: () => setUi({ shortcutsOpen: true }),
      },
      {
        id: 'mode-coach',
        title: 'Coach view (plain language)',
        group: 'View',
        icon: 'user',
        run: () => setPref('display.view_mode', 'coach'),
      },
      {
        id: 'mode-analyst',
        title: 'Analyst view (measurements)',
        group: 'View',
        icon: 'bars',
        run: () => setPref('display.view_mode', 'analyst'),
      },
      {
        id: 'mode-research',
        title: 'Research view (raw data)',
        group: 'View',
        icon: 'flask',
        run: () => setPref('display.view_mode', 'research'),
      },
      {
        id: 'theme',
        title: `Switch theme (now ${themePref})`,
        group: 'View',
        icon: theme === 'dark' ? 'sun' : 'moon',
        run: () => setPref('display.theme', theme === 'dark' ? 'light' : 'dark'),
      },
      { id: 'undo', title: 'Undo', group: 'Edit', icon: 'undo', shortcut: 'Ctrl+Z', run: () => void undo() },
      {
        id: 'redo',
        title: 'Redo',
        group: 'Edit',
        icon: 'redo',
        shortcut: 'Ctrl+Shift+Z',
        run: () => void redo(),
      },
    ],
    [lastProjectId, theme, themePref],
  )
  useRegisterCommands('global', globalCommands)

  let view: React.ReactNode
  switch (route.name) {
    case 'home':
      view = <HomeView />
      break
    case 'project':
      view = (
        <ProjectView
          key={route.projectId}
          projectId={route.projectId}
          tab={route.tab}
          take={route.take}
          reference={route.ref}
        />
      )
      break
    case 'settings':
      view = <SettingsView section={route.section} />
      break
    case 'calibration':
      view = <CalibrationView />
      break
    case 'profiles':
      view = <ProfilesView profileId={route.profileId} />
      break
    case 'diagnostics':
      view = <DiagnosticsView />
      break
    case 'help':
      view = <HelpView topic={route.topic} />
      break
  }

  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <TopBar route={route} />
      {backend === 'offline' ? (
        <div className="offline-banner" role="alert">
          <Icon name="alert" size={15} />
          <span>
            <strong>The analysis server is not reachable.</strong> Start it with <code>./run.sh</code> (or{' '}
            <code>run.bat</code>). Retrying automatically…
          </span>
          <Button size="xs" variant="ghost" icon="refresh" onClick={() => window.location.reload()}>
            Reload
          </Button>
        </div>
      ) : null}
      <div id="main" className="app-main">
        <ErrorBoundary label="page" resetKey={route}>
          {view}
        </ErrorBoundary>
      </div>
      <CommandPalette />
      <ShortcutsDialog />
      <ConfirmHost />
      <ContextMenuHost />
      <Toaster />
    </div>
  )
}
