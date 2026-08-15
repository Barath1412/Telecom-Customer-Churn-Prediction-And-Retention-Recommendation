import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import { NarrationPanel } from './NarrationPanel'
import type { Narration } from '@/types/api'

const sampleLlmNarration: Narration = {
  summary: 'Fibre customer one month in, on a rolling contract with no support or security add-ons.',
  why: 'Two observable gaps put this account at the top of list: a month-to-month contract and no tech-support add-on.',
  talk_track: "I can see you joined us last month on fibre. I'm able to add Tech Support and Online Security.",
  evidence_ids: ['DELTA-051', 'LEVER-060', 'LEVER-061'],
  uncertainty_note: 'The retention effect used to rank this offer is a business assumption of 0.14.',
  source: 'llm',
  model: 'gemini-3.5-flash-lite',
  validator_attempts: 2,
  generated_at: '2026-08-13T02:04:11Z',
}

const sampleTemplateNarration: Narration = {
  ...sampleLlmNarration,
  source: 'fallback_template',
  model: '',
  validator_attempts: 1,
}

describe('NarrationPanel', () => {
  it('renders narration content correctly when present', () => {
    render(<NarrationPanel narration={sampleLlmNarration} />)

    expect(
      screen.getByText(/Fibre customer one month in, on a rolling contract/i),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/Two observable gaps put this account at the top/i),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/I can see you joined us last month on fibre/i),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/The retention effect used to rank this offer is a business assumption/i),
    ).toBeInTheDocument()
  })

  it('labels LLM generated notes with model name and info badge tone', () => {
    render(<NarrationPanel narration={sampleLlmNarration} />)

    const badge = screen.getByText('AI-drafted · gemini-3.5-flash-lite')
    expect(badge).toBeInTheDocument()
    // Info badge maps to border-accent text-accent in Badge component
    expect(badge).toHaveClass('text-accent')
  })

  it('labels template fallback notes with neutral badge tone', () => {
    render(<NarrationPanel narration={sampleTemplateNarration} />)

    const badge = screen.getByText('Template · no model')
    expect(badge).toBeInTheDocument()
    // Neutral badge has border-line-strong text-ink-2 classes
    expect(badge).toHaveClass('text-ink-2')
  })

  it('renders rewrite badge with neutral tone (avoiding warn tone collision) when validator_attempts > 1', () => {
    render(<NarrationPanel narration={sampleLlmNarration} />)

    // validator_attempts = 2 -> rewritten 1×
    const rewriteBadge = screen.getByText('rewritten 1×')
    expect(rewriteBadge).toBeInTheDocument()
    // Must use neutral tone (text-ink-2), never warn (text-warn)
    expect(rewriteBadge).toHaveClass('text-ink-2')
    expect(rewriteBadge).not.toHaveClass('text-warn')
  })

  it('renders evidence IDs verbatim in a monospaced element for audit integrity', () => {
    const { container } = render(<NarrationPanel narration={sampleLlmNarration} />)

    const evidenceSpan = container.querySelector('span.font-mono')
    expect(evidenceSpan).toBeInTheDocument()
    expect(evidenceSpan).toHaveTextContent('DELTA-051, LEVER-060, LEVER-061')
  })

  it('renders "none cited" in monospaced element when evidence_ids is empty', () => {
    const noEvidenceNarration: Narration = {
      ...sampleLlmNarration,
      evidence_ids: [],
    }

    const { container } = render(<NarrationPanel narration={noEvidenceNarration} />)

    const evidenceSpan = container.querySelector('span.font-mono')
    expect(evidenceSpan).toBeInTheDocument()
    expect(evidenceSpan).toHaveTextContent('none cited')
  })

  it('renders an explicit explanatory message when narration is null', () => {
    render(<NarrationPanel narration={null} />)

    expect(
      screen.getByText(
        'No note was generated for this customer. Use the levers and the policy trace directly.',
      ),
    ).toBeInTheDocument()
  })

  it('passes axe accessibility checks standalone on both non-null and null states', async () => {
    // Non-null narration
    const { container: container1 } = render(
      <NarrationPanel narration={sampleLlmNarration} />,
    )
    const result1 = await axe(container1)
    expect(result1.violations).toEqual([])

    // Null narration
    const { container: container2 } = render(<NarrationPanel narration={null} />)
    const result2 = await axe(container2)
    expect(result2.violations).toEqual([])
  })
})
