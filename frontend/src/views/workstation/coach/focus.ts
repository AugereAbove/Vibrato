import type { Finding } from '../../../api/types'
import { fitRange } from '../../../components/timeline/viewport'
import type { ViewMode } from '../../../state/prefs'
import { setLayers } from '../../../state/ui'
import { select, useWorkspace } from '../../../state/workspace'
import { layersFor } from '../actions'

function levelFor(id: string | null): 'note' | 'syllable' | 'word' | 'phrase' {
  if (!id) return 'phrase'
  if (id.startsWith('nt')) return 'note'
  if (id.startsWith('sy')) return 'syllable'
  if (id.startsWith('wd')) return 'word'
  return 'phrase'
}

export function showFinding(finding: Finding, mode: ViewMode): void {
  const practice = finding.practice
  if (!practice) return
  select({
    kind: 'segment',
    level: levelFor(practice.segment_id),
    refId: practice.segment_id,
    takeId: practice.user_segment_id,
    start: practice.focus_start,
    end: practice.focus_end,
    label: practice.label,
  })
  useWorkspace.setState({
    region: { start: practice.focus_start, end: practice.focus_end },
    focusKey: finding.key,
  })
  const layers = layersFor(finding.texts.layers)
  if (layers.length) setLayers(mode, Object.fromEntries(layers.map((l) => [l, true])))
  fitRange(practice.ref_start, practice.ref_end, 0.2)
}
