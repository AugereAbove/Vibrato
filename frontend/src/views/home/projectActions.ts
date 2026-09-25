import { projectsApi } from '../../api/endpoints'
import type { Project } from '../../api/types'
import { attempt, reportError } from '../../state/errors'
import { pushUndo } from '../../state/history'
import { invalidate } from '../../state/resource'
import { navigate } from '../../state/router'
import { beginSave, trackTask } from '../../state/tasks'

export function refreshList(): void {
  invalidate((key) => key.startsWith('projects:'))
}

export async function patchProject(
  project: Project,
  patch: Parameters<typeof projectsApi.update>[1],
  label: string,
  inverse: Parameters<typeof projectsApi.update>[1],
) {
  const apply = async (values: Parameters<typeof projectsApi.update>[1]) => {
    const end = beginSave()
    try {
      await projectsApi.update(project.id, values)
      refreshList()
      invalidate(`project:${project.id}`)
    } finally {
      end()
    }
  }
  try {
    await apply(patch)
    pushUndo({ label, undo: () => apply(inverse), redo: () => apply(patch) })
  } catch (error) {
    reportError(error, `${label} failed`)
  }
}

export async function downloadBackup(project: Project): Promise<void> {
  const blob = await attempt(() => projectsApi.backup(project.id), 'Backup failed')
  if (!blob) return
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `vibrato-backup-${project.name.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.zip`
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 2000)
}

export function startDemo(): void {
  void attempt(async () => {
    const { task } = await projectsApi.createDemo()
    trackTask(task, {
      onComplete: (done) => {
        refreshList()
        const result = done.result as { id?: string } | null
        const id = result?.id
        if (id) navigate({ name: 'project', projectId: id, tab: 'compare' })
      },
    })
  }, 'The demo project could not be created')
}
