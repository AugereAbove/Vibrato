import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { confirmAction } from './confirm'
import { ConfirmHost } from './Dialog'

async function ask(): Promise<{ answer: Promise<boolean> }> {
  let answer!: Promise<boolean>
  await act(async () => {
    answer = confirmAction({
      title: 'Delete take 3?',
      body: 'This cannot be undone.',
      confirmLabel: 'Delete',
      danger: true,
    })
  })
  return { answer }
}

describe('confirmAction', () => {
  it('resolves true when confirmed', async () => {
    const user = userEvent.setup()
    render(<ConfirmHost />)
    const { answer } = await ask()
    expect(screen.getByRole('dialog', { name: 'Delete take 3?' })).toBeInTheDocument()
    expect(screen.getByText('This cannot be undone.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    await expect(answer).resolves.toBe(true)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('resolves false on Escape and on Cancel', async () => {
    const user = userEvent.setup()
    render(<ConfirmHost />)
    const first = await ask()
    await user.keyboard('{Escape}')
    await expect(first.answer).resolves.toBe(false)
    const second = await ask()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await expect(second.answer).resolves.toBe(false)
  })

  it('keeps focus inside the dialog', async () => {
    const user = userEvent.setup()
    render(<ConfirmHost />)
    const { answer } = await ask()
    const confirm = screen.getByRole('button', { name: 'Delete' })
    act(() => confirm.focus())
    await user.tab()
    expect(screen.getByRole('button', { name: 'Close' })).toHaveFocus()
    await user.tab({ shift: true })
    expect(confirm).toHaveFocus()
    await user.keyboard('{Enter}')
    await expect(answer).resolves.toBe(true)
  })

  it('cancels a pending question when a new one arrives', async () => {
    render(<ConfirmHost />)
    const first = await ask()
    await ask()
    await expect(first.answer).resolves.toBe(false)
  })
})
