import { useState, type ReactNode } from 'react'
import { recordingsApi } from '../../api/endpoints'
import type { Bookmark, Recording, Segment, SongSection, Task } from '../../api/types'
import { engine } from '../../audio/engine'
import { fitRange } from '../../components/timeline/viewport'
import { Badge } from '../../components/ui/Badge'
import { Button, IconButton } from '../../components/ui/Button'
import { ProgressBar } from '../../components/ui/Feedback'
import { Icon } from '../../components/ui/Icon'
import { type MenuEntry } from '../../components/ui/Menu'
import { openContextMenu } from '../../components/ui/contextMenu'
import { scoreTone } from '../../lib/score'
import { Tooltip } from '../../components/ui/Tooltip'
import { CATEGORY_ICONS, CATEGORY_ORDER, categoryLabel } from '../../lib/categories'
import { formatDuration, formatScore, formatTime, relativeTime } from '../../lib/format'
import { navigate } from '../../state/router'
import { setUi, useUi } from '../../state/ui'
import { useWorkspace } from '../../state/workspace'
import type { WorkstationData } from './useWorkstation'
import {
  addBookmark,
  analyzeRecording,
  compareTake,
  deleteRecording,
  loopRegion,
  removeBookmark,
  renameBookmark,
  updateRecording,
} from './actions'
import { openImport } from './importStore'
import { openRecorder } from './recordStore'

function SideSection({
  id,
  title,
  count,
  actions,
  children,
}: {
  id: string
  title: string
  count?: number
  actions?: ReactNode
  children: ReactNode
}) {
  const collapsed = useUi((s) => s.sidebarSections[id] === false)
  return (
    <section className="side-section">
      <div className="side-section-header">
        <button
          type="button"
          className="panel-section-header"
          aria-expanded={!collapsed}
          onClick={() =>
            useUi.setState((s) => ({ sidebarSections: { ...s.sidebarSections, [id]: collapsed } }))
          }
        >
          <Icon name="chevron-down" size={12} className="chevron" />
          {title}
          {count !== undefined ? <span className="side-count">{count}</span> : null}
        </button>
        <div className="side-actions">{actions}</div>
      </div>
      {!collapsed ? <div className="side-section-body">{children}</div> : null}
    </section>
  )
}

function TaskLine({ task }: { task: Task | undefined }) {
  if (!task) return null
  return (
    <div className="side-task" title={task.message}>
      <ProgressBar value={task.progress} label={task.message} />
      <span className="tiny faint truncate">{task.message || task.stage}</span>
    </div>
  )
}

export function Sidebar({
  data,
  bookmarks,
  sections,
  autoSections,
  onEditRecording,
  onEditSections,
  onEditProject,
  onClose,
}: {
  data: WorkstationData
  bookmarks: Bookmark[]
  sections: SongSection[]
  autoSections: Segment[]
  onEditRecording: (recording: Recording) => void
  onEditSections: () => void
  onEditProject: () => void
  onClose: () => void
}) {
  const { detail, references, takes, reference, take, projectId, comparison, recordingTasks } = data
  const [editingBookmark, setEditingBookmark] = useState<string | null>(null)
  const project = detail?.project
  const referenceMenu = (recording: Recording): MenuEntry[] => [
    {
      label: 'Open',
      icon: 'folder',
      onSelect: () => navigate({ name: 'project', projectId, tab: 'compare', ref: recording.id }),
    },
    { label: 'Details, lyrics and pronunciation…', icon: 'edit', onSelect: () => onEditRecording(recording) },
    {
      label: recording.is_primary ? 'Main reference' : 'Make main reference',
      icon: 'star',
      disabled: Boolean(recording.is_primary),
      onSelect: () =>
        void updateRecording(projectId, recording, { is_primary: true }, 'Change main reference'),
    },
    {
      label: 'Re-analyse',
      icon: 'refresh',
      onSelect: () => void analyzeRecording(projectId, recording, true),
    },
    {
      label: 'Download original file',
      icon: 'download',
      onSelect: () => window.open(recordingsApi.originalUrl(recording.id), '_blank'),
    },
    'separator',
    {
      label: 'Delete reference…',
      icon: 'trash',
      danger: true,
      onSelect: () => void deleteRecording(projectId, recording),
    },
  ]
  const takeMenu = (recording: Recording): MenuEntry[] => [
    {
      label: 'Open',
      icon: 'folder',
      onSelect: () => navigate({ name: 'project', projectId, tab: 'compare', take: recording.id }),
    },
    { label: 'Rename and notes…', icon: 'edit', onSelect: () => onEditRecording(recording) },
    {
      label: recording.favorite ? 'Remove from favourites' : 'Mark as favourite',
      icon: 'star',
      onSelect: () =>
        void updateRecording(
          projectId,
          recording,
          { favorite: !recording.favorite },
          recording.favorite ? 'Unfavourite take' : 'Favourite take',
        ),
    },
    {
      label: 'Compare again',
      icon: 'compare',
      disabled: !reference,
      onSelect: () => void compareTake(projectId, recording, reference?.id ?? null, true),
    },
    {
      label: 'Download original file',
      icon: 'download',
      onSelect: () => window.open(recordingsApi.originalUrl(recording.id), '_blank'),
    },
    'separator',
    {
      label: 'Delete take…',
      icon: 'trash',
      danger: true,
      onSelect: () => void deleteRecording(projectId, recording),
    },
  ]
  const categories = comparison?.scores.categories
  const sessions = (detail?.sessions ?? []).filter((s) => s.takes > 0 || s.notes || s.active_seconds >= 60)
  const shownSections = sections.length ? sections : autoSections
  return (
    <nav className="sidebar" aria-label="Project navigation">
      <header className="panel-header">
        <button
          type="button"
          className="sidebar-project"
          onClick={onEditProject}
          title="Edit project details"
        >
          <span className="sidebar-project-name truncate">{project?.name ?? 'Project'}</span>
          {project?.song_title ? (
            <span className="sidebar-project-song truncate">
              {project.song_title}
              {project.song_artist ? ` · ${project.song_artist}` : ''}
            </span>
          ) : null}
        </button>
        <IconButton icon="chevron-left" label="Collapse sidebar" size="xs" onClick={onClose} />
      </header>
      <div className="sidebar-body">
        <SideSection
          id="references"
          title="Reference vocals"
          count={references.length}
          actions={
            <IconButton
              icon="plus"
              label="Import reference"
              size="xs"
              onClick={() => openImport('reference')}
            />
          }
        >
          {references.length === 0 ? (
            <button type="button" className="side-empty" onClick={() => openImport('reference')}>
              <Icon name="upload" size={14} /> Import the vocal you want to learn
            </button>
          ) : null}
          {references.map((recording) => {
            const issues = (recording.qc?.issues ?? []).filter((i) => i.severity !== 'info')
            return (
              <div key={recording.id}>
                <button
                  type="button"
                  className={`side-item${recording.id === reference?.id ? ' is-active' : ''}`}
                  onClick={() => navigate({ name: 'project', projectId, tab: data.tab, ref: recording.id })}
                  onContextMenu={(event) => openContextMenu(event, referenceMenu(recording), recording.name)}
                >
                  <Icon name="music" size={14} className="ref-text" />
                  <span className="grow truncate">{recording.name}</span>
                  {recording.is_primary ? (
                    <Icon name="star-filled" size={11} className="faint" title="Main reference" />
                  ) : null}
                  {issues.length ? (
                    <Icon
                      name="alert"
                      size={12}
                      className="warn-text"
                      title={issues.map((i) => i.title).join(', ')}
                    />
                  ) : null}
                  <span className="tiny faint num">{formatDuration(recording.duration_s)}</span>
                </button>
                <TaskLine task={recordingTasks.get(recording.id)} />
              </div>
            )
          })}
        </SideSection>
        <SideSection
          id="takes"
          title="Takes"
          count={takes.length}
          actions={
            <>
              <IconButton icon="upload" label="Import take" size="xs" onClick={() => openImport('take')} />
              <IconButton
                icon="mic"
                label="Record take"
                shortcut="R"
                size="xs"
                onClick={() => openRecorder(null)}
              />
            </>
          }
        >
          {takes.length === 0 ? (
            <div className="stack" style={{ gap: 6, padding: '0 4px' }}>
              <Button
                size="sm"
                variant="subtle"
                icon="mic"
                onClick={() => openRecorder(null)}
                disabled={!reference}
              >
                Record your first take
              </Button>
              <Button size="sm" variant="ghost" icon="upload" onClick={() => openImport('take')}>
                Import a take
              </Button>
            </div>
          ) : null}
          {[...takes].reverse().map((recording) => (
            <div key={recording.id}>
              <button
                type="button"
                className={`side-item take-item${recording.id === take?.id ? ' is-active' : ''}`}
                onClick={() => navigate({ name: 'project', projectId, tab: data.tab, take: recording.id })}
                onContextMenu={(event) => openContextMenu(event, takeMenu(recording), recording.name)}
              >
                <span className={`take-score tone-${scoreTone(recording.overall_score)}`}>
                  {formatScore(recording.overall_score)}
                </span>
                <span className="grow stack" style={{ gap: 0 }}>
                  <span className="truncate">{recording.name}</span>
                  <span className="tiny faint">
                    {recording.source === 'record' ? 'recorded' : 'imported'}{' '}
                    {relativeTime(recording.created_at)}
                    {recording.region_start_s != null
                      ? ` · ${formatTime(recording.region_start_s, 0)}–${formatTime(recording.region_end_s ?? 0, 0)}`
                      : ''}
                  </span>
                </span>
                {recording.favorite ? <Icon name="star-filled" size={11} className="ref-text" /> : null}
              </button>
              <TaskLine task={recordingTasks.get(recording.id)} />
            </div>
          ))}
        </SideSection>
        <SideSection
          id="sections"
          title="Song sections"
          count={shownSections.length}
          actions={
            <IconButton
              icon="edit"
              label="Edit sections"
              size="xs"
              onClick={onEditSections}
              disabled={!reference}
            />
          }
        >
          {shownSections.length === 0 ? (
            <p className="side-hint">Sections appear after the reference is analysed.</p>
          ) : null}
          {shownSections.map((section) => (
            <button
              key={section.id}
              type="button"
              className="side-item"
              onClick={() => {
                fitRange(section.start_s, section.end_s, 0.05)
                useWorkspace.setState({ region: { start: section.start_s, end: section.end_s } })
              }}
              onDoubleClick={() => {
                loopRegion({ start: section.start_s, end: section.end_s })
                void engine.play(section.start_s)
              }}
              onContextMenu={(event) =>
                openContextMenu(event, [
                  {
                    label: 'Loop section',
                    icon: 'loop',
                    onSelect: () => loopRegion({ start: section.start_s, end: section.end_s }),
                  },
                  {
                    label: 'Record this section',
                    icon: 'mic',
                    onSelect: () => openRecorder({ start: section.start_s, end: section.end_s }),
                  },
                  { label: 'Edit sections…', icon: 'edit', onSelect: onEditSections },
                ])
              }
            >
              <Icon name="layers" size={13} className="faint" />
              <span className="grow truncate">{section.label}</span>
              <span className="tiny faint num">
                {formatTime(section.start_s, 0)}–{formatTime(section.end_s, 0)}
              </span>
            </button>
          ))}
        </SideSection>
        <SideSection
          id="bookmarks"
          title="Bookmarks"
          count={bookmarks.length}
          actions={
            <IconButton
              icon="plus"
              label="Bookmark the playhead (B)"
              size="xs"
              disabled={!reference}
              onClick={() => {
                const region = useWorkspace.getState().region
                if (reference)
                  void addBookmark(
                    reference.id,
                    region?.start ?? engine.position(),
                    region?.end ?? null,
                    `Bookmark ${bookmarks.length + 1}`,
                  )
              }}
            />
          }
        >
          {bookmarks.length === 0 ? <p className="side-hint">Press B to bookmark the playhead.</p> : null}
          {bookmarks.map((bookmark) =>
            editingBookmark === bookmark.id ? (
              <input
                key={bookmark.id}
                className="input side-input"
                defaultValue={bookmark.label}
                aria-label="Bookmark name"
                autoFocus
                onBlur={(event) => {
                  setEditingBookmark(null)
                  if (event.target.value.trim() && event.target.value !== bookmark.label)
                    void renameBookmark(bookmark, event.target.value.trim())
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') (event.target as HTMLInputElement).blur()
                  if (event.key === 'Escape') setEditingBookmark(null)
                }}
              />
            ) : (
              <button
                key={bookmark.id}
                type="button"
                className="side-item bookmark-item"
                onClick={() => {
                  engine.seek(bookmark.start_s)
                  if (bookmark.end_s != null)
                    useWorkspace.setState({ region: { start: bookmark.start_s, end: bookmark.end_s } })
                }}
                onDoubleClick={() => setEditingBookmark(bookmark.id)}
                onContextMenu={(event) =>
                  openContextMenu(event, [
                    { label: 'Rename', icon: 'edit', onSelect: () => setEditingBookmark(bookmark.id) },
                    {
                      label: 'Loop',
                      icon: 'loop',
                      disabled: bookmark.end_s == null,
                      onSelect: () =>
                        bookmark.end_s != null &&
                        loopRegion({ start: bookmark.start_s, end: bookmark.end_s }),
                    },
                    'separator',
                    {
                      label: 'Delete',
                      icon: 'trash',
                      danger: true,
                      onSelect: () => void removeBookmark(bookmark),
                    },
                  ])
                }
              >
                <Icon name="bookmark" size={13} className="ref-text" />
                <span className="grow truncate">{bookmark.label || 'Bookmark'}</span>
                <span className="tiny faint num">{formatTime(bookmark.start_s, 1)}</span>
              </button>
            ),
          )}
        </SideSection>
        {categories ? (
          <SideSection id="analyzers" title="Analysis">
            {CATEGORY_ORDER.map((category) => {
              const score = categories[category]
              if (!score) return null
              return (
                <Tooltip
                  key={category}
                  content={`${score.count} measurements · confidence ${Math.round(score.confidence * 100)}%`}
                  side="right"
                  block
                >
                  <button
                    type="button"
                    className="side-item"
                    onClick={() =>
                      setUi({
                        bottomOpen: true,
                        bottomTab: 'measurements',
                        tableFilters: {
                          category,
                          minConfidence: 0,
                          minMagnitude: 0,
                          search: '',
                          onlyFlagged: false,
                        },
                      })
                    }
                  >
                    <Icon
                      name={CATEGORY_ICONS[category]}
                      size={13}
                      style={{ color: `var(--cat-${category})` }}
                    />
                    <span className="grow">{categoryLabel(category)}</span>
                    {score.confidence < 0.5 ? <Badge tone="warn">low conf.</Badge> : null}
                    <span className={`num small tone-text-${scoreTone(score.score)}`}>
                      {formatScore(score.score)}
                    </span>
                  </button>
                </Tooltip>
              )
            })}
          </SideSection>
        ) : null}
        <SideSection id="sessions" title="Practice history" count={sessions.length}>
          {sessions.length === 0 ? <p className="side-hint">Sessions are recorded as you practise.</p> : null}
          {sessions.slice(0, 8).map((session) => (
            <button
              key={session.id}
              type="button"
              className="side-item"
              onClick={() => navigate({ name: 'project', projectId, tab: 'progress' })}
            >
              <Icon name="calendar" size={13} className="faint" />
              <span className="grow stack" style={{ gap: 0 }}>
                <span className="truncate">
                  {new Date(session.started_at).toLocaleDateString(undefined, {
                    day: 'numeric',
                    month: 'short',
                  })}
                </span>
                <span className="tiny faint">
                  {session.takes} take{session.takes === 1 ? '' : 's'} ·{' '}
                  {formatDuration(session.active_seconds)}
                </span>
              </span>
            </button>
          ))}
        </SideSection>
      </div>
    </nav>
  )
}
