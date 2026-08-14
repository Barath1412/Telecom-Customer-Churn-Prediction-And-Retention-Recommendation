import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'
import { useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { renderApp, screen } from './utils'

function ModalWithTrigger() {
  const [open, setOpen] = useState(false)
  return (
    <div>
      <Button onClick={() => setOpen(true)}>Open Modal</Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Approve recommendation" description="This action is audited.">
        <Button>First</Button>
        <Button>Last</Button>
      </Modal>
    </div>
  )
}

describe('Modal focus trap and accessibility', () => {
  it('traps focus in the confirmation dialog and closes on Escape', async () => {
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
    // Wrapped back to first element, not escaped into the page
    expect(screen.getByRole('button', { name: 'First' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('cycles backward with Shift+Tab from first element to last element', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    renderApp(
      <Modal open onClose={onClose} title="Approve recommendation">
        <Button>First</Button>
        <Button>Last</Button>
      </Modal>,
    )
    expect(screen.getByRole('button', { name: 'First' })).toHaveFocus()
    await user.tab({ shift: true })
    expect(screen.getByRole('button', { name: 'Last' })).toHaveFocus()
  })

  it('restores focus to the triggering element when closed', async () => {
    const user = userEvent.setup()
    renderApp(<ModalWithTrigger />)
    const trigger = screen.getByRole('button', { name: 'Open Modal' })
    await user.click(trigger)
    expect(screen.getByRole('button', { name: 'First' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(trigger).toHaveFocus()
  })

  it('is exposed as a dialog with aria-modal, title and description', () => {
    renderApp(
      <Modal
        open
        onClose={() => {}}
        title="Reject recommendation"
        description="Reason is required"
        footer={<Button>Confirm</Button>}
      >
        <p>Modal body content</p>
      </Modal>,
    )
    const dialog = screen.getByRole('dialog', { name: 'Reject recommendation' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByText('Reason is required')).toHaveAttribute('id', 'modal-desc')
    expect(dialog).toHaveAttribute('aria-describedby', 'modal-desc')
  })

  it('has zero axe accessibility violations when open', async () => {
    const { container } = renderApp(
      <Modal open onClose={() => {}} title="Accessible Modal" description="Zero violations expected">
        <Button>Action</Button>
      </Modal>,
    )
    const results = await axe(container)
    expect(results.violations).toEqual([])
  })
})
