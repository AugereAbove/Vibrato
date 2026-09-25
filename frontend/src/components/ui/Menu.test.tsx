import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MenuButton } from './Menu'

function setup() {
  const rename = vi.fn()
  const remove = vi.fn()
  const user = userEvent.setup()
  render(
    <MenuButton
      label="Take actions"
      items={[
        { label: 'Rename', onSelect: rename },
        { label: 'Export', onSelect: vi.fn(), disabled: true },
        'separator',
        { label: 'Delete', onSelect: remove, danger: true },
      ]}
    />,
  )
  return { rename, remove, user }
}

describe('MenuButton', () => {
  it('opens with the first item focused and skips disabled items', async () => {
    const { remove, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Take actions' }))
    expect(screen.getByRole('menu', { name: 'Take actions' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Rename' })).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitem', { name: 'Rename' })).toHaveFocus()
    await user.keyboard('{ArrowUp}{Enter}')
    expect(remove).toHaveBeenCalledOnce()
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('closes on Escape and returns focus to the button', async () => {
    const { rename, user } = setup()
    const button = screen.getByRole('button', { name: 'Take actions' })
    await user.click(button)
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(button).toHaveFocus()
    expect(rename).not.toHaveBeenCalled()
  })

  it('closes when clicking elsewhere', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: 'Take actions' }))
    await user.click(document.body)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})
