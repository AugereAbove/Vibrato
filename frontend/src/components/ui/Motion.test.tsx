import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ScoreRing } from './Motion'

describe('ScoreRing', () => {
  it('announces the score', () => {
    render(<ScoreRing score={72.4} label="Overall" />)
    expect(screen.getByRole('img', { name: 'Overall 72 out of 100' })).toBeInTheDocument()
    expect(screen.getByText('72')).toBeInTheDocument()
  })

  it('marks low confidence instead of hiding it', () => {
    render(<ScoreRing score={80} confidence={0.3} label="Pitch" />)
    const ring = screen.getByRole('img', { name: 'Pitch 80 out of 100, low confidence' })
    expect(ring).toHaveClass('is-uncertain')
  })

  it('says when there is no score', () => {
    render(<ScoreRing score={null} label="Vibrato" />)
    expect(screen.getByRole('img', { name: 'Vibrato not available' })).toBeInTheDocument()
    expect(screen.getByText('–')).toBeInTheDocument()
  })

  it('shows the change from the previous take', () => {
    render(<ScoreRing score={70} previous={64} size={72} />)
    expect(screen.getByText('+6')).toHaveClass('score-ring-delta')
  })
})
