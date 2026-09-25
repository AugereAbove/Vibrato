import type { ViewMode } from '../../state/prefs'
import { setUi, useUi, type BottomTab } from '../../state/ui'
import { IconButton } from '../../components/ui/Button'
import { EmptyState } from '../../components/ui/Feedback'
import { Tabs } from '../../components/ui/Tabs'
import type { WorkstationData } from './useWorkstation'
import { HeatmapPanel } from './bottom/HeatmapPanel'
import { MeasurementsTable } from './bottom/MeasurementsTable'
import { PreviewsPanel } from './bottom/PreviewsPanel'
import { QualityPanel } from './bottom/QualityPanel'
import { ScoresPanel } from './bottom/ScoresPanel'
import { TakesPanel } from './bottom/TakesPanel'
import { VowelSpace } from './bottom/VowelSpace'

export function BottomPanel({ data, mode }: { data: WorkstationData; mode: ViewMode }) {
  const tab = useUi((s) => s.bottomTab)
  const open = useUi((s) => s.bottomOpen)
  const comparison = data.comparison
  const needsComparison = (content: React.ReactNode) =>
    comparison ? (
      content
    ) : (
      <EmptyState compact icon="compare" title="Available once a take is compared">
        Import or record a take against the reference to see differences here.
      </EmptyState>
    )
  let body: React.ReactNode = null
  if (open) {
    switch (tab) {
      case 'heatmap':
        body = needsComparison(
          comparison ? (
            <HeatmapPanel comparison={comparison} refIndex={data.refIndex} cindex={data.cindex} />
          ) : null,
        )
        break
      case 'measurements':
        body = needsComparison(
          comparison ? <MeasurementsTable comparison={comparison} cindex={data.cindex} mode={mode} /> : null,
        )
        break
      case 'scores':
        body = needsComparison(
          comparison ? <ScoresPanel key={comparison.id} comparison={comparison} /> : null,
        )
        break
      case 'vowels':
        body = (
          <VowelSpace refIndex={data.refIndex} takeIndex={data.takeIndex} cindex={data.cindex} mode={mode} />
        )
        break
      case 'previews':
        body = <PreviewsPanel take={data.take} hasComparison={Boolean(comparison)} mode={mode} />
        break
      case 'takes':
        body = (
          <TakesPanel
            projectId={data.projectId}
            referenceId={data.reference?.id ?? null}
            takes={data.takes}
            currentTake={data.take}
          />
        )
        break
      case 'quality':
        body = (
          <QualityPanel
            reference={data.reference}
            take={data.take}
            refContamination={data.refAnalysis?.contamination ?? null}
            takeContamination={data.takeAnalysis?.contamination ?? null}
            refRuns={data.refAnalysis?.runs ?? []}
            takeRuns={data.takeAnalysis?.runs ?? []}
          />
        )
        break
    }
  }
  const metricCount = comparison?.metrics.length
  return (
    <section className={`bottom-panel${open ? '' : ' is-collapsed'}`} aria-label="Details">
      <div className="bottom-panel-header">
        <Tabs<BottomTab>
          ariaLabel="Detail views"
          size="sm"
          value={tab}
          onChange={(value) => setUi({ bottomTab: value, bottomOpen: true })}
          items={[
            { id: 'heatmap', label: 'Heatmap', icon: 'grid' },
            { id: 'measurements', label: 'Measurements', icon: 'list', count: metricCount },
            { id: 'scores', label: 'Scores', icon: 'bars' },
            { id: 'vowels', label: 'Vowel space', icon: 'vowel' },
            { id: 'previews', label: 'Previews', icon: 'wand' },
            { id: 'takes', label: 'Takes', icon: 'history', count: data.takes.length || undefined },
            { id: 'quality', label: 'Recording quality', icon: 'shield' },
          ]}
        />
        <span className="spacer" />
        <IconButton
          icon={open ? 'chevron-down' : 'chevron-up'}
          label={open ? 'Collapse details' : 'Expand details'}
          size="xs"
          onClick={() => setUi({ bottomOpen: !open })}
        />
      </div>
      {open ? (
        <div className="bottom-panel-body" key={tab}>
          {body}
        </div>
      ) : null}
    </section>
  )
}
