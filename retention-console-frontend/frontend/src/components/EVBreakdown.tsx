import { deltaWithRange, pct, usd } from '@/lib/format'
import type { Recommendation, Risk, Value } from '@/types/api'

export interface EVBreakdownProps {
  risk: Risk
  value: Value
  rec: Recommendation
}

/**
 * Shows the arithmetic, not just the answer.
 *
 * The expected value is the number that decides who gets called, and one of its
 * four inputs (Δ) is a business assumption rather than a measurement. Printing
 * the sum in full is what lets an agent — or a mentor — see that immediately
 * instead of trusting a single figure.
 */
export function EVBreakdown({ risk, value, rec }: EVBreakdownProps) {
  return (
    <div className="space-y-3">
      {/* 1. Formula shown in full: P × CLTV × Δ − cost = EV */}
      <div className="num flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
        <span>{pct(risk.p_churn)}</span>
        <span className="text-ink-3">×</span>
        <span>{usd(value.cltv)}</span>
        <span className="text-ink-3">×</span>
        <span>{pct(rec.delta_prior, 0)}</span>
        <span className="text-ink-3">−</span>
        <span>{usd(rec.cost)}</span>
        <span className="text-ink-3">=</span>
        <span className="text-base font-semibold">{usd(rec.expected_value)}</span>
      </div>

      {/* 2. Definition list breaking out each of the four inputs */}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
        <Row term="Churn risk" def={pct(risk.p_churn)} />
        <Row term="Lifetime value" def={usd(value.cltv)} />
        <Row term="Assumed effect" def={deltaWithRange(rec.delta_prior, rec.delta_ci)} />
        <Row term="Offer cost" def={usd(rec.cost)} />
      </dl>

      {/* 3. Provenance line */}
      <p className="text-micro text-ink-3">
        The effect size is a business assumption ({rec.delta_source ?? 'unsourced'}), not a
        measured result. Ranking is a hypothesis under test until the control group reports.
      </p>
    </div>
  )
}

function Row({ term, def }: { term: string; def: string }) {
  return (
    <div>
      <dt className="text-ink-3">{term}</dt>
      <dd className="num text-ink">{def}</dd>
    </div>
  )
}
