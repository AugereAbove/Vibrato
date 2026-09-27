import type { Comparison, Finding, Recording } from '../../../api/types'
import { engine } from '../../../audio/engine'
import { Button } from '../../../components/ui/Button'
import { Icon } from '../../../components/ui/Icon'
import { CATEGORY_ICONS } from '../../../lib/categories'
import { setPref } from '../../../state/prefs'
import { openRecorder } from '../recordStore'
import { categoryBars, focusFindings, nailedIt, plainSentence, plainTip, verdict } from './plainResults'

function hear(mode: 'ref' | 'take', finding: Finding): void {
  const practice = finding.practice
  if (!practice) return
  engine.setAlternate(false)
  void engine.playRange(mode, practice.ref_start, practice.ref_end)
}

function FocusCard({ finding, rank, hasTake }: { finding: Finding; rank: number; hasTake: boolean }) {
  const practice = finding.practice
  return (
    <li className="simple-focus">
      <span className="simple-focus-rank" aria-hidden>
        {rank}
      </span>
      <div className="simple-focus-body">
        <p className="simple-focus-text">{plainSentence(finding)}</p>
        <p className="simple-focus-tip">
          <strong>Tip:</strong> {plainTip(finding)}
        </p>
        {practice ? (
          <div className="simple-focus-actions">
            <Button size="sm" variant="secondary" icon="play" onClick={() => hear('ref', finding)}>
              Hear the singer
            </Button>
            <Button
              size="sm"
              variant="secondary"
              icon="play"
              disabled={!hasTake}
              onClick={() => hear('take', finding)}
            >
              Hear yourself
            </Button>
            <Button
              size="sm"
              variant="accent-soft"
              icon="mic"
              onClick={() => openRecorder({ start: practice.ref_start, end: practice.ref_end })}
            >
              Sing this bit again
            </Button>
          </div>
        ) : null}
      </div>
    </li>
  )
}

export function SimpleResults({ comparison, take }: { comparison: Comparison; take: Recording | null }) {
  const overall = comparison.scores.overall
  const result = verdict(overall.score)
  const focus = focusFindings(comparison.coaching)
  const good = nailedIt(comparison.coaching)
  const bars = categoryBars(comparison.scores)
  const shaky = comparison.warnings.length > 0 || (overall.score !== null && overall.confidence < 0.4)
  const isBest =
    comparison.personal_best?.comparison_id === comparison.id &&
    comparison.previous !== null &&
    comparison.previous.overall !== null &&
    overall.score !== null &&
    overall.score > comparison.previous.overall
  const change =
    comparison.previous && comparison.previous.overall !== null && overall.score !== null
      ? Math.round(overall.score) - Math.round(comparison.previous.overall)
      : null
  return (
    <section className="simple-results" aria-label="Your result">
      <header className={`simple-verdict tone-${result.tone}`}>
        <div
          className="simple-score"
          aria-label={result.score === null ? 'No score' : `${result.score} out of 100`}
        >
          {result.score === null ? (
            <Icon name="alert" size={28} />
          ) : (
            <>
              <span className="simple-score-value">{result.score}</span>
              <span className="simple-score-max">/ 100</span>
            </>
          )}
        </div>
        <div className="grow">
          <h2 className="simple-phrase">{result.phrase}</h2>
          <p className="simple-detail">{result.detail}</p>
          <div className="simple-badges">
            {isBest ? (
              <span className="celebrate" role="status">
                <Icon name="star-filled" size={13} /> Your best take yet
              </span>
            ) : null}
            {change !== null && change !== 0 ? (
              <span className={`simple-change ${change > 0 ? 'is-up' : 'is-down'}`}>
                <Icon name={change > 0 ? 'trend-up' : 'trend-down'} size={13} />
                {change > 0 ? `${change} better` : `${-change} lower`} than your last take
              </span>
            ) : null}
          </div>
        </div>
        <Button variant="primary" icon="record" onClick={() => openRecorder(null)}>
          Record another take
        </Button>
      </header>

      {shaky ? (
        <p className="simple-note">
          <Icon name="info" size={14} /> This recording was hard to measure, so treat the result as a rough
          guide. Try singing closer to the microphone with no music playing in the room.
        </p>
      ) : null}

      <div className="simple-columns">
        <div className="simple-section">
          <h3 className="simple-heading">{focus.length ? 'Work on these' : 'Nothing big to fix'}</h3>
          {focus.length ? (
            <ol className="simple-focus-list">
              {focus.map((finding, index) => (
                <FocusCard key={finding.key} finding={finding} rank={index + 1} hasTake={Boolean(take)} />
              ))}
            </ol>
          ) : (
            <p className="simple-empty">
              {overall.score === null
                ? 'We need a clearer recording before we can give advice.'
                : 'Nothing stood out as clearly different from the singer. Great work! Try a harder part of the song next.'}
            </p>
          )}
        </div>

        <div className="simple-side">
          {good.length ? (
            <div className="simple-section">
              <h3 className="simple-heading">You nailed</h3>
              <ul className="simple-good-list">
                {good.map((text) => (
                  <li key={text}>
                    <Icon name="check" size={14} /> {text}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {bars.length ? (
            <div className="simple-section">
              <h3 className="simple-heading">How each part went</h3>
              <ul className="simple-bars">
                {bars.map((bar) => (
                  <li key={bar.id} className="simple-bar">
                    <span className="simple-bar-label">
                      <Icon name={CATEGORY_ICONS[bar.id] ?? 'dot'} size={13} />
                      {bar.label}
                    </span>
                    <span
                      className="simple-bar-track"
                      role="meter"
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={bar.score}
                      aria-label={`${bar.label}: ${bar.word}`}
                    >
                      <span className="simple-bar-fill" style={{ width: `${bar.score}%` }} />
                    </span>
                    <span className="simple-bar-word">{bar.word}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>

      <footer className="simple-footer">
        <Button variant="ghost" icon="sliders" onClick={() => setPref('display.results_view', 'full')}>
          Show full analysis
        </Button>
      </footer>
    </section>
  )
}
