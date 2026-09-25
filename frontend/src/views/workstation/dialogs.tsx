import { useEffect, useMemo, useState } from 'react'
import { recordingsApi } from '../../api/endpoints'
import type { Recording, Segment, SongSection } from '../../api/types'
import { Button, IconButton } from '../../components/ui/Button'
import { Select, Switch, TextArea, TextField } from '../../components/ui/Controls'
import { Dialog } from '../../components/ui/Dialog'
import { formatTime } from '../../lib/format'
import { keys, refreshProject, refreshRecording, useReferenceProfiles } from '../../state/data'
import { attempt, reportError } from '../../state/errors'
import { invalidate, useResource } from '../../state/resource'
import { beginSave } from '../../state/tasks'
import { useWorkspace } from '../../state/workspace'
import { analyzeRecording, updateRecording } from './actions'

export function RecordingEditor({
  projectId,
  recording,
  onClose,
  words,
}: {
  projectId: string
  recording: Recording | null
  onClose: () => void
  words: Segment[]
}) {
  const [name, setName] = useState('')
  const [notes, setNotes] = useState('')
  const [lyrics, setLyrics] = useState('')
  const [singer, setSinger] = useState('')
  const [profileId, setProfileId] = useState('')
  const [excluded, setExcluded] = useState(false)
  const [busy, setBusy] = useState(false)
  const profiles = useReferenceProfiles()
  const overrides = useResource(
    recording && recording.kind === 'reference' ? `pronunciations:${recording.id}` : null,
    () => recordingsApi.pronunciations(recording!.id).then((r) => r.overrides),
  )
  const [edits, setEdits] = useState<Record<number, string>>({})
  useEffect(() => {
    if (!recording) return
    const frame = window.requestAnimationFrame(() => {
      setName(recording.name)
      setNotes(recording.notes)
      setLyrics(recording.lyrics ?? '')
      setSinger(recording.singer_label ?? '')
      setProfileId(recording.reference_profile_id ?? '')
      setExcluded(Boolean(recording.excluded_from_profile))
      setEdits({})
    })
    return () => window.cancelAnimationFrame(frame)
  }, [recording])
  const lyricWords = useMemo(
    () =>
      words
        .map((w) => ({
          index: typeof w.props.word_index === 'number' ? w.props.word_index : -1,
          word: w.label,
          phones: Array.isArray(w.props.phones) ? (w.props.phones as string[]).join(' ') : '',
        }))
        .filter((w) => w.index >= 0),
    [words],
  )
  if (!recording) return null
  const isReference = recording.kind === 'reference'
  const save = async () => {
    setBusy(true)
    const patch: Record<string, unknown> = {}
    if (name.trim() && name.trim() !== recording.name) patch.name = name.trim()
    if (notes !== recording.notes) patch.notes = notes
    if (isReference) {
      if (singer !== (recording.singer_label ?? '')) patch.singer_label = singer
      if ((profileId || null) !== recording.reference_profile_id)
        patch.reference_profile_id = profileId || null
      if (excluded !== Boolean(recording.excluded_from_profile)) patch.excluded_from_profile = excluded
    }
    if (Object.keys(patch).length) await updateRecording(projectId, recording, patch, 'Edit recording')
    let reanalyze = false
    if (isReference && lyrics !== (recording.lyrics ?? '')) {
      const done = await attempt(() => recordingsApi.setLyrics(recording.id, lyrics), 'Lyrics were not saved')
      if (done) reanalyze = true
    }
    for (const [index, value] of Object.entries(edits)) {
      const word = lyricWords.find((w) => w.index === Number(index))
      if (!word) continue
      const done = await attempt(
        () => recordingsApi.setPronunciation(recording.id, Number(index), word.word, value.trim() || null),
        'Pronunciation was not saved',
      )
      if (done) reanalyze = true
    }
    setBusy(false)
    refreshProject(projectId)
    if (reanalyze) {
      await analyzeRecording(projectId, recording, true)
      refreshRecording(recording.id)
    }
    onClose()
  }
  return (
    <Dialog
      open
      onClose={onClose}
      width={640}
      title={isReference ? 'Reference details' : 'Take details'}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => void save()} loading={busy}>
            Save
          </Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 12 }}>
        <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <TextArea label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
        {isReference ? (
          <>
            <div className="form-grid">
              <TextField
                label="Singer / reference label"
                value={singer}
                onChange={(e) => setSinger(e.target.value)}
              />
              <Select
                label="Reference profile"
                value={profileId}
                onChange={setProfileId}
                options={[
                  { value: '', label: 'None' },
                  ...(profiles.data ?? []).map((p) => ({ value: p.id, label: p.name })),
                ]}
              />
            </div>
            <Switch
              checked={excluded}
              onChange={setExcluded}
              label="Exclude from the singer profile"
              description="Use this for contaminated or unrepresentative recordings."
            />
            <TextArea
              label="Lyrics"
              hint="One line per phrase. Saving changed lyrics re-analyses the reference."
              value={lyrics}
              onChange={(e) => setLyrics(e.target.value)}
              rows={5}
            />
            {lyricWords.length ? (
              <details className="raw-result">
                <summary>Pronunciations ({lyricWords.length} words)</summary>
                <p className="tiny faint">
                  Pronunciations use ARPAbet symbols (e.g. “L AY T”). Override a word if its automatic
                  pronunciation is wrong; leave empty to use the automatic one.
                </p>
                <div className="pron-grid">
                  {lyricWords.map((w) => (
                    <label key={w.index} className="pron-row">
                      <span className="pron-word">{w.word}</span>
                      <input
                        className="input"
                        value={edits[w.index] ?? overrides.data?.[String(w.index)] ?? ''}
                        placeholder={w.phones}
                        onChange={(e) => setEdits((current) => ({ ...current, [w.index]: e.target.value }))}
                        aria-label={`Pronunciation of ${w.word}`}
                      />
                    </label>
                  ))}
                </div>
              </details>
            ) : null}
          </>
        ) : null}
        <p className="tiny faint">
          {recording.original_filename} · {recording.source_format ?? ''}{' '}
          {recording.source_sample_rate ? `${(recording.source_sample_rate / 1000).toFixed(1)} kHz` : ''}{' '}
          {recording.source_bit_depth ? `${recording.source_bit_depth}-bit` : ''}{' '}
          {recording.source_channels ? `${recording.source_channels} ch` : ''}
        </p>
      </div>
    </Dialog>
  )
}

export function SectionsDialog({
  open,
  onClose,
  reference,
  sections,
  automatic,
}: {
  open: boolean
  onClose: () => void
  reference: Recording | null
  sections: SongSection[]
  automatic: Segment[]
}) {
  const [rows, setRows] = useState<{ label: string; start_s: number; end_s: number }[]>([])
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!open) return
    const frame = window.requestAnimationFrame(() =>
      setRows(
        (sections.length ? sections : automatic).map((s) => ({
          label: s.label,
          start_s: s.start_s,
          end_s: s.end_s,
        })),
      ),
    )
    return () => window.cancelAnimationFrame(frame)
  }, [open, sections, automatic])
  if (!reference) return null
  const region = useWorkspace.getState().region
  const save = async () => {
    setBusy(true)
    const end = beginSave()
    try {
      await recordingsApi.setSections(
        reference.id,
        rows.filter((r) => r.label.trim() && r.end_s > r.start_s),
      )
      invalidate(keys.sections(reference.id))
      onClose()
    } catch (error) {
      reportError(error, 'Sections were not saved')
    } finally {
      end()
      setBusy(false)
    }
  }
  return (
    <Dialog
      open={open}
      onClose={onClose}
      width={560}
      title="Song sections"
      description="Label verses, choruses and other parts. Sections appear on the ruler and can be looped."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => void save()} loading={busy}>
            Save sections
          </Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 8 }}>
        {rows.map((row, index) => (
          <div key={index} className="section-row">
            <input
              className="input"
              value={row.label}
              aria-label="Section name"
              onChange={(e) =>
                setRows((r) => r.map((x, i) => (i === index ? { ...x, label: e.target.value } : x)))
              }
            />
            <input
              className="input num"
              type="number"
              step={0.01}
              value={row.start_s}
              aria-label="Start (s)"
              onChange={(e) =>
                setRows((r) => r.map((x, i) => (i === index ? { ...x, start_s: Number(e.target.value) } : x)))
              }
            />
            <input
              className="input num"
              type="number"
              step={0.01}
              value={row.end_s}
              aria-label="End (s)"
              onChange={(e) =>
                setRows((r) => r.map((x, i) => (i === index ? { ...x, end_s: Number(e.target.value) } : x)))
              }
            />
            <IconButton
              icon="trash"
              label="Remove section"
              onClick={() => setRows((r) => r.filter((_, i) => i !== index))}
            />
          </div>
        ))}
        <div className="row">
          <Button
            size="sm"
            icon="plus"
            onClick={() =>
              setRows((r) => [
                ...r,
                region
                  ? {
                      label: `Section ${r.length + 1}`,
                      start_s: Number(region.start.toFixed(2)),
                      end_s: Number(region.end.toFixed(2)),
                    }
                  : {
                      label: `Section ${r.length + 1}`,
                      start_s: 0,
                      end_s: Number(reference.duration_s.toFixed(2)),
                    },
              ])
            }
          >
            {region
              ? `Add from selection (${formatTime(region.start, 1)}–${formatTime(region.end, 1)})`
              : 'Add section'}
          </Button>
          {automatic.length ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                setRows(automatic.map((s) => ({ label: s.label, start_s: s.start_s, end_s: s.end_s })))
              }
            >
              Use detected sections
            </Button>
          ) : null}
        </div>
      </div>
    </Dialog>
  )
}
