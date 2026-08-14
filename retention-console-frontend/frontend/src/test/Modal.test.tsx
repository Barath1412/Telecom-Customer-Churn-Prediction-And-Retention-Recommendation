import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { renderApp, screen } from './utils'

describe('Modal focus trap', () => {
  it('moves focus in, cycles with Tab, and closes on Escape', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    renderApp(
      <Modal open onClose={onClose} title="Approve recommendation">
        <Button>First</Button>
        <Button>Last</Button>
      </Modal>,
    )
    expect(screen.getByRole('button', { name: 'First' })).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'Last' })).toHaveFocus()
    await user.tab()
    // Wrapped, not escaped into the page behind.
    expect(screen.getByRole('button', { name: 'First' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('is exposed as a dialog', () => {
    renderApp(
      <Modal open onClose={() => {}} title="Reject recommendation">
        <Button>OK</Button>
      </Modal>,
    )
    expect(screen.getByRole('dialog', { name: 'Reject recommendation' })).toHaveAttribute(
      'aria-modal',
      'true',
    )
  })
})
