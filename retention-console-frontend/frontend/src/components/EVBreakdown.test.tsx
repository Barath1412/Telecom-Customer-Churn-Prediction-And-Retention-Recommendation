import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import { EVBreakdown } from './EVBreakdown'
import type { Recommendation, Risk, Value } from '@/types/api'

const sampleRisk: Risk = {
  p_churn: 0.99,
  risk_band: 'critical',
  percentile: 100,
}

const sampleValue: Value = {
  cltv: 5962.0,
  monthly_charges: 95.45,
  tenure_months: 1,
  currency: 'USD',
}

const sampleRec: Recommendation = {
  offer_id: 'OFF-BUNDLE-ALL',
  offer_name: 'Tech Support + Online Security bundle, 12 months',
  cost: 120.51,
  delta_prior: 0.14,
  delta_ci: [0.05, 0.24],
  delta_source: 'business_judgment_v1',
  expected_value: 705.82,
  requires_approval: false,
}

describe('EVBreakdown', () => {
  it('renders the formula in full with real substituted numbers', () => {
    render(<EVBreakdown risk={sampleRisk} value={sampleValue} rec={sampleRec} />)

    // Formula components
    expect(screen.getAllByText('99.0%').length).toBeGreaterThan(0)
    expect(screen.getAllByText('$5,962.00').length).toBeGreaterThan(0)
    expect(screen.getByText('14%')).toBeInTheDocument()
    expect(screen.getAllByText('$120.51').length).toBeGreaterThan(0)
    expect(screen.getByText('$705.82')).toBeInTheDocument()
  })

  it('renders a definition list breaking out all four inputs', () => {
    render(<EVBreakdown risk={sampleRisk} value={sampleValue} rec={sampleRec} />)

    expect(screen.getByText('Churn risk')).toBeInTheDocument()
    expect(screen.getByText('Lifetime value')).toBeInTheDocument()
    expect(screen.getByText('Assumed effect')).toBeInTheDocument()
    expect(screen.getByText('Offer cost')).toBeInTheDocument()
  })

  it('never prints a delta without its range in the definition list', () => {
    render(<EVBreakdown risk={sampleRisk} value={sampleValue} rec={sampleRec} />)

    // Asserts exact deltaWithRange output format: "14% assumed (range 5%–24%)"
    expect(screen.getByText('14% assumed (range 5%–24%)')).toBeInTheDocument()
  })

  it('renders the provenance line with delta_source when present', () => {
    render(<EVBreakdown risk={sampleRisk} value={sampleValue} rec={sampleRec} />)

    expect(
      screen.getByText(/The effect size is a business assumption \(business_judgment_v1\)/i),
    ).toBeInTheDocument()
  })

  it('explicitly renders "unsourced" in the provenance line when delta_source is null', () => {
    const unsourcedRec: Recommendation = {
      ...sampleRec,
      delta_source: null,
    }

    render(<EVBreakdown risk={sampleRisk} value={sampleValue} rec={unsourcedRec} />)

    expect(
      screen.getByText(/The effect size is a business assumption \(unsourced\)/i),
    ).toBeInTheDocument()
  })

  it('formats money to 2 decimals and probabilities to 1 decimal with .num styling', () => {
    const rawRec: Recommendation = {
      ...sampleRec,
      cost: 120.5,
      expected_value: 705.816,
    }
    const rawRisk: Risk = {
      ...sampleRisk,
      p_churn: 0.9227,
    }
    const rawValue: Value = {
      ...sampleValue,
      cltv: 5000,
    }

    const { container } = render(
      <EVBreakdown risk={rawRisk} value={rawValue} rec={rawRec} />,
    )

    // Formatted money values (always 2 decimals)
    expect(screen.getAllByText('$120.50').length).toBeGreaterThan(0)
    expect(screen.getByText('$705.82')).toBeInTheDocument()
    expect(screen.getAllByText('$5,000.00').length).toBeGreaterThan(0)

    // Formatted probability (1 decimal)
    expect(screen.getAllByText('92.3%').length).toBeGreaterThan(0)

    // Verify .num monospaced class is applied to numeric outputs
    const numElements = container.querySelectorAll('.num')
    expect(numElements.length).toBeGreaterThan(0)
  })

  it('passes axe accessibility checks standalone with zero violations', async () => {
    const { container } = render(
      <EVBreakdown risk={sampleRisk} value={sampleValue} rec={sampleRec} />,
    )
    const results = await axe(container)
    expect(results.violations).toEqual([])
  })
})
