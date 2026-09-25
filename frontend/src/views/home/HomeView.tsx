import { useMemo, useRef, useState } from 'react'
import { projectsApi } from '../../api/endpoints'
import type { Project } from '../../api/types'
import { ProjectDialog } from '../../components/project/ProjectDialog'
import { Badge } from '../../components/ui/Badge'
import { Button, IconButton } from '../../components/ui/Button'
import { Segmented, Select, TextField } from '../../components/ui/Controls'
import { confirmAction } from '../../components/ui/confirm'
import { EmptyState, ErrorState, ProgressBar, Skeleton } from '../../components/ui/Feedback'
import { Icon } from '../../components/ui/Icon'
import { MenuButton, type MenuEntry } from '../../components/ui/Menu'
import { openContextMenu } from '../../components/ui/contextMenu'
import { ScoreRing } from '../../components/ui/Motion'
import { relativeTime } from '../../lib/format'
import { useProjects } from '../../state/data'
import { attempt } from '../../state/errors'
import { navigate } from '../../state/router'
import { useTaskStore } from '../../state/tasks'
import { downloadBackup, patchProject, refreshList, startDemo } from './projectActions'
import { setUi, useUi } from '../../state/ui'

function projectMenu(project: Project, onEdit: () => void): MenuEntry[] {
  return [
    {
      label: 'Open',
      icon: 'folder',
      onSelect: () => navigate({ name: 'project', projectId: project.id, tab: 'compare' }),
    },
    { label: 'Edit details…', icon: 'edit', onSelect: onEdit },
    {
      label: project.favorite ? 'Remove from favourites' : 'Add to favourites',
      icon: 'star',
      onSelect: () =>
        void patchProject(project, { favorite: !project.favorite }, 'Favourite project', {
          favorite: Boolean(project.favorite),
        }),
    },
    {
      label: 'Duplicate',
      icon: 'copy',
      onSelect: () =>
        void attempt(async () => {
          await projectsApi.duplicate(project.id)
          refreshList()
        }, 'Duplicate failed'),
    },
    { label: 'Back up as .zip', icon: 'download', onSelect: () => void downloadBackup(project) },
    {
      label: project.archived ? 'Unarchive' : 'Archive',
      icon: 'archive',
      onSelect: () =>
        void patchProject(
          project,
          { archived: !project.archived },
          project.archived ? 'Unarchive project' : 'Archive project',
          { archived: Boolean(project.archived) },
        ),
    },
    'separator',
    {
      label: 'Delete…',
      icon: 'trash',
      danger: true,
      onSelect: async () => {
        const ok = await confirmAction({
          title: `Delete “${project.name}”?`,
          body: 'All recordings, analyses, comparisons and progress history in this project are deleted. This cannot be undone. Consider backing it up first.',
          confirmLabel: 'Delete project',
          danger: true,
        })
        if (!ok) return
        await attempt(async () => {
          await projectsApi.remove(project.id)
          refreshList()
        }, 'Delete failed')
      },
    },
  ]
}

function ProjectCard({ project, onEdit }: { project: Project; onEdit: (project: Project) => void }) {
  const open = () => navigate({ name: 'project', projectId: project.id, tab: 'compare' })
  return (
    <article
      className="project-card"
      onContextMenu={(event) =>
        openContextMenu(
          event,
          projectMenu(project, () => onEdit(project)),
          project.name,
        )
      }
    >
      <button type="button" className="project-card-main" onClick={open} aria-label={`Open ${project.name}`}>
        <div className="project-card-head">
          <div className="project-art" aria-hidden>
            <Icon name={project.is_demo ? 'flask' : 'music'} size={18} />
          </div>
          <div className="grow" style={{ minWidth: 0 }}>
            <h3 className="truncate">{project.name}</h3>
            <p className="small muted truncate">
              {project.song_title || 'Untitled song'}
              {project.song_artist ? ` · ${project.song_artist}` : ''}
            </p>
          </div>
          <ScoreRing score={project.best_score} size={42} label="Best take score" />
        </div>
        <div className="project-card-meta">
          <span>
            <Icon name="music" size={12} /> {project.reference_count} ref
          </span>
          <span>
            <Icon name="mic" size={12} /> {project.take_count} take{project.take_count === 1 ? '' : 's'}
          </span>
          <span className="faint">opened {relativeTime(project.last_opened_at ?? project.updated_at)}</span>
          {project.is_demo ? <Badge tone="synthetic">demo</Badge> : null}
          {project.archived ? <Badge>archived</Badge> : null}
        </div>
      </button>
      <div className="project-card-actions">
        <IconButton
          icon={project.favorite ? 'star-filled' : 'star'}
          label={project.favorite ? 'Remove from favourites' : 'Add to favourites'}
          size="xs"
          className={project.favorite ? 'is-favorite' : undefined}
          onClick={() =>
            void patchProject(project, { favorite: !project.favorite }, 'Favourite project', {
              favorite: Boolean(project.favorite),
            })
          }
        />
        <MenuButton
          label={`Actions for ${project.name}`}
          items={() => projectMenu(project, () => onEdit(project))}
          size="xs"
        />
      </div>
    </article>
  )
}

function Onboarding({ onCreate }: { onCreate: () => void }) {
  const demoTask = useTaskStore((s) =>
    Object.values(s.tasks).find(
      (t) => t.kind === 'demo' && (t.status === 'running' || t.status === 'queued'),
    ),
  )
  const steps = [
    ['Create a project', 'One project per song you are learning.'],
    ['Import the reference', 'The vocal you want to imitate — an isolated vocal works best.'],
    ['Record or import your take', 'Sing along with the reference in your headphones.'],
    ['See what differs', 'Pitch, timing, vibrato, vowels, dynamics, breath and tone, aligned note by note.'],
    ['Fix one thing at a time', '“What should I fix next?” picks the most useful target and loops it.'],
  ]
  return (
    <section className="onboarding card">
      <div className="onboarding-copy">
        <span className="eyebrow">Welcome to Vibrato</span>
        <h2>Learn a vocal performance by measuring what makes it sound the way it does.</h2>
        <p className="muted">
          Vibrato compares your singing with a reference recording, explains the biggest audible differences
          and helps you practise them. Everything runs on this computer: no accounts, no uploads.
        </p>
        <div className="row-wrap" style={{ marginTop: 14 }}>
          <Button variant="primary" size="lg" icon="flask" onClick={startDemo} loading={Boolean(demoTask)}>
            Explore the demo project
          </Button>
          <Button size="lg" icon="plus" onClick={onCreate}>
            New project
          </Button>
        </div>
        {demoTask ? (
          <div style={{ marginTop: 12, maxWidth: 360 }}>
            <ProgressBar value={demoTask.progress} label="Building demo" />
            <p className="tiny faint">{demoTask.message}</p>
          </div>
        ) : null}
        <p className="tiny faint" style={{ marginTop: 10 }}>
          The demo uses a synthetic singer generated by Vibrato itself, with deliberate differences planted in
          three practice takes.
        </p>
      </div>
      <ol className="onboarding-steps">
        {steps.map(([title, body], index) => (
          <li key={title}>
            <span className="step-number">{index + 1}</span>
            <div>
              <strong>{title}</strong>
              <p className="small muted">{body}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  )
}

export function HomeView() {
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('recent')
  const [filter, setFilter] = useState<'all' | 'favorites' | 'archived'>('all')
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Project | null>(null)
  const onboardingDismissed = useUi((s) => s.onboardingDismissed)
  const restoreInput = useRef<HTMLInputElement>(null)
  const projects = useProjects(search, sort, filter === 'archived', filter === 'favorites')
  const list = useMemo(() => projects.data ?? [], [projects.data])
  const firstRun = !projects.loading && list.length === 0 && !search && filter === 'all'
  const demoTask = useTaskStore((s) =>
    Object.values(s.tasks).find(
      (t) => t.kind === 'demo' && (t.status === 'running' || t.status === 'queued'),
    ),
  )
  const hasDemo = list.some((p) => p.is_demo)
  return (
    <div className="page home">
      <div className="page-inner">
        {(firstRun || !onboardingDismissed) && !projects.error ? (
          <div className="onboarding-wrap">
            <Onboarding onCreate={() => setCreating(true)} />
            {!firstRun ? (
              <button
                type="button"
                className="link-button onboarding-dismiss"
                onClick={() => setUi({ onboardingDismissed: true })}
              >
                Hide introduction
              </button>
            ) : null}
          </div>
        ) : null}
        <div className="page-header">
          <div>
            <h1>Projects</h1>
            <p className="muted">Each project holds one song: references, your takes and your progress.</p>
          </div>
          <div className="row-wrap">
            <input
              ref={restoreInput}
              type="file"
              accept=".zip,application/zip"
              hidden
              onChange={async (event) => {
                const file = event.target.files?.[0]
                event.target.value = ''
                if (!file) return
                const result = await attempt(() => projectsApi.restore(file), 'Restore failed')
                if (result) {
                  refreshList()
                  navigate({ name: 'project', projectId: result.project.id, tab: 'compare' })
                }
              }}
            />
            <Button variant="ghost" icon="upload" onClick={() => restoreInput.current?.click()}>
              Restore backup
            </Button>
            {!hasDemo ? (
              <Button variant="ghost" icon="flask" onClick={startDemo} loading={Boolean(demoTask)}>
                Demo project
              </Button>
            ) : null}
            <Button variant="primary" icon="plus" onClick={() => setCreating(true)}>
              New project
            </Button>
          </div>
        </div>
        <div className="home-toolbar">
          <div style={{ width: 280 }}>
            <TextField
              icon="search"
              placeholder="Search projects, songs or singers"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search projects"
            />
          </div>
          <Segmented
            ariaLabel="Filter projects"
            value={filter}
            onChange={setFilter}
            options={[
              { value: 'all', label: 'All' },
              { value: 'favorites', label: 'Favourites', icon: 'star' },
              { value: 'archived', label: 'Archived', icon: 'archive' },
            ]}
          />
          <span className="spacer" />
          <div style={{ width: 190 }}>
            <Select
              ariaLabel="Sort projects"
              value={sort}
              onChange={setSort}
              options={[
                { value: 'recent', label: 'Recently opened' },
                { value: 'updated', label: 'Recently changed' },
                { value: 'name', label: 'Name' },
                { value: 'created', label: 'Newest first' },
                { value: 'score', label: 'Best score' },
              ]}
            />
          </div>
        </div>
        {projects.error ? (
          <ErrorState error={projects.error} onRetry={() => void projects.refresh()} />
        ) : null}
        {projects.loading ? (
          <div className="project-grid">
            {Array.from({ length: 3 }, (_, i) => (
              <div key={i} className="project-card is-skeleton">
                <Skeleton height={18} width="60%" />
                <Skeleton height={12} width="40%" />
                <Skeleton height={10} width="80%" />
              </div>
            ))}
          </div>
        ) : list.length === 0 && !firstRun ? (
          <EmptyState
            icon="search"
            title={filter === 'archived' ? 'No archived projects' : 'No projects match'}
          >
            {search ? 'Try a different search.' : 'Create a project to get started.'}
          </EmptyState>
        ) : (
          <div className="project-grid">
            {list.map((project) => (
              <ProjectCard key={project.id} project={project} onEdit={setEditing} />
            ))}
          </div>
        )}
        <p className="privacy-note">
          <Icon name="shield" size={13} /> Local only: audio and analyses stay in Vibrato’s data folder on
          this computer. No telemetry.
        </p>
      </div>
      <ProjectDialog
        open={creating || editing !== null}
        project={editing}
        onClose={() => {
          setCreating(false)
          setEditing(null)
        }}
        onSaved={(project) => {
          if (creating) navigate({ name: 'project', projectId: project.id, tab: 'compare' })
        }}
      />
    </div>
  )
}
