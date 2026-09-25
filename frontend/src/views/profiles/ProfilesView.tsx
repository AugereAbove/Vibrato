import { useState } from 'react'
import { profilesApi, projectsApi, recordingsApi } from '../../api/endpoints'
import type { Recording } from '../../api/types'
import { Badge, ConfidenceBadge } from '../../components/ui/Badge'
import { Button, IconButton } from '../../components/ui/Button'
import { Switch, TextArea, TextField } from '../../components/ui/Controls'
import { Dialog } from '../../components/ui/Dialog'
import { confirmAction } from '../../components/ui/confirm'
import { EmptyState, ErrorState, SkeletonLines } from '../../components/ui/Feedback'
import { formatDuration, formatNumber, formatPercent } from '../../lib/format'
import { keys, useReferenceProfile, useReferenceProfiles } from '../../state/data'
import { attempt } from '../../state/errors'
import { invalidate, useResource } from '../../state/resource'
import { navigate } from '../../state/router'

function AddRecordingsDialog({
  profileId,
  open,
  onClose,
}: {
  profileId: string
  open: boolean
  onClose: () => void
}) {
  const references = useResource(open ? 'all-references' : null, async () => {
    const { projects } = await projectsApi.list({ archived: true })
    const lists = await Promise.all(
      projects.map((p) =>
        recordingsApi
          .list(p.id, 'reference')
          .then((r) => r.recordings.map((rec) => ({ ...rec, projectName: p.name }))),
      ),
    )
    return lists.flat()
  })
  const [busy, setBusy] = useState<string | null>(null)
  const assign = async (recording: Recording, value: string | null) => {
    setBusy(recording.id)
    await attempt(
      () => recordingsApi.update(recording.id, { reference_profile_id: value }),
      'Could not update the recording',
    )
    setBusy(null)
    invalidate(keys.profile(profileId))
    invalidate(keys.profiles)
    invalidate('all-references')
  }
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add reference recordings"
      width={620}
      description="Add every recording of the same singer so recurring traits can be separated from song-specific ones."
    >
      {references.loading ? <SkeletonLines lines={4} /> : null}
      {references.data && references.data.length === 0 ? (
        <EmptyState compact title="No reference recordings in any project yet" />
      ) : null}
      <ul className="plain-list">
        {(references.data ?? []).map((rec) => (
          <li key={rec.id} className="row">
            <span className="grow stack" style={{ gap: 0 }}>
              <strong className="truncate">{rec.name}</strong>
              <span className="tiny faint">
                {(rec as Recording & { projectName: string }).projectName} · {formatDuration(rec.duration_s)}
              </span>
            </span>
            {rec.reference_profile_id === profileId ? (
              <Button
                size="sm"
                variant="ghost"
                loading={busy === rec.id}
                onClick={() => void assign(rec, null)}
              >
                Remove
              </Button>
            ) : (
              <Button
                size="sm"
                variant="secondary"
                icon="plus"
                loading={busy === rec.id}
                onClick={() => void assign(rec, profileId)}
              >
                {rec.reference_profile_id ? 'Move here' : 'Add'}
              </Button>
            )}
          </li>
        ))}
      </ul>
    </Dialog>
  )
}

function ProfileDetail({ profileId }: { profileId: string }) {
  const detail = useReferenceProfile(profileId)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState('')
  const [notes, setNotes] = useState('')
  if (detail.loading) return <SkeletonLines lines={6} />
  if (detail.error || !detail.data)
    return <ErrorState error={detail.error} onRetry={() => void detail.refresh()} />
  const d = detail.data
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="card card-pad row-wrap">
        <div className="grow">
          <h2>{d.profile.name}</h2>
          {d.profile.notes ? <p className="small muted">{d.profile.notes}</p> : null}
          <div className="row" style={{ marginTop: 6 }}>
            <ConfidenceBadge value={d.confidence} />
            <span className="small faint">
              based on {d.recordings.filter((r) => !r.excluded).length} recording
              {d.recordings.filter((r) => !r.excluded).length === 1 ? '' : 's'}
            </span>
          </div>
        </div>
        <Button icon="plus" onClick={() => setAdding(true)}>
          Add recordings
        </Button>
        <IconButton
          icon="edit"
          label="Rename"
          onClick={() => {
            setName(d.profile.name)
            setNotes(d.profile.notes)
            setEditing(true)
          }}
        />
        <IconButton
          icon="trash"
          label="Delete profile"
          onClick={async () => {
            const ok = await confirmAction({
              title: `Delete “${d.profile.name}”?`,
              body: 'Recordings stay in their projects; only the grouping is removed.',
              danger: true,
              confirmLabel: 'Delete',
            })
            if (!ok) return
            await attempt(() => profilesApi.remove(profileId), 'Delete failed')
            invalidate(keys.profiles)
            navigate({ name: 'profiles' })
          }}
        />
      </div>
      <div className="card card-pad">
        <h3>Recurring traits</h3>
        <p className="small muted">{d.note}</p>
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Trait</th>
              <th scope="col">Typical value</th>
              <th scope="col">Range across recordings</th>
              <th scope="col">Consistency</th>
              <th scope="col">Recordings</th>
            </tr>
          </thead>
          <tbody>
            {d.traits.map((trait) => (
              <tr key={trait.key}>
                <th scope="row">{trait.label}</th>
                <td className="num">
                  {trait.median == null
                    ? '–'
                    : trait.unit === 'ratio'
                      ? formatPercent(trait.median)
                      : `${formatNumber(trait.median, 2)} ${trait.unit}`}
                </td>
                <td className="num faint">
                  {trait.range
                    ? `${formatNumber(trait.range[0], 2)} – ${formatNumber(trait.range[1], 2)}`
                    : '–'}
                </td>
                <td>
                  <Badge
                    tone={
                      trait.consistency === 'consistent'
                        ? 'good'
                        : trait.consistency === 'unknown'
                          ? 'neutral'
                          : 'warn'
                    }
                  >
                    {trait.consistency}
                  </Badge>
                </td>
                <td className="num">{trait.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card card-pad">
        <h3>Recordings</h3>
        {d.recordings.length === 0 ? (
          <p className="small muted">No recordings yet. Add references of this singer from any project.</p>
        ) : (
          <ul className="plain-list">
            {d.recordings.map((rec) => (
              <li key={rec.id} className="row">
                <span className="grow stack" style={{ gap: 0 }}>
                  <strong className={rec.excluded ? 'faint' : undefined}>{rec.name}</strong>
                  <span className="tiny faint">
                    {formatDuration(rec.duration_s)} · quality {formatPercent(rec.quality)}
                  </span>
                </span>
                <Switch
                  checked={!rec.excluded}
                  onChange={async (include) => {
                    await attempt(
                      () => recordingsApi.update(rec.id, { excluded_from_profile: !include }),
                      'Could not update',
                    )
                    invalidate(keys.profile(profileId))
                  }}
                  label={rec.excluded ? 'Excluded' : 'Included'}
                />
                {rec.project_id ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      navigate({
                        name: 'project',
                        projectId: rec.project_id as string,
                        tab: 'compare',
                        ref: rec.id,
                      })
                    }
                  >
                    Open
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        <p className="tiny faint">
          Exclude recordings with backing music, heavy effects or unusual style so they do not distort the
          profile.
        </p>
      </div>
      <AddRecordingsDialog profileId={profileId} open={adding} onClose={() => setAdding(false)} />
      <Dialog
        open={editing}
        onClose={() => setEditing(false)}
        title="Edit profile"
        footer={
          <>
            <Button variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={async () => {
                await attempt(() => profilesApi.update(profileId, { name, notes }), 'Profile was not saved')
                invalidate(keys.profiles)
                invalidate(keys.profile(profileId))
                setEditing(false)
              }}
            >
              Save
            </Button>
          </>
        }
      >
        <div className="stack" style={{ gap: 10 }}>
          <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <TextArea label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} />
        </div>
      </Dialog>
    </div>
  )
}

export function ProfilesView({ profileId }: { profileId?: string }) {
  const profiles = useReferenceProfiles()
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const list = profiles.data ?? []
  const selected = profileId ?? list[0]?.id ?? null
  return (
    <div className="page profiles">
      <div className="page-inner wide">
        <div className="page-header">
          <div>
            <h1>Reference library</h1>
            <p className="muted">
              Group several recordings of the same singer to learn which traits are characteristic of them
              (consistent across songs) and which are specific to one song.
            </p>
          </div>
          <Button variant="primary" icon="plus" onClick={() => setCreating(true)}>
            New singer profile
          </Button>
        </div>
        <div className="calibration-layout">
          <aside className="card calibration-list">
            <div className="panel-header">
              <span className="panel-title">Profiles</span>
            </div>
            {profiles.loading ? <SkeletonLines lines={3} /> : null}
            {list.length === 0 && !profiles.loading ? <p className="side-hint">No profiles yet.</p> : null}
            {list.map((profile) => (
              <button
                key={profile.id}
                type="button"
                className={`side-item${profile.id === selected ? ' is-active' : ''}`}
                onClick={() => navigate({ name: 'profiles', profileId: profile.id }, true)}
              >
                <span className="grow truncate">{profile.name}</span>
                <span className="tiny faint">{profile.recordings ?? 0}</span>
              </button>
            ))}
          </aside>
          <section style={{ minWidth: 0 }}>
            {selected ? (
              <ProfileDetail key={selected} profileId={selected} />
            ) : (
              <EmptyState
                icon="users"
                title="Create a singer profile"
                actions={
                  <Button icon="plus" onClick={() => setCreating(true)}>
                    New profile
                  </Button>
                }
              >
                Then add reference recordings of that singer from your projects.
              </EmptyState>
            )}
          </section>
        </div>
      </div>
      <Dialog
        open={creating}
        onClose={() => setCreating(false)}
        title="New singer profile"
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreating(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={!name.trim()}
              onClick={async () => {
                const created = await attempt(
                  () => profilesApi.create(name.trim()),
                  'Profile was not created',
                )
                if (!created) return
                invalidate(keys.profiles)
                setCreating(false)
                setName('')
                navigate({ name: 'profiles', profileId: created.profile.id })
              }}
            >
              Create
            </Button>
          </>
        }
      >
        <TextField
          label="Singer or style name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. My vocal teacher"
          data-autofocus
        />
      </Dialog>
    </div>
  )
}
