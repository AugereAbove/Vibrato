import type { Finding, Recording } from '../../../api/types'
import { comparisonsApi } from '../../../api/endpoints'
import { engine } from '../../../audio/engine'
import { CategoryChip } from '../../../components/ui/Badge'
import { Button } from '../../../components/ui/Button'
import { Dialog } from '../../../components/ui/Dialog'
import { EmptyState, ErrorState, SkeletonLines } from '../../../components/ui/Feedback'
import { formatTime } from '../../../lib/format'
import type { ViewMode } from '../../../state/prefs'
import { useResource } from '../../../state/resource'
import { loopRegion } from '../actions'
import { FindingCard } from './FindingCard'
import { closeWhy, useWhyStore } from './whyStore'

export function WhyDialog({
  comparisonId,
  mode,
  projectId,
  take,
  referenceId,
}: {
  comparisonId: string | null
  mode: ViewMode
  projectId: string
  take: Recording | null
  referenceId: string | null
}) {
  const region = useWhyStore((s) => s.region)
  const key =
    region && comparisonId ? `why:${comparisonId}:${region.start.toFixed(3)}:${region.end.toFixed(3)}` : null
  const result = useResource(key, () =>
    comparisonsApi.why(comparisonId as string, region!.start, region!.end),
  )
  const data = result.data
  const tiers: [string, string, Finding[]][] = data
    ? [
        ['Primary', 'Most likely the main reason it sounds different here', data.primary],
        ['Secondary', 'Also contributing', data.secondary],
        ['Minor', 'Small or less noticeable', data.minor],
      ]
    : []
  return (
    <Dialog
      open={region !== null}
      onClose={closeWhy}
      width={760}
      title="Why does this sound different?"
      description={
        region
          ? `Reference ${formatTime(region.start)} – ${formatTime(region.end)} compared with the matching part of your take.`
          : undefined
      }
      footer={
        region ? (
          <>
            <Button
              variant="ghost"
              icon="play"
              onClick={() => {
                void engine.playRange('ref', region.start, region.end)
              }}
            >
              Reference
            </Button>
            <Button
              variant="ghost"
              icon="play"
              onClick={() => {
                void engine.playRange('take', region.start, region.end)
              }}
            >
              Your take
            </Button>
            <Button
              variant="primary"
              icon="loop"
              onClick={() => {
                loopRegion(region)
                engine.setAlternate(true)
                void engine.play(region.start)
                closeWhy()
              }}
            >
              Loop A/B here
            </Button>
          </>
        ) : null
      }
    >
      {result.loading ? <SkeletonLines lines={5} /> : null}
      {result.error ? <ErrorState error={result.error} onRetry={() => void result.refresh()} /> : null}
      {data ? (
        <div className="stack why-body" style={{ gap: 14 }}>
          {data.primary.length + data.secondary.length + data.minor.length === 0 ? (
            <EmptyState compact icon="check" title="Nothing reliable stands out in this region">
              The measurements here are within tolerance, or not confident enough to interpret.
            </EmptyState>
          ) : null}
          {tiers.map(([label, help, findings]) =>
            findings.length ? (
              <section key={label} className="why-tier">
                <div className="row">
                  <span className="eyebrow">{label}</span>
                  <span className="faint tiny">{help}</span>
                </div>
                <div className="stack" style={{ gap: 8 }}>
                  {findings.map((finding) => (
                    <FindingCard
                      key={finding.key}
                      finding={finding}
                      mode={mode}
                      projectId={projectId}
                      take={take}
                      referenceId={referenceId}
                      compact={label !== 'Primary'}
                    />
                  ))}
                </div>
              </section>
            ) : null,
          )}
          {data.already_close.length ? (
            <section>
              <span className="eyebrow">Already close</span>
              <ul className="plain-list">
                {data.already_close.map((item) => (
                  <li key={item.category}>
                    <CategoryChip category={item.category} /> <span className="muted">{item.text}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {data.insufficient_confidence.length ? (
            <section>
              <span className="eyebrow">Insufficient confidence</span>
              <ul className="plain-list">
                {data.insufficient_confidence.map((item) => (
                  <li key={item.name} className="muted">
                    {item.text}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          <p className="faint tiny">
            Based on {data.measurements_considered} measurements in this region (pitch, timing, vibrato,
            vowels, dynamics, voice quality, consonants, breath and timbre), weighted by confidence and
            perceptual importance.
          </p>
        </div>
      ) : null}
    </Dialog>
  )
}
