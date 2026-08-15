import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import { PolicyTrace } from './PolicyTrace'
import type { PolicyRule } from '@/types/api'

const samplePassRule: PolicyRule = {
  rule_id: 'R1_ELIGIBILITY',
  state: 'pass',
  detail: 'levers matched catalog requirements',
}

const sampleVetoRule: PolicyRule = {
  rule_id: 'R6_INVOLUNTARY',
  state: 'veto',
  detail: 'account flagged involuntary (moved / deceased)',
}

const sampleNotEvaluableRule: PolicyRule = {
  rule_id: 'R4_COOLDOWN',
  state: 'not_evaluable',
  detail: 'no offer-history feed connected',
  unmet_requirement: 'recommendation history per customer, last 90d',
}

const sampleMultiRules: PolicyRule[] = [
  samplePassRule,
  sampleVetoRule,
  sampleNotEvaluableRule,
]

describe('PolicyTrace', () => {
  it('renders a pass rule with neutral tone and visible "pass" text', () => {
    render(<PolicyTrace rules={[samplePassRule]} />)

    const badge = screen.getByText('pass')
    expect(badge).toBeInTheDocument()
    // Neutral tone (quiet, non-risk): border-line-strong text-ink-2
    expect(badge).toHaveClass('text-ink-2')
    expect(badge).not.toHaveClass('text-low')
  })

  it('renders a veto rule through Badge with non-risk danger styling and visible "veto" text', () => {
    render(<PolicyTrace rules={[sampleVetoRule]} />)

    const badge = screen.getByText('veto')
    expect(badge).toBeInTheDocument()
    // Must use application danger token (text-danger), strictly avoiding risk-band critical (text-critical)
    expect(badge).toHaveClass('text-danger')
    expect(badge).not.toHaveClass('text-critical')
  })

  it('renders a not_evaluable rule with warn tone, "not checked" text, and the specific unmet requirement feed', () => {
    render(<PolicyTrace rules={[sampleNotEvaluableRule]} />)

    const badge = screen.getByText('not checked')
    expect(badge).toBeInTheDocument()
    // warn tone is reserved for not_evaluable
    expect(badge).toHaveClass('text-warn')

    // Specific missing data feed name rendered from unmet_requirement
    expect(
      screen.getByText('Needs: recommendation history per customer, last 90d'),
    ).toBeInTheDocument()
  })

  it('never renders unmet_requirement for pass or veto rules', () => {
    render(<PolicyTrace rules={[samplePassRule, sampleVetoRule]} />)

    expect(screen.queryByText(/Needs:/i)).not.toBeInTheDocument()
  })

  it('renders rule_id verbatim in a monospaced element for audit integrity', () => {
    const { container } = render(<PolicyTrace rules={sampleMultiRules} />)

    const monoIds = Array.from(container.querySelectorAll('.font-mono')).map(
      (el) => el.textContent,
    )
    expect(monoIds).toEqual(['R1_ELIGIBILITY', 'R6_INVOLUNTARY', 'R4_COOLDOWN'])
  })

  it('passes axe accessibility checks standalone on a multi-state rule list with zero violations', async () => {
    const { container } = render(<PolicyTrace rules={sampleMultiRules} />)
    const results = await axe(container)
    expect(results.violations).toEqual([])
  })
})
