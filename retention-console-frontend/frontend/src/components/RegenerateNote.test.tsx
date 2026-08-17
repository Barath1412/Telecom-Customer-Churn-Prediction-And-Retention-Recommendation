import { describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import userEvent from '@testing-library/user-event'
import { renderApp, screen, waitFor } from '@/test/utils'
import { server } from '@/mocks/server'
import { api } from '@/lib/api'
import { NarrationPanel } from './NarrationPanel'
import type { Narration } from '@/types/api'

const existing: Narration = {
  summary: 'The note that was already on the page.',
  why: 'Two observable gaps put this account near the top of the list.',
  talk_track: 'Confirm the account details on screen, then present the offer.',
  evidence_ids: ['DELTA-051', 'LEVER-060'],
  uncertainty_note: 'The retention effect used to rank this offer is a business assumption.',
  source: 'example_fixture',
  model: '',
  validator_attempts: 1,
  generated_at: '2026-08-13T02:04:11Z',
}

describe('NarrationPanel — live generation', () => {
  it('shows no button when no customerId is given', () => {
    renderApp(<NarrationPanel narration={existing} />)
    expect(screen.queryByRole('button', { name: /generate note/i })).not.toBeInTheDocument()
    expect(screen.getByText(existing.summary)).toBeInTheDocument()
  })

  it('replaces the note and reports how it was generated, calling api.narrate with force: true', async () => {
    const narrateSpy = vi.spyOn(api, 'narrate')
    const user = userEvent.setup()
    renderApp(<NarrationPanel narration={existing} customerId="0295-PPHDO" />)

    const btn = screen.getByRole('button', { name: /generate note with ai/i })
    await user.click(btn)

    expect(narrateSpy).toHaveBeenCalledWith('0295-PPHDO', { force: true })

    await waitFor(() =>
      expect(screen.getByText(/generated just now/i)).toBeInTheDocument(),
    )
    // The mock says validator_attempts: 2, so the panel must say the first draft
    // was rejected rather than quietly showing a clean single pass.
    expect(screen.getByText(/first draft was rejected by a validator/i)).toBeInTheDocument()
    expect(screen.getByText(/in 7\.4s/i)).toBeInTheDocument()
    expect(screen.queryByText(existing.summary)).not.toBeInTheDocument()

    // Second click after note already exists also passes { force: true }
    await user.click(btn)
    expect(narrateSpy).toHaveBeenCalledTimes(2)
    expect(narrateSpy).toHaveBeenLastCalledWith('0295-PPHDO', { force: true })

    narrateSpy.mockRestore()
  })

  it('keeps the previous note on screen when generation fails', async () => {
    server.use(
      http.post('/api/customers/:id/narrate', () =>
        HttpResponse.json(
          {
            error: {
              code: 'NARRATION_TIMEOUT',
              message: 'The model did not respond within 30s.',
              request_id: 'req_test',
            },
          },
          { status: 504 },
        ),
      ),
    )
    const user = userEvent.setup()
    renderApp(<NarrationPanel narration={existing} customerId="0295-PPHDO" />)

    await user.click(screen.getByRole('button', { name: /generate note with ai/i }))

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('alert')).toHaveTextContent(/NARRATION_TIMEOUT/)
    // The whole point: a failed generation must not blank the panel.
    expect(screen.getByText(existing.summary)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /generate note with ai/i })).toBeEnabled()
  })

  it('offers generation even when there is no note yet', () => {
    renderApp(<NarrationPanel narration={null} customerId="5461-QKNTN" />)
    expect(screen.getByRole('button', { name: /generate note with ai/i })).toBeInTheDocument()
    expect(screen.getByText(/no note was generated/i)).toBeInTheDocument()
  })
})
