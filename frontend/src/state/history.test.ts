import { beforeEach, describe, expect, it } from 'vitest'
import { clearHistory, pushUndo, redo, undo, useHistory } from './history'
import { useToasts } from './toasts'

describe('undo history', () => {
  beforeEach(() => {
    clearHistory()
    useToasts.setState({ toasts: [] })
  })

  it('undoes and redoes in order', async () => {
    let value = 0
    const change = (to: number) => {
      const from = value
      value = to
      pushUndo({ label: `set ${to}`, undo: () => void (value = from), redo: () => void (value = to) })
    }
    change(1)
    change(2)
    await undo()
    expect(value).toBe(1)
    await undo()
    expect(value).toBe(0)
    await undo()
    expect(value).toBe(0)
    await redo()
    expect(value).toBe(1)
    await redo()
    expect(value).toBe(2)
  })

  it('drops the redo stack after a new change', async () => {
    pushUndo({ label: 'a', undo: () => {}, redo: () => {} })
    await undo()
    expect(useHistory.getState().future).toHaveLength(1)
    pushUndo({ label: 'b', undo: () => {}, redo: () => {} })
    expect(useHistory.getState().future).toHaveLength(0)
  })

  it('keeps the entry and reports the error when undo fails', async () => {
    pushUndo({
      label: 'rename take',
      undo: () => Promise.reject(new Error('disk full')),
      redo: () => {},
    })
    await undo()
    expect(useHistory.getState().past).toHaveLength(1)
    expect(useHistory.getState().busy).toBe(false)
    const toast = useToasts.getState().toasts.at(-1)
    expect(toast?.kind).toBe('error')
    expect(toast?.title).toContain('Could not undo "rename take"')
    expect(toast?.body).toBe('disk full')
  })

  it('caps the history length', () => {
    for (let i = 0; i < 80; i += 1) pushUndo({ label: String(i), undo: () => {}, redo: () => {} })
    const past = useHistory.getState().past
    expect(past).toHaveLength(50)
    expect(past.at(-1)?.label).toBe('79')
  })
})
