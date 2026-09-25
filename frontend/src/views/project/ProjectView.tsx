import { useEffect, useMemo } from 'react'
import { projectsApi } from '../../api/endpoints'
import { ApiError } from '../../api/client'
import { engine } from '../../audio/engine'
import { useRegisterCommands, type Command } from '../../components/shell/commands'
import { Button } from '../../components/ui/Button'
import { EmptyState, ErrorState } from '../../components/ui/Feedback'
import { fitAll } from '../../components/timeline/viewport'
import { LAYERS } from '../../lib/categories'
import { useResolvedTheme, useViewMode } from '../../state/prefs'
import { navigate, type ProjectTab } from '../../state/router'
import { setUi, toggleLayer, useUi } from '../../state/ui'
import { useWorkspace } from '../../state/workspace'
import { applyFocus, analyzeRecording, compareTake, realignRegion, toggleLoop } from '../workstation/actions'
import { showFinding } from '../workstation/coach/focus'
import { openWhy } from '../workstation/coach/whyStore'
import { openImport } from '../workstation/importStore'
import { openRecorder } from '../workstation/recordStore'
import { useWorkstation } from '../workstation/useWorkstation'
import { Workstation } from '../workstation/Workstation'
import { ProgressView } from '../progress/ProgressView'
import { TrainingView } from '../training/TrainingView'

export function ProjectView({
  projectId,
  tab,
  take,
  reference,
}: {
  projectId: string
  tab: ProjectTab
  take?: string
  reference?: string
}) {
  const data = useWorkstation(projectId, tab, take, reference)
  const mode = useViewMode()
  const theme = useResolvedTheme()

  useEffect(() => {
    setUi({ lastProjectId: projectId })
    return () => engine.stop(0)
  }, [projectId])

  const takes = data.takes
  const currentIndex = takes.findIndex((t) => t.id === data.take?.id)
  const previousTake = currentIndex > 0 ? takes[currentIndex - 1] : null
  const layers = useUi((s) => s.layersByMode[mode])
  const commands: Command[] = useMemo(() => {
    const comparison = data.comparison
    const primary = comparison?.coaching.primary[0] ?? null
    const list: Command[] = [
      {
        id: 'import-reference',
        title: 'Import reference',
        group: 'Project',
        icon: 'music',
        run: () => openImport('reference'),
      },
      {
        id: 'import-take',
        title: 'Import take',
        group: 'Project',
        icon: 'upload',
        run: () => openImport('take'),
      },
      {
        id: 'record-take',
        title: 'Record take',
        group: 'Project',
        icon: 'mic',
        shortcut: 'R',
        disabled: !data.reference,
        run: () => openRecorder(null),
      },
      {
        id: 'analyze',
        title: data.take ? `Analyse again: ${data.take.name}` : 'Analyse the reference again',
        group: 'Project',
        icon: 'refresh',
        disabled: !data.take && !data.reference,
        run: () => {
          if (data.take) void compareTake(projectId, data.take, data.reference?.id ?? null, true)
          else if (data.reference) void analyzeRecording(projectId, data.reference, true)
        },
      },
      {
        id: 'reanalyze-selection',
        title: 'Reanalyse selection (realign region)',
        group: 'Project',
        icon: 'anchor',
        disabled: !comparison || !data.take,
        run: () => {
          const region = useWorkspace.getState().region
          if (region && comparison && data.take)
            void realignRegion(projectId, comparison.id, data.take.id, region)
        },
      },
      {
        id: 'biggest',
        title: 'Find biggest difference',
        group: 'Coaching',
        icon: 'target',
        disabled: !primary,
        run: () => primary && showFinding(primary, mode),
      },
      {
        id: 'next',
        title: 'What should I fix next?',
        group: 'Coaching',
        icon: 'target',
        shortcut: 'N',
        disabled: !comparison?.coaching.next_focus,
        run: () => comparison?.coaching.next_focus && applyFocus(comparison.coaching.next_focus, mode),
      },
      {
        id: 'why',
        title: 'Why does the selection sound different?',
        group: 'Coaching',
        icon: 'bulb',
        shortcut: 'W',
        disabled: !comparison,
        run: () => {
          const { region, selection } = useWorkspace.getState()
          const target = region ?? (selection ? { start: selection.start, end: selection.end } : null)
          if (target) openWhy(target)
        },
      },
      {
        id: 'loop',
        title: 'Loop selection',
        group: 'Playback',
        icon: 'loop',
        shortcut: 'L',
        run: toggleLoop,
      },
      {
        id: 'ab',
        title: 'Toggle reference / take',
        group: 'Playback',
        icon: 'compare',
        shortcut: 'A',
        run: () => engine.toggleAB(),
      },
      {
        id: 'fit',
        title: 'Fit whole recording',
        group: 'View',
        icon: 'fit',
        shortcut: 'Shift+F',
        run: fitAll,
      },
      {
        id: 'previous-take',
        title: previousTake ? `Compare previous take (${previousTake.name})` : 'Compare previous take',
        group: 'Project',
        icon: 'history',
        disabled: !previousTake,
        run: () =>
          previousTake && navigate({ name: 'project', projectId, tab: 'compare', take: previousTake.id }),
      },
      {
        id: 'tab-train',
        title: 'Training mode',
        group: 'Project',
        icon: 'dumbbell',
        run: () => navigate({ name: 'project', projectId, tab: 'train', take, ref: reference }),
      },
      {
        id: 'tab-progress',
        title: 'Progress',
        group: 'Project',
        icon: 'trend-up',
        run: () => navigate({ name: 'project', projectId, tab: 'progress' }),
      },
      {
        id: 'report',
        title: 'Export session report',
        group: 'Export',
        icon: 'file',
        run: () => window.open(projectsApi.reportUrl(projectId, comparison?.id ?? null), '_blank'),
      },
      {
        id: 'progress-csv',
        title: 'Export progress history (CSV)',
        group: 'Export',
        icon: 'download',
        run: () => window.open(projectsApi.progressCsvUrl(projectId), '_blank'),
      },
      {
        id: 'measurements',
        title: 'Show measurements table',
        group: 'View',
        icon: 'list',
        run: () => setUi({ bottomOpen: true, bottomTab: 'measurements' }),
      },
      {
        id: 'previews',
        title: 'Counterfactual previews',
        group: 'View',
        icon: 'wand',
        run: () => setUi({ bottomOpen: true, bottomTab: 'previews' }),
      },
    ]
    for (const layer of LAYERS) {
      list.push({
        id: `layer-${layer.id}`,
        title: `Toggle ${layer.label.toLowerCase()}`,
        group: 'Layers',
        icon: layers?.[layer.id] ? 'eye' : 'eye-off',
        keywords: layer.description,
        run: () => toggleLayer(mode, layer.id),
      })
    }
    return list
  }, [data.comparison, data.reference, data.take, projectId, mode, previousTake, take, reference, layers])
  useRegisterCommands('project', commands)

  if (data.projectError) {
    const missing = data.projectError instanceof ApiError && data.projectError.status === 404
    return (
      <div className="page">
        <div className="page-inner">
          {missing ? (
            <EmptyState
              icon="folder"
              title="This project does not exist"
              actions={<Button onClick={() => navigate({ name: 'home' })}>All projects</Button>}
            >
              It may have been deleted.
            </EmptyState>
          ) : (
            <ErrorState error={data.projectError} />
          )}
        </div>
      </div>
    )
  }
  if (tab === 'train') return <TrainingView data={data} mode={mode} theme={theme} />
  if (tab === 'progress') return <ProgressView data={data} mode={mode} />
  return <Workstation data={data} mode={mode} theme={theme} />
}
