import { useEffect, useRef, useState } from 'react'
import { recordingsApi } from '../../api/endpoints'
import type { Recording } from '../../api/types'
import { Button } from '../../components/ui/Button'
import { Segmented, Switch, TextArea, TextField } from '../../components/ui/Controls'
import { Dialog } from '../../components/ui/Dialog'
import { Icon } from '../../components/ui/Icon'
import { formatBytes } from '../../lib/format'
import { AUDIO_ACCEPT, importFile } from './actions'
import { useImportStore } from './importStore'

function stripExtension(name: string): string {
  return name.replace(/\.[a-z0-9]+$/i, '')
}

interface ImportDialogProps {
  projectId: string
  reference: Recording | null
  onImported?: (recording: Recording) => void
}

export function ImportDialog(props: ImportDialogProps) {
  const session = useImportStore((state) => state.session)
  return <ImportDialogBody key={session} {...props} />
}

function ImportDialogBody({ projectId, reference, onImported }: ImportDialogProps) {
  const { open, kind, files } = useImportStore()
  const [nameDraft, setNameDraft] = useState<string | null>(null)
  const [lyrics, setLyrics] = useState('')
  const [primary, setPrimary] = useState(!reference)
  const [busy, setBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const name = nameDraft ?? (files.length === 1 ? stripExtension(files[0].name) : '')

  const close = () => useImportStore.setState({ open: false, files: [] })
  const submit = async () => {
    if (files.length === 0) return
    setBusy(true)
    const imported: Recording[] = []
    for (const file of files) {
      const recording = await importFile(projectId, file, file.name, {
        kind,
        name: files.length === 1 && name.trim() ? name.trim() : stripExtension(file.name),
        referenceId: kind === 'take' ? (reference?.id ?? null) : null,
        lyrics: kind === 'reference' ? lyrics : '',
        source: 'import',
      })
      if (recording) {
        imported.push(recording)
        if (kind === 'reference' && (primary || !reference) && files.length === 1) {
          await recordingsApi.update(recording.id, { is_primary: true }).catch(() => undefined)
        }
      }
    }
    setBusy(false)
    close()
    if (imported.length) onImported?.(imported[imported.length - 1])
  }
  return (
    <Dialog
      open={open}
      onClose={close}
      width={560}
      title={kind === 'reference' ? 'Import reference vocal' : 'Import your take'}
      description={
        kind === 'reference'
          ? 'Use an isolated vocal if you can: backing tracks, reverb and doubled vocals reduce measurement confidence.'
          : reference
            ? `The take will be aligned and compared with “${reference.name}”.`
            : 'There is no reference yet, so the take will only be analysed.'
      }
      footer={
        <>
          <Button variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button
            variant="primary"
            icon="upload"
            onClick={() => void submit()}
            disabled={files.length === 0}
            loading={busy}
          >
            Import {files.length > 1 ? `${files.length} files` : ''}
          </Button>
        </>
      }
    >
      <div className="stack" style={{ gap: 14 }}>
        <Segmented
          ariaLabel="Import as"
          value={kind}
          onChange={(value) => useImportStore.setState({ kind: value })}
          options={[
            { value: 'reference', label: 'Reference', icon: 'music' },
            { value: 'take', label: 'My take', icon: 'mic' },
          ]}
        />
        <div
          className="file-drop"
          role="button"
          tabIndex={0}
          onClick={() => input.current?.click()}
          onKeyDown={(event) => (event.key === 'Enter' || event.key === ' ') && input.current?.click()}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault()
            const dropped = [...event.dataTransfer.files]
            if (dropped.length) useImportStore.setState({ files: dropped })
          }}
        >
          <Icon name="upload" size={20} />
          {files.length ? (
            <div className="stack" style={{ gap: 2 }}>
              {files.map((file) => (
                <span key={file.name} className="small">
                  <strong>{file.name}</strong> <span className="faint">{formatBytes(file.size)}</span>
                </span>
              ))}
            </div>
          ) : (
            <span className="small muted">
              Drop audio here or click to choose (WAV, FLAC, MP3, M4A/AAC, OGG, AIFF)
            </span>
          )}
          <input
            ref={input}
            type="file"
            accept={AUDIO_ACCEPT}
            multiple
            hidden
            onChange={(event) => {
              const chosen = [...(event.target.files ?? [])]
              if (chosen.length) useImportStore.setState({ files: chosen })
              event.target.value = ''
            }}
          />
        </div>
        {files.length <= 1 ? (
          <TextField
            label="Name"
            value={name}
            onChange={(event) => setNameDraft(event.target.value)}
            placeholder="Recording name"
          />
        ) : null}
        {kind === 'reference' ? (
          <>
            <TextArea
              label="Lyrics (optional)"
              hint="One line per phrase. Lyrics improve word, syllable and phoneme alignment; you can add or edit them later."
              value={lyrics}
              onChange={(event) => setLyrics(event.target.value)}
              rows={4}
            />
            {reference ? (
              <Switch
                checked={primary}
                onChange={setPrimary}
                label="Make this the main reference"
                description="Takes are compared with the main reference by default."
              />
            ) : null}
          </>
        ) : null}
      </div>
    </Dialog>
  )
}

export function DropOverlay({ onDrop }: { onDrop: (files: File[], kind: 'reference' | 'take') => void }) {
  const [active, setActive] = useState(false)
  const [hoverKind, setHoverKind] = useState<'reference' | 'take' | null>(null)
  const depth = useRef(0)
  useEffect(() => {
    const hasFiles = (event: DragEvent) => [...(event.dataTransfer?.types ?? [])].includes('Files')
    const enter = (event: DragEvent) => {
      if (!hasFiles(event)) return
      depth.current += 1
      setActive(true)
    }
    const leave = (event: DragEvent) => {
      if (!hasFiles(event)) return
      depth.current = Math.max(0, depth.current - 1)
      if (depth.current === 0) setActive(false)
    }
    const over = (event: DragEvent) => {
      if (hasFiles(event)) event.preventDefault()
    }
    const drop = (event: DragEvent) => {
      if (!hasFiles(event)) return
      event.preventDefault()
      depth.current = 0
      setActive(false)
    }
    window.addEventListener('dragenter', enter)
    window.addEventListener('dragleave', leave)
    window.addEventListener('dragover', over)
    window.addEventListener('drop', drop)
    return () => {
      window.removeEventListener('dragenter', enter)
      window.removeEventListener('dragleave', leave)
      window.removeEventListener('dragover', over)
      window.removeEventListener('drop', drop)
    }
  }, [])
  if (!active) return null
  const zone = (kind: 'reference' | 'take', title: string, text: string, icon: string) => (
    <div
      className={`drop-zone${hoverKind === kind ? ' is-hover' : ''}`}
      onDragEnter={() => setHoverKind(kind)}
      onDragLeave={() => setHoverKind(null)}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault()
        const files = [...event.dataTransfer.files]
        setHoverKind(null)
        setActive(false)
        depth.current = 0
        if (files.length) onDrop(files, kind)
      }}
    >
      <Icon name={icon} size={28} />
      <strong>{title}</strong>
      <span className="small muted">{text}</span>
    </div>
  )
  return (
    <div className="drop-overlay" aria-hidden>
      {zone('reference', 'Drop as reference', 'The vocal you want to learn from', 'music')}
      {zone('take', 'Drop as my take', 'Compared with the current reference', 'mic')}
    </div>
  )
}
