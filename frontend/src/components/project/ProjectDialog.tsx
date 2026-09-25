import { useEffect, useState } from 'react'
import { projectsApi } from '../../api/endpoints'
import type { Project } from '../../api/types'
import { keys } from '../../state/data'
import { reportError } from '../../state/errors'
import { pushUndo } from '../../state/history'
import { invalidate } from '../../state/resource'
import { beginSave } from '../../state/tasks'
import { Button } from '../ui/Button'
import { TextArea, TextField } from '../ui/Controls'
import { Dialog } from '../ui/Dialog'

export interface ProjectFields {
  name: string
  song_title: string
  song_artist: string
  singer_label: string
  notes: string
}

const EMPTY: ProjectFields = { name: '', song_title: '', song_artist: '', singer_label: '', notes: '' }

export function ProjectDialog({
  open,
  project,
  onClose,
  onSaved,
}: {
  open: boolean
  project?: Project | null
  onClose: () => void
  onSaved?: (project: Project) => void
}) {
  const [fields, setFields] = useState<ProjectFields>(EMPTY)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!open) return
    const frame = window.requestAnimationFrame(() =>
      setFields(
        project
          ? {
              name: project.name,
              song_title: project.song_title,
              song_artist: project.song_artist,
              singer_label: project.singer_label,
              notes: project.notes,
            }
          : EMPTY,
      ),
    )
    return () => window.cancelAnimationFrame(frame)
  }, [open, project])
  const set =
    (key: keyof ProjectFields) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setFields((f) => ({ ...f, [key]: event.target.value }))
  const submit = async () => {
    if (!fields.name.trim()) return
    setBusy(true)
    const end = beginSave()
    try {
      if (project) {
        const before: ProjectFields = {
          name: project.name,
          song_title: project.song_title,
          song_artist: project.song_artist,
          singer_label: project.singer_label,
          notes: project.notes,
        }
        const after = { ...fields, name: fields.name.trim() }
        const apply = async (values: ProjectFields) => {
          await projectsApi.update(project.id, values)
          invalidate(keys.project(project.id))
          invalidate((key) => key.startsWith('projects:'))
        }
        const { project: saved } = await projectsApi.update(project.id, after)
        invalidate(keys.project(project.id))
        invalidate((key) => key.startsWith('projects:'))
        pushUndo({ label: 'Edit project details', undo: () => apply(before), redo: () => apply(after) })
        onSaved?.(saved)
      } else {
        const { project: created } = await projectsApi.create({ ...fields, name: fields.name.trim() })
        invalidate((key) => key.startsWith('projects:'))
        onSaved?.(created)
      }
      onClose()
    } catch (error) {
      reportError(error, project ? 'Project was not saved' : 'Project was not created')
    } finally {
      end()
      setBusy(false)
    }
  }
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={project ? 'Project details' : 'New project'}
      description={
        project
          ? undefined
          : 'A project holds one song: its reference vocal(s), your takes and your progress.'
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => void submit()}
            disabled={!fields.name.trim()}
            loading={busy}
          >
            {project ? 'Save' : 'Create project'}
          </Button>
        </>
      }
    >
      <form
        className="stack"
        style={{ gap: 12 }}
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        <TextField
          label="Project name"
          value={fields.name}
          onChange={set('name')}
          placeholder="e.g. Harbor Light – verse practice"
          data-autofocus
          required
        />
        <div className="form-grid">
          <TextField label="Song title" value={fields.song_title} onChange={set('song_title')} />
          <TextField label="Artist" value={fields.song_artist} onChange={set('song_artist')} />
        </div>
        <TextField
          label="Reference singer label"
          value={fields.singer_label}
          onChange={set('singer_label')}
          hint="Only used to organise your reference profiles."
        />
        <TextArea label="Notes" value={fields.notes} onChange={set('notes')} rows={3} />
        <button type="submit" hidden />
      </form>
    </Dialog>
  )
}
