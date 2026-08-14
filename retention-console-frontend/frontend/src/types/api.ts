/**
 * Types mirroring api-contract/*.json exactly.
 *
 * These are the contract. If the backend changes a field, change it here first,
 * let TypeScript show you every screen that breaks, then fix those. That is the
 * entire reason this project is TypeScript and not JavaScript: the payload has
 * ~40 fields across five nesting levels, several of which are nullable in ways
 * that matter (`offer_id: null` means "no offer qualified", not "loading").
 */

export type Arm = 'treatment' | 'control'
export type RiskBand = 'critical' | 'high' | 'medium' | 'low'
export type RuleState = 'pass' | 'veto' | 'not_evaluable'
export type QueueStatus =
  | 'recommended'
  | 'no_eligible_offer'
  | 'involuntary_routed_to_account_ops'

export interface Lever {
  code: string
  label: string
}

export interface Risk {
  p_churn: number
  risk_band: RiskBand
  percentile: number
}

export interface Value {
  cltv: number
  monthly_charges: number
  tenure_months: number
  currency: string
}

export interface Recommendation {
  /** null when no offer qualified. Render the empty state, not a blank card. */
  offer_id: string | null
  offer_name: string | null
  cost: number
  delta_prior: number
  /** [low, high]. Never show delta_prior without this. */
  delta_ci: [number, number]
  delta_source: string | null
  expected_value: number
  requires_approval: boolean
}

export interface Alternative {
  offer_id: string
  offer_name: string
  delta_prior: number
  expected_value: number
}

export interface PolicyRule {
  rule_id: string
  state: RuleState
  detail: string
  /** Present only when state === 'not_evaluable'. What data feed is missing. */
  unmet_requirement?: string
}

export interface Attribution {
  feature: string
  contribution: number
  direction: 'increases_risk' | 'decreases_risk'
}

export interface Narration {
  summary: string
  why: string
  talk_track: string
  evidence_ids: string[]
  /** Composed by the backend from delta_prior/delta_ci. Never model-written. */
  uncertainty_note: string
  source: 'llm' | 'fallback_template' | 'example_fixture'
  model: string
  validator_attempts: number
  generated_at: string
}

export interface QueueItem {
  rank: number
  customer_id: string
  arm: Arm
  risk: Risk
  value: Value
  levers: Lever[]
  recommendation: Recommendation
  status: QueueStatus
}

export interface CustomerDetail extends QueueItem {
  alternatives: Alternative[]
  vetoed: { offer_id: string; rule_id: string; detail: string }[]
  attribution: Attribution[]
  attribution_disclaimer: string
  evidence: { ids: string[]; count: number; approx_tokens: number }
  policy_trace: PolicyRule[]
  profile: Record<string, string | number>
  provenance: {
    model_name: string
    model_version: string
    model_roc_auc: number
    catalog_version: number
    kb_version: number
    scored_at: string
  }
  narration: Narration | null
}

export interface QueueResponse {
  run_id: string
  capacity: number
  total_eligible: number
  returned: number
  page: number
  page_size: number
  items: QueueItem[]
}

export interface SummaryResponse {
  run_id: string
  generated_at: string
  model: { name: string; version: string; roc_auc: number; pr_auc: number; brier: number }
  funnel: {
    scored: number
    involuntary: number
    no_eligible_offer: number
    recommended: number
    queued_today: number
    treatment: number
    control: number
  }
  economics: { offer_spend: number; expected_value: number }
  offer_mix: Record<string, number>
  precision_at_capacity: number
  base_rate: number
  allocation_parity: {
    attribute: string
    group: string
    n: number
    queued: number
    queue_rate: number
    mean_offer_value: number
  }[]
  lever_prevalence: { code: string; pct_of_top100: number }[]
}

export interface Offer {
  offer_id: string
  name: string
  category: string
  requires_levers: string[]
  excludes_levers: string[]
  min_tenure_months: number
  cost_type: 'fixed' | 'pct_of_annual'
  discount_pct: number
  unit_cost: number | null
  delta_prior: number
  delta_ci: [number, number]
  delta_source: string
}

export interface CatalogResponse {
  catalog_version: number
  currency: string
  policy: {
    margin_floor_pct: number
    max_discount_pct: number
    cooldown_days: number
    max_offers_per_quarter: number
    approval_required_above_cost: number
  }
  offers: Offer[]
}

export type ActionKind = 'approve' | 'edit' | 'reject'

export interface ActionRequest {
  action: ActionKind
  actor: string
  reason_code: string | null
  modified_offer_id: string | null
  note: string | null
}

export interface ActionResponse {
  recommendation_id: string
  customer_id: string
  action: ActionKind
  actor: string
  acted_at: string
  audit_id: string
  status: 'recorded'
}

export interface ApiErrorBody {
  error: {
    code: 'VALIDATION_ERROR' | 'LEAKAGE_REJECTED' | string
    message: string
    fields?: { field: string; message: string; received?: unknown }[]
    request_id: string
  }
}
