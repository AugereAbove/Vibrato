import { setUi, useUi } from '../../state/ui'
import { Dialog } from '../ui/Dialog'

const GROUPS: { title: string; items: [string, string][] }[] = [
  {
    title: 'Playback',
    items: [
      ['Space', 'Play / pause'],
      ['A', 'Switch between reference and take at the same moment'],
      ['L', 'Loop the selection (or toggle the loop)'],
      ['← / →', 'Seek 1 second'],
      ['Shift + ← / →', 'Fine seek (0.1 s)'],
      ['Home / End', 'Go to the start / end'],
      [', / .', 'Previous / next note'],
      ['[ / ]', 'Previous / next phrase'],
    ],
  },
  {
    title: 'Timeline',
    items: [
      ['F', 'Fit the selection'],
      ['Shift + F', 'Fit the whole recording'],
      ['+ / −', 'Zoom in / out'],
      ['Ctrl/⌘ + scroll', 'Zoom around the pointer'],
      ['Shift + scroll', 'Scroll horizontally'],
      ['Alt + scroll', 'Zoom the pitch lane vertically'],
      ['Drag', 'Select a region (hold Alt to snap to syllables)'],
      ['Double-click', 'Select the phrase'],
      ['Alt + click', 'Pin measurements at that moment'],
      ['P', 'Select the phrase under the playhead'],
      ['Esc', 'Clear the selection'],
    ],
  },
  {
    title: 'Practice',
    items: [
      ['R', 'Record a take'],
      ['N', 'What should I fix next?'],
      ['W', 'Why does the selection sound different?'],
      ['B', 'Bookmark the playhead or selection'],
    ],
  },
  {
    title: 'App',
    items: [
      ['Ctrl/⌘ + K', 'Command palette'],
      ['Ctrl/⌘ + Z', 'Undo'],
      ['Ctrl/⌘ + Shift + Z', 'Redo'],
      ['?', 'This list'],
    ],
  },
]

export function ShortcutsDialog() {
  const open = useUi((s) => s.shortcutsOpen)
  return (
    <Dialog
      open={open}
      onClose={() => setUi({ shortcutsOpen: false })}
      title="Keyboard shortcuts"
      width={720}
    >
      <div className="shortcut-grid">
        {GROUPS.map((group) => (
          <section key={group.title}>
            <h4 className="eyebrow" style={{ marginBottom: 8 }}>
              {group.title}
            </h4>
            <dl className="shortcut-list">
              {group.items.map(([keys, label]) => (
                <div key={keys} className="shortcut-row">
                  <dt>
                    {keys.split(' / ').map((part, i) => (
                      <span key={part}>
                        {i > 0 ? <span className="faint"> / </span> : null}
                        <kbd className="kbd">{part}</kbd>
                      </span>
                    ))}
                  </dt>
                  <dd>{label}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
      <p className="faint tiny" style={{ marginTop: 12 }}>
        Single-key shortcuts are ignored while you type in a text field, and browser shortcuts are left alone.
      </p>
    </Dialog>
  )
}
