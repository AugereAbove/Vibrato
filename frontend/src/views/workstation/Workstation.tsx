import { useMemo, useState } from 'react'
import { comparisonsApi, recordingsApi } from '../../api/endpoints'
import type { Anchor, Recording } from '../../api/types'
import { engine } from '../../audio/engine'
import { ProjectDialog } from '../../components/project/ProjectDialog'
import { Timeline } from '../../components/timeline/Timeline'
import { fitRange } from '../../components/timeline/viewport'
import { Button } from '../../components/ui/Button'
import { ErrorBoundary } from '../../components/ui/ErrorBoundary'
import { Callout, EmptyState, ErrorState, SkeletonLines } from '../../components/ui/Feedback'
import { Icon } from '../../components/ui/Icon'
import { MenuButton, type MenuEntry } from '../../components/ui/Menu'
import { openContextMenu } from '../../components/ui/contextMenu'
import { LAYERS } from '../../lib/categories'
import { formatTime } from '../../lib/format'
import { keys, useAlignmentPath, useBookmarks, useSections } from '../../state/data'
import { attempt } from '../../state/errors'
import type { ViewMode } from '../../state/prefs'
import { invalidate } from '../../state/resource'
import { resetLayers, setUi, toggleLayer, useLayers, useUi, LIMITS } from '../../state/ui'
import { nextPinId, useWorkspace } from '../../state/workspace'
import { BottomPanel } from './BottomPanel'
import { CoachPanel } from './coach/CoachPanel'
import { WhyDialog } from './coach/WhyDialog'
import { openWhy } from './coach/whyStore'
import { addBookmark, analyzeRecording, compareTake, loopRegion, realignRegion } from './actions'
import { RecordingEditor, SectionsDialog } from './dialogs'
import { DropOverlay, ImportDialog } from './ImportDialog'
import { openImport } from './importStore'
import { Inspector } from './Inspector'
import { PipelineProgress } from './Pipeline'
import { RecordDialog } from './RecordDialog'
import { openRecorder } from './recordStore'
import { useWorkstationShortcuts } from './shortcuts'
import { Sidebar } from './Sidebar'
import { TransportBar } from './TransportBar'
import type { WorkstationData } from './useWorkstation'

function Splitter({
  onDrag,
  orientation,
  label,
}: {
  onDrag: (delta: number) => void
  orientation: 'vertical' | 'horizontal'
  label: string
}) {
  return (
    <div
      className={`splitter splitter-${orientation}`}
      role="separator"
      aria-orientation={orientation}
      aria-label={label}
      tabIndex={0}
      onKeyDown={(event) => {
        const step = event.shiftKey ? 40 : 12
        if (orientation === 'vertical' && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
          event.preventDefault()
          onDrag(event.key === 'ArrowLeft' ? -step : step)
        }
        if (orientation === 'horizontal' && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
          event.preventDefault()
          onDrag(event.key === 'ArrowUp' ? -step : step)
        }
      }}
      onPointerDown={(event) => {
        event.preventDefault()
        const target = event.currentTarget
        target.setPointerCapture(event.pointerId)
        let last = orientation === 'vertical' ? event.clientX : event.clientY
        target.classList.add('is-dragging')
        const move = (e: PointerEvent) => {
          const position = orientation === 'vertical' ? e.clientX : e.clientY
          onDrag(position - last)
          last = position
        }
        const up = () => {
          target.classList.remove('is-dragging')
          target.removeEventListener('pointermove', move)
          target.removeEventListener('pointerup', up)
        }
        target.addEventListener('pointermove', move)
        target.addEventListener('pointerup', up)
      }}
    />
  )
}

function clamp(value: number, [min, max]: readonly [number, number]): number {
  return Math.max(min, Math.min(max, value))
}

export function Workstation({
  data,
  mode,
  theme,
}: {
  data: WorkstationData
  mode: ViewMode
  theme: 'dark' | 'light'
}) {
  const { reference, take, comparison, projectId } = data
  const sidebarOpen = useUi((s) => s.sidebarOpen)
  const inspectorOpen = useUi((s) => s.inspectorOpen)
  const sidebarWidth = useUi((s) => s.sidebarWidth)
  const inspectorWidth = useUi((s) => s.inspectorWidth)
  const bottomHeight = useUi((s) => s.bottomHeight)
  const bottomOpen = useUi((s) => s.bottomOpen)
  const layers = useLayers(mode)
  const bookmarks = useBookmarks(reference?.id ?? null)
  const sections = useSections(reference?.id ?? null)
  const alignment = useAlignmentPath(comparison?.id ?? null)
  const focusKey = useWorkspace((s) => s.focusKey)
  const [editing, setEditing] = useState<Recording | null>(null)
  const [editingSections, setEditingSections] = useState(false)
  const [editingProject, setEditingProject] = useState(false)
  useWorkstationShortcuts(data, mode, true)

  const autoSections = useMemo(() => data.refIndex?.byLevel.section ?? [], [data.refIndex])
  const rulerSections = useMemo(
    () => ((sections.data ?? []).length ? (sections.data ?? []) : autoSections),
    [sections.data, autoSections],
  )
  const anchors = useMemo(() => alignment.data?.anchors ?? [], [alignment.data])
  const focus = comparison?.coaching.findings.find((f) => f.key === focusKey) ?? null
  const refTask = reference ? data.recordingTasks.get(reference.id) : undefined
  const takeTask = take ? data.recordingTasks.get(take.id) : undefined

  const onAnchorMove = async (anchor: Anchor, userTime: number) => {
    const result = await attempt(
      () => comparisonsApi.updateAnchor(anchor.id, { user_time_s: userTime }),
      'Anchor was not moved',
    )
    if (!result || !take) return
    invalidate(keys.alignment(comparison?.id ?? ''))
    await compareTake(projectId, take, reference?.id ?? null, true)
  }

  const contextMenu = (event: React.MouseEvent, t: number) => {
    const workspace = useWorkspace.getState()
    const region =
      workspace.region && t >= workspace.region.start && t <= workspace.region.end ? workspace.region : null
    const items: MenuEntry[] = [
      {
        heading: region
          ? `Selection ${formatTime(region.start)}–${formatTime(region.end)}`
          : `At ${formatTime(t)}`,
      },
    ]
    if (region) {
      items.push(
        {
          label: 'Why does this sound different?',
          icon: 'bulb',
          disabled: !comparison,
          onSelect: () => openWhy(region),
          shortcut: 'W',
        },
        { label: 'Loop selection', icon: 'loop', onSelect: () => loopRegion(region), shortcut: 'L' },
        {
          label: 'Zoom to selection',
          icon: 'fit',
          onSelect: () => fitRange(region.start, region.end),
          shortcut: 'F',
        },
        { label: 'Record this passage', icon: 'mic', onSelect: () => openRecorder(region) },
        {
          label: 'Bookmark selection',
          icon: 'bookmark',
          disabled: !reference,
          onSelect: () => reference && void addBookmark(reference.id, region.start, region.end, 'Selection'),
        },
      )
      if (comparison) {
        items.push(
          {
            label: 'Export A/B snippet',
            icon: 'download',
            onSelect: () =>
              window.open(comparisonsApi.abUrl(comparison.id, region.start, region.end), '_blank'),
          },
          {
            label: 'Realign this region',
            icon: 'anchor',
            onSelect: () => take && void realignRegion(projectId, comparison.id, take.id, region),
          },
        )
      }
      if (reference)
        items.push({
          label: 'Export reference audio',
          icon: 'download',
          onSelect: () =>
            window.open(recordingsApi.segmentUrl(reference.id, region.start, region.end), '_blank'),
        })
      items.push('separator')
    }
    items.push(
      {
        label: 'Play reference from here',
        icon: 'play',
        onSelect: () => {
          engine.setMode('ref')
          void engine.play(t)
        },
      },
      {
        label: 'Play take from here',
        icon: 'play',
        disabled: !take,
        onSelect: () => {
          engine.setMode('take')
          void engine.play(t)
        },
      },
      {
        label: 'Bookmark here',
        icon: 'bookmark',
        disabled: !reference,
        onSelect: () => reference && void addBookmark(reference.id, t, null, 'Bookmark'),
      },
      {
        label: 'Pin measurements here',
        icon: 'pin',
        onSelect: () =>
          useWorkspace.setState((s) => ({
            pins: [...s.pins, { id: nextPinId(), time: t, label: `Pin at ${t.toFixed(2)} s`, values: [] }],
          })),
        hint: 'Alt+click on the timeline pins with values',
      },
    )
    if (comparison && reference && take && mode !== 'coach') {
      items.push({
        label: 'Add alignment anchor here',
        icon: 'anchor',
        hint: 'Locks this reference moment to the matching take moment',
        onSelect: async () => {
          const userTime = data.model.map.refToUser(t)
          const created = await attempt(
            () =>
              comparisonsApi.addAnchor({
                reference_id: reference.id,
                take_id: take.id,
                ref_time_s: t,
                user_time_s: userTime,
                label: 'manual',
              }),
            'Anchor was not added',
          )
          if (created) {
            invalidate(keys.alignment(comparison.id))
            setUi({
              layersByMode: { ...useUi.getState().layersByMode, [mode]: { ...layers, alignment: true } },
            })
          }
        },
      })
    }
    openContextMenu(event, items, 'Timeline actions')
  }

  const layerMenu: MenuEntry[] = [
    { heading: 'Show on the timeline' },
    ...LAYERS.map((layer) => ({
      label: layer.label,
      hint: layer.description,
      checked: layers[layer.id],
      onSelect: () => toggleLayer(mode, layer.id),
    })),
    'separator',
    { label: 'Reset to defaults for this mode', icon: 'refresh', onSelect: () => resetLayers(mode) },
  ]

  let center: React.ReactNode
  if (data.projectLoading && !data.detail) {
    center = (
      <div className="center-pad">
        <SkeletonLines lines={6} />
      </div>
    )
  } else if (!reference) {
    center = (
      <div className="center-pad">
        <EmptyState
          icon="music"
          title="Start with the reference vocal"
          actions={
            <>
              <Button variant="primary" icon="upload" onClick={() => openImport('reference')}>
                Import reference
              </Button>
              <Button variant="ghost" icon="mic" onClick={() => openImport('take')}>
                Import a take instead
              </Button>
            </>
          }
        >
          Import the performance you want to learn from — ideally an isolated vocal. You can also drag a file
          anywhere onto this window. Then record or import your own takes to compare.
        </EmptyState>
      </div>
    )
  } else {
    const takeMissingComparison =
      take && !comparison && !takeTask && data.comparisonId === null && !data.comparisonLoading
    center = (
      <>
        {refTask && data.refAnalysisStatus !== 'ready' ? (
          <PipelineProgress task={refTask} title="Analysing the reference" />
        ) : null}
        {takeTask ? <PipelineProgress task={takeTask} title={`Comparing ${take?.name ?? 'take'}`} /> : null}
        {data.refAnalysisStatus === 'none' && !refTask ? (
          <Callout tone="info" title="The reference has not been analysed yet">
            <Button size="sm" icon="activity" onClick={() => void analyzeRecording(projectId, reference)}>
              Analyse now
            </Button>
          </Callout>
        ) : null}
        {data.refAnalysis?.analysis.outdated && mode !== 'coach' ? (
          <Callout tone="warn" title="This analysis was made by an older version of Vibrato">
            <Button
              size="sm"
              icon="refresh"
              onClick={() => void analyzeRecording(projectId, reference, true)}
            >
              Re-analyse
            </Button>
          </Callout>
        ) : null}
        {takeMissingComparison && take ? (
          <Callout tone="info" title={`${take.name} has not been compared with this reference`}>
            <Button size="sm" icon="compare" onClick={() => void compareTake(projectId, take, reference.id)}>
              Compare now
            </Button>
          </Callout>
        ) : null}
        {data.comparisonError ? (
          <ErrorState error={data.comparisonError} onRetry={data.refreshComparison} compact />
        ) : null}
        {!take && data.refAnalysisStatus === 'ready' ? (
          <div className="take-prompt">
            <Icon name="mic" size={18} />
            <div className="grow">
              <strong>Now sing it yourself.</strong>
              <span className="muted">
                {' '}
                Record a take while the reference plays in your headphones, or import one.
              </span>
            </div>
            <Button variant="primary" icon="record" onClick={() => openRecorder(null)}>
              Record take
            </Button>
            <Button variant="ghost" icon="upload" onClick={() => openImport('take')}>
              Import take
            </Button>
          </div>
        ) : null}
        {comparison ? (
          <CoachPanel comparison={comparison} mode={mode} projectId={projectId} take={take} />
        ) : null}
        {data.refAnalysisStatus === 'ready' || data.refAnalysisStatus === 'none' ? (
          <Timeline
            key={`${reference.id}:${take?.id ?? ''}`}
            model={data.model}
            mode={mode}
            theme={theme}
            layers={layers}
            bookmarks={bookmarks.data ?? []}
            sections={rulerSections}
            anchors={anchors}
            focus={focus}
            onContextMenu={contextMenu}
            onAnchorMove={(anchor, userTime) => void onAnchorMove(anchor, userTime)}
            onBookmarkClick={(bookmark) => engine.seek(bookmark.start_s)}
            toolbarExtra={
              <MenuButton
                icon="layers"
                label="Layers"
                text="Layers"
                items={layerMenu}
                size="xs"
                variant="subtle"
              />
            }
          />
        ) : data.refAnalysisStatus === 'loading' ? (
          <div className="center-pad">
            <SkeletonLines lines={5} />
          </div>
        ) : null}
        {bottomOpen ? (
          <Splitter
            orientation="horizontal"
            label="Resize details panel"
            onDrag={(delta) =>
              setUi({ bottomHeight: clamp(useUi.getState().bottomHeight - delta, LIMITS.bottom) })
            }
          />
        ) : null}
        <div className="bottom-slot" style={{ height: bottomOpen ? bottomHeight : undefined }}>
          <ErrorBoundary label="details panel" resetKey={`${take?.id}:${mode}`}>
            <BottomPanel data={data} mode={mode} />
          </ErrorBoundary>
        </div>
      </>
    )
  }

  return (
    <div className="workstation-shell">
      <div
        className="workstation"
        style={{
          gridTemplateColumns: `${sidebarOpen ? `${sidebarWidth}px` : '0px'} ${sidebarOpen ? '4px' : '0px'} minmax(0, 1fr) ${inspectorOpen ? '4px' : '0px'} ${inspectorOpen ? `${inspectorWidth}px` : '0px'}`,
        }}
      >
        <div className={`sidebar-slot${sidebarOpen ? '' : ' is-collapsed'}`}>
          {sidebarOpen ? (
            <Sidebar
              data={data}
              bookmarks={bookmarks.data ?? []}
              sections={sections.data ?? []}
              autoSections={autoSections}
              onEditRecording={setEditing}
              onEditSections={() => setEditingSections(true)}
              onEditProject={() => setEditingProject(true)}
              onClose={() => setUi({ sidebarOpen: false })}
            />
          ) : null}
        </div>
        {sidebarOpen ? (
          <Splitter
            orientation="vertical"
            label="Resize sidebar"
            onDrag={(delta) =>
              setUi({ sidebarWidth: clamp(useUi.getState().sidebarWidth + delta, LIMITS.sidebar) })
            }
          />
        ) : (
          <span />
        )}
        <main className="center" aria-label="Comparison workspace">
          {!sidebarOpen ? (
            <button
              type="button"
              className="edge-toggle edge-left"
              aria-label="Show sidebar"
              onClick={() => setUi({ sidebarOpen: true })}
            >
              <Icon name="chevron-right" size={14} />
            </button>
          ) : null}
          {!inspectorOpen ? (
            <button
              type="button"
              className="edge-toggle edge-right"
              aria-label="Show inspector"
              onClick={() => setUi({ inspectorOpen: true })}
            >
              <Icon name="chevron-left" size={14} />
            </button>
          ) : null}
          <div className="center-scroll">
            <ErrorBoundary label="comparison workspace" resetKey={`${reference?.id}:${take?.id}`}>
              {center}
            </ErrorBoundary>
          </div>
        </main>
        {inspectorOpen ? (
          <Splitter
            orientation="vertical"
            label="Resize inspector"
            onDrag={(delta) =>
              setUi({ inspectorWidth: clamp(useUi.getState().inspectorWidth - delta, LIMITS.inspector) })
            }
          />
        ) : (
          <span />
        )}
        <div className={`inspector-slot${inspectorOpen ? '' : ' is-collapsed'}`}>
          {inspectorOpen ? (
            <ErrorBoundary label="inspector" resetKey={`${take?.id}:${mode}`}>
              <Inspector data={data} mode={mode} onClose={() => setUi({ inspectorOpen: false })} />
            </ErrorBoundary>
          ) : null}
        </div>
      </div>
      <TransportBar
        projectId={projectId}
        takes={data.takes}
        currentTake={take}
        hasReference={Boolean(reference)}
        duration={data.model.duration}
      />
      <ImportDialog projectId={projectId} reference={reference} />
      <RecordDialog projectId={projectId} reference={reference} takes={data.takes} />
      <WhyDialog
        comparisonId={comparison?.id ?? null}
        mode={mode}
        projectId={projectId}
        take={take}
        referenceId={reference?.id ?? null}
      />
      {editing ? (
        <RecordingEditor
          projectId={projectId}
          recording={editing}
          words={editing.id === reference?.id ? (data.refIndex?.byLevel.word ?? []) : []}
          onClose={() => setEditing(null)}
        />
      ) : null}
      <SectionsDialog
        open={editingSections}
        onClose={() => setEditingSections(false)}
        reference={reference}
        sections={sections.data ?? []}
        automatic={autoSections}
      />
      <ProjectDialog
        open={editingProject}
        project={data.detail?.project ?? null}
        onClose={() => setEditingProject(false)}
      />
      <DropOverlay onDrop={(files, kind) => openImport(kind, files)} />
    </div>
  )
}
