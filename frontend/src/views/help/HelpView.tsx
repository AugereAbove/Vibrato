import { useMemo, useState } from 'react'
import { Badge, BasisTag } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { TextField } from '../../components/ui/Controls'
import { ErrorState, SkeletonLines } from '../../components/ui/Feedback'
import { Icon } from '../../components/ui/Icon'
import { Tabs } from '../../components/ui/Tabs'
import { categoryLabel } from '../../lib/categories'
import { humanize } from '../../lib/format'
import { useMethods } from '../../state/data'
import { navigate } from '../../state/router'
import { setUi } from '../../state/ui'

type Topic = 'start' | 'methods' | 'metrics' | 'glossary' | 'science'

const WORKFLOW: [string, string, string][] = [
  ['folder', 'Create a project', 'One project per song. Give it the song name and, optionally, the singer.'],
  [
    'music',
    'Import the reference',
    'Drag in the vocal you want to learn. Isolated vocals give the most reliable measurements; add lyrics to get word and phoneme timing.',
  ],
  [
    'mic',
    'Record or import your take',
    'Press R. With headphones on, the reference plays while you sing so your take lines up with it.',
  ],
  [
    'compare',
    'See both performances aligned',
    'Your take is warped onto the reference timeline, so each note and word sits under its counterpart.',
  ],
  [
    'target',
    'Click a bad region',
    'Heatmap cells, notes and words are clickable. The inspector shows reference, your values, the difference and how confident each measurement is.',
  ],
  [
    'bulb',
    'Understand why it sounds different',
    'Select a region and press W. Differences are ranked by size, confidence and how noticeable they usually are.',
  ],
  [
    'headphones',
    'Hear A/B',
    'Press A to jump between the reference and your take at the same moment, or loop with A↔B alternation.',
  ],
  [
    'dumbbell',
    'Fix one thing',
    '“What should I fix next?” (N) chooses one target, loops it and shows only the relevant graph.',
  ],
  [
    'trend-up',
    'Record again and track progress',
    'Each take is compared automatically; progress shows trends, personal bests and recurring habits.',
  ],
]

export function HelpView({ topic }: { topic?: string }) {
  const methods = useMethods()
  const [query, setQuery] = useState('')
  const active: Topic = (['start', 'methods', 'metrics', 'glossary', 'science'] as Topic[]).includes(
    topic as Topic,
  )
    ? (topic as Topic)
    : 'start'
  const glossary = useMemo(() => {
    const entries = Object.entries(methods.data?.glossary ?? {})
    const q = query.trim().toLowerCase()
    return q ? entries.filter(([term, text]) => `${term} ${text}`.toLowerCase().includes(q)) : entries
  }, [methods.data, query])
  const metrics = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = methods.data?.metrics ?? []
    return q
      ? list.filter((m) => `${m.name} ${m.id} ${m.description} ${m.why}`.toLowerCase().includes(q))
      : list
  }, [methods.data, query])
  return (
    <div className="page help">
      <div className="page-inner">
        <div className="page-header">
          <div>
            <h1>Help</h1>
            <p className="muted">
              How to use Vibrato, how every number is measured, and what the words mean.
            </p>
          </div>
          <Button variant="ghost" icon="keyboard" onClick={() => setUi({ shortcutsOpen: true })}>
            Keyboard shortcuts
          </Button>
        </div>
        <Tabs<Topic>
          ariaLabel="Help topics"
          value={active}
          onChange={(value) => navigate({ name: 'help', topic: value }, true)}
          items={[
            { id: 'start', label: 'Getting started', icon: 'home' },
            { id: 'methods', label: 'Methods', icon: 'activity' },
            { id: 'metrics', label: 'Measurements', icon: 'list' },
            { id: 'glossary', label: 'Glossary', icon: 'bookmark' },
            { id: 'science', label: 'Scientific caveats', icon: 'flask' },
          ]}
        />
        <div className="help-body" key={active}>
          {active === 'start' ? (
            <ol className="workflow">
              {WORKFLOW.map(([icon, title, text], index) => (
                <li key={title} className="workflow-step card card-pad">
                  <span className="step-number">{index + 1}</span>
                  <Icon name={icon} size={18} />
                  <div>
                    <strong>{title}</strong>
                    <p className="small muted">{text}</p>
                  </div>
                </li>
              ))}
            </ol>
          ) : null}
          {methods.loading && active !== 'start' ? <SkeletonLines lines={6} /> : null}
          {methods.error && active !== 'start' ? (
            <ErrorState error={methods.error} onRetry={() => void methods.refresh()} />
          ) : null}
          {active === 'methods' && methods.data ? (
            <div className="stack" style={{ gap: 12 }}>
              {Object.entries(methods.data.global).map(([key, text]) => (
                <section key={key} className="card card-pad">
                  <h3>{humanize(key)}</h3>
                  <p className="small">{text}</p>
                </section>
              ))}
              <section className="card card-pad">
                <h3>Categories</h3>
                <dl className="glossary">
                  {Object.entries(methods.data.categories).map(([key, text]) => (
                    <div key={key}>
                      <dt>{categoryLabel(key)}</dt>
                      <dd>{text}</dd>
                    </div>
                  ))}
                </dl>
              </section>
              <p className="tiny faint">
                Versions:{' '}
                {Object.entries(methods.data.versions)
                  .map(([k, v]) => `${k} ${v}`)
                  .join(' · ')}
                . Per-analyzer details are on the diagnostics page.
              </p>
            </div>
          ) : null}
          {active === 'metrics' && methods.data ? (
            <div className="stack" style={{ gap: 10 }}>
              <div style={{ width: 300 }}>
                <TextField
                  icon="search"
                  placeholder="Search measurements"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  aria-label="Search measurements"
                />
              </div>
              {metrics.map((m) => (
                <section key={m.id} className="card card-pad metric-help">
                  <div className="row">
                    <strong className="grow">{m.name}</strong>
                    <Badge>{categoryLabel(m.category)}</Badge>
                    <BasisTag basis={m.basis} />
                    {m.anatomy_dependent ? <Badge tone="warn">partly anatomical</Badge> : null}
                  </div>
                  <p className="small">{m.description}</p>
                  <p className="small muted">
                    <strong>Why it matters: </strong>
                    {m.why}
                  </p>
                  <p className="small muted">
                    <strong>Tolerance: </strong>
                    {m.tolerance} {m.unit} — {m.tolerance_basis}
                  </p>
                  <p className="tiny faint">
                    {m.id} · weight {m.weight} · importance {m.importance} · trainability {m.trainability} ·
                    higher = {m.higher}, lower = {m.lower}
                  </p>
                </section>
              ))}
            </div>
          ) : null}
          {active === 'glossary' && methods.data ? (
            <div className="stack" style={{ gap: 10 }}>
              <div style={{ width: 300 }}>
                <TextField
                  icon="search"
                  placeholder="Search the glossary"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  aria-label="Search glossary"
                />
              </div>
              <dl className="glossary card card-pad">
                {glossary.map(([term, text]) => (
                  <div key={term}>
                    <dt>{term}</dt>
                    <dd>{text}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : null}
          {active === 'science' ? (
            <div className="stack" style={{ gap: 12 }}>
              <section className="card card-pad">
                <h3>What audio can and cannot tell</h3>
                <p className="small">
                  A recording shows the sound, not the body that made it. Vibrato measures acoustic properties
                  — pitch, timing, formant frequencies, loudness, spectral balance, periodicity — and derives
                  comparisons from them. It never observes tongue position, larynx height, vocal-fold
                  behaviour or muscle activity directly. When coaching mentions a physical cause, it is
                  labelled <BasisTag basis="inferred" /> and phrased as “likely”.
                </p>
              </section>
              <section className="card card-pad">
                <h3>How to read the labels</h3>
                <dl className="glossary">
                  <div>
                    <dt>
                      <BasisTag basis="measured" />
                    </dt>
                    <dd>Read directly from the audio signal (e.g. pitch in cents, loudness in dB).</dd>
                  </div>
                  <div>
                    <dt>
                      <BasisTag basis="derived" />
                    </dt>
                    <dd>
                      Calculated from measured values (e.g. normalised formants, breathiness index from CPPS).
                    </dd>
                  </div>
                  <div>
                    <dt>
                      <BasisTag basis="inferred" />
                    </dt>
                    <dd>
                      A probable physical or perceptual interpretation. Useful as a hint, not a diagnosis.
                    </dd>
                  </div>
                  <div>
                    <dt>
                      <BasisTag basis="experimental" />
                    </dt>
                    <dd>Produced by a method with limited validation; treat with extra caution.</dd>
                  </div>
                </dl>
              </section>
              <section className="card card-pad">
                <h3>Scores and priorities</h3>
                <p className="small">
                  Scores turn each difference into 0–100 using a tolerance inspired by typical just-noticeable
                  differences. The overall score is a convenience summary and is not diagnostic. Coaching
                  priorities multiply the size of a difference by confidence, typical perceptual importance,
                  persistence across takes and how trainable it is. These weights are transparent heuristics,
                  not a validated perceptual model, and you can override them.
                </p>
              </section>
              <section className="card card-pad">
                <h3>Synthetic previews</h3>
                <p className="small">
                  Counterfactual previews modify your own recording in one respect using standard signal
                  processing (PSOLA, gain envelopes, filtering, WORLD). They are always labelled synthetic,
                  never imitate the reference singer’s voice, and do not predict how your body would produce
                  the sound.
                </p>
              </section>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
