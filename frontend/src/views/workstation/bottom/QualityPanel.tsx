import type { QualityReport, Recording } from '../../../api/types'
import { Badge } from '../../../components/ui/Badge'
import { EmptyState } from '../../../components/ui/Feedback'
import { Icon } from '../../../components/ui/Icon'
import { CATEGORY_ORDER, categoryLabel } from '../../../lib/categories'
import { formatDb, formatDuration, formatHz, formatPercent, formatSeconds } from '../../../lib/format'

function Report({
  recording,
  tone,
  contamination,
}: {
  recording: Recording
  tone: 'ref' | 'take'
  contamination: { score: number; evidence: string[] } | null
}) {
  const qc: QualityReport | null = recording.qc
  if (!qc) return <EmptyState compact title="No quality report" />
  const rows: [string, string][] = [
    ['Duration', formatDuration(qc.duration_s)],
    ['Source', `${recording.source_format ?? '?'} ${recording.source_subtype ?? ''}`.trim()],
    ['Sample rate', qc.source_sample_rate ? `${(qc.source_sample_rate / 1000).toFixed(1)} kHz` : '–'],
    ['Bit depth', recording.source_bit_depth ? `${recording.source_bit_depth}-bit` : 'unknown'],
    ['Channels', `${qc.source_channels} (${qc.mixdown})`],
    ['Lossy codec', qc.lossy ? 'yes' : 'no'],
    ['Peak / true peak', `${formatDb(qc.peak_dbfs)} / ${formatDb(qc.true_peak_dbfs)}FS`],
    ['RMS', `${formatDb(qc.rms_dbfs)}FS`],
    ['Integrated loudness', qc.lufs_integrated != null ? `${qc.lufs_integrated.toFixed(1)} LUFS` : '–'],
    ['DC offset', qc.dc_offset.toFixed(4)],
    ['Clipped samples', `${qc.clipped_samples} (${formatPercent(qc.clipped_fraction, 2)})`],
    ['Noise floor', `${formatDb(qc.noise_floor_dbfs)}FS`],
    [
      'Signal-to-noise',
      qc.snr_db != null ? `${qc.snr_db.toFixed(1)} dB${qc.snr_reliable ? '' : ' (estimate)'}` : '–',
    ],
    [
      'Silence at edges',
      `${formatSeconds(qc.leading_silence_s, 1)} / ${formatSeconds(qc.trailing_silence_s, 1)}`,
    ],
    [
      'Bandwidth',
      qc.bandwidth_hz ? `${formatHz(qc.bandwidth_hz)}${qc.bandwidth_limited ? ' (limited)' : ''}` : '–',
    ],
    [
      'Reverb estimate',
      qc.reverb_rt_estimate_s != null
        ? `${qc.reverb_rt_estimate_s.toFixed(2)} s (conf. ${formatPercent(qc.reverb_confidence)})`
        : '–',
    ],
  ]
  return (
    <div className="qc-report card card-pad">
      <div className="row">
        <Badge tone={tone}>{tone === 'ref' ? 'Reference' : 'Take'}</Badge>
        <strong className="truncate">{recording.name}</strong>
        <span className="spacer" />
        <span className="small">quality {formatPercent(qc.overall_quality)}</span>
      </div>
      {qc.issues.length ? (
        <ul className="qc-issues">
          {qc.issues.map((issue) => (
            <li key={issue.code} className={`qc-issue sev-${issue.severity}`}>
              <Icon name={issue.severity === 'info' ? 'info' : 'alert'} size={14} />
              <div>
                <strong>{issue.title}</strong>
                <p className="small">{issue.what}</p>
                <p className="small muted">{issue.why}</p>
                <p className="small faint">{issue.action}</p>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="small good-text">No quality problems detected.</p>
      )}
      <dl className="kv">
        {rows.map(([label, value]) => (
          <div key={label} style={{ display: 'contents' }}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <div className="qc-factors">
        <span className="eyebrow">Confidence factor by category</span>
        {CATEGORY_ORDER.map((c) => {
          const value = qc.factors[c]
          if (value == null) return null
          return (
            <div key={c} className="qc-factor" title={(qc.factor_reasons[c] ?? []).join('; ')}>
              <span>{categoryLabel(c)}</span>
              <span className="qc-factor-track">
                <span style={{ width: `${value * 100}%` }} className={value < 0.6 ? 'is-low' : undefined} />
              </span>
              <span className="num">{formatPercent(value)}</span>
            </div>
          )
        })}
      </div>
      {contamination && contamination.score > 0.2 ? (
        <p className="small warn-text">
          Possible contamination ({formatPercent(contamination.score)}): {contamination.evidence.join('; ')}
        </p>
      ) : null}
    </div>
  )
}

export function QualityPanel({
  reference,
  take,
  refContamination,
  takeContamination,
}: {
  reference: Recording | null
  take: Recording | null
  refContamination: { score: number; evidence: string[] } | null
  takeContamination: { score: number; evidence: string[] } | null
}) {
  if (!reference && !take) return <EmptyState compact title="No recordings yet" />
  return (
    <div className="quality-panel">
      {reference ? <Report recording={reference} tone="ref" contamination={refContamination} /> : null}
      {take ? <Report recording={take} tone="take" contamination={takeContamination} /> : null}
    </div>
  )
}
