import type { Task } from '../../api/types'
import { Button } from '../../components/ui/Button'
import { ProgressBar } from '../../components/ui/Feedback'
import { Icon } from '../../components/ui/Icon'
import { cancelTask } from '../../state/tasks'

const ANALYSIS_STEPS = [
  { id: 'decode', label: 'Audio checks', until: 0.05 },
  { id: 'pitch', label: 'Pitch tracking', until: 0.45 },
  { id: 'features', label: 'Formants & voice quality', until: 0.78 },
  { id: 'segment', label: 'Phrases, words & notes', until: 0.8 },
  { id: 'analyzers', label: 'Analyzers', until: 1 },
]

const COMPARE_STEPS = [
  { id: 'reference', label: 'Reference analysis', until: 0.4 },
  { id: 'take', label: 'Take analysis', until: 0.8 },
  { id: 'align', label: 'Alignment', until: 0.88 },
  { id: 'compare', label: 'Measurements', until: 0.94 },
  { id: 'coach', label: 'Coaching', until: 1 },
]

export function PipelineProgress({ task, title }: { task: Task; title?: string }) {
  const steps = task.kind === 'compare' ? COMPARE_STEPS : ANALYSIS_STEPS
  const current = steps.findIndex((s) => task.progress < s.until)
  const index = current < 0 ? steps.length - 1 : current
  return (
    <div className="pipeline" role="status" aria-live="polite">
      <div className="row">
        <span className="spinner" />
        <strong>{title ?? (task.kind === 'compare' ? 'Comparing with the reference' : 'Analysing')}</strong>
        <span className="spacer" />
        <span className="num faint small">{Math.round(task.progress * 100)}%</span>
        <Button size="xs" variant="ghost" icon="x" onClick={() => void cancelTask(task.id)}>
          Cancel
        </Button>
      </div>
      <ol className="pipeline-steps">
        {steps.map((step, i) => (
          <li key={step.id} className={i < index ? 'is-done' : i === index ? 'is-current' : undefined}>
            <span className="pipeline-dot">{i < index ? <Icon name="check" size={10} /> : null}</span>
            {step.label}
          </li>
        ))}
      </ol>
      <ProgressBar value={task.progress} label="Analysis progress" />
      <p className="tiny faint truncate">{task.message}</p>
    </div>
  )
}
