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
  | 'review_no_profitable_offer'
  | 'review_no_applicable_offer'
  | 'no_action_needed'

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
  /** null when unsourced. Print "unsourced" explicitly in the provenance line. */
  delta_source: string | null
  expected_value: number
  requires_approval: boolean
}

export interface Alternative {
  offer_id: string
  offer_name: string
  cost: number
  delta_prior: number
  delta_ci: [number, number]
  expected_value: number
  talk_track?: string
}

export interface PolicyRuleBase {
  rule_id: string
  detail: string
}

export interface EvaluablePolicyRule extends PolicyRuleBase {
  state: 'pass' | 'veto'
  /** Absent when state is evaluable ('pass' | 'veto'). */
  unmet_requirement?: never
}

export interface NotEvaluablePolicyRule extends PolicyRuleBase {
  state: 'not_evaluable'
  /** Present only when state === 'not_evaluable'. What data feed is missing. */
  unmet_requirement: string
}

export type PolicyRule = EvaluablePolicyRule | NotEvaluablePolicyRule

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
  source: 'llm' | 'fallback_template' | 'example_fixture' | 'deterministic'
  model: string
  validator_attempts: number
  generated_at: string
}

export interface Provenance {
  model_name: string
  model_version: string
  model_roc_auc: number
  catalog_version: number
  kb_version: number
  scored_at: string
}

export type QueueStatusFilter =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'all_scored'
  | 'no_action_needed'
  | 'review_no_profitable_offer'
  | 'review_no_applicable_offer'

export interface QueueDecision {
  action: 'approve' | 'edit' | 'reject'
  actor: string
  reason_code: string | null
  note?: string | null
  acted_at: string
  offered_offer_id: string | null
  offered_offer_name: string | null
  offer_changed: boolean
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
  queue_position: number
  actionable: boolean
  /** Present only for status=approved / status=rejected items. */
  decision?: QueueDecision
}

export interface CustomerDetail extends QueueItem {
  queue_position: number
  actionable: boolean
  alternatives: Alternative[]
  vetoed: { offer_id: string; rule_id: string; detail: string }[]
  attribution: Attribution[]
  attribution_disclaimer: string
  evidence: { ids: string[]; count: number; approx_tokens: number }
  policy_trace: PolicyRule[]
  profile: Record<string, string | number>
  provenance: Provenance
  narration: Narration | null
}

/**
 * POST /api/customers/{id}/narrate — the live pipeline run.
 *
 * `decision` is returned so the claim "narration cannot change the recommendation"
 * is checkable from the client: it is computed before the model is called and the
 * graph raises if it moves afterwards.
 */
export interface NarrateResponse {
  customer_id: string
  narration: Narration
  decision: {
    status: QueueStatus
    offer_id: string | null
    offer_name: string | null
    cost: number | null
    expected_value: number | null
    p_churn: number
    levers: string[]
  }
  violations: string[]
  provider: string
  elapsed_ms: number
}

export interface UploadBatchResponse {
  status: string
  total_uploaded: number
  qualified_recommended: number
  new_queue_total: number
  new_pending_total: number
  promoted_to_active: string[]
}

export interface QueueResponse {
  run_id: string
  capacity: number
  total_scored?: number
  total_eligible: number
  pending_total: number
  approved_total: number
  rejected_total: number
  cohort_total?: number
  no_action_needed_total?: number
  no_profitable_total?: number
  no_applicable_total?: number
  status: QueueStatusFilter
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
    recommended: number
    review_no_profitable_offer: number
    review_no_applicable_offer: number
    no_action_needed: number
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
  note: string
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
    min_expected_value_usd: number
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

export type ScoreRequest = Record<string, string | number>

export interface ScoreResponse {
  p_churn: number
  risk_band: RiskBand
  levers: Lever[]
  recommendation: Recommendation
  policy_trace: PolicyRule[]
  provenance: Provenance
}

export type ApiErrorCode = 'VALIDATION_ERROR' | 'LEAKAGE_REJECTED' | string

export interface ApiErrorField {
  field: string
  message: string
  received?: unknown
}

export interface ApiErrorDetail {
  code: ApiErrorCode
  message: string
  fields?: ApiErrorField[]
  request_id: string
}

export interface ApiErrorBody {
  error: ApiErrorDetail
}

export interface LlmCallLog {
  call_id: string
  customer_id: string
  provider: string
  model: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  elapsed_ms: number
  passed_validators: string[]
  all_validators_passed: boolean
  cost_usd: number
  timestamp: string
}

export interface LlmTelemetryResponse {
  total_calls: number
  total_prompt_tokens: number
  total_completion_tokens: number
  total_tokens: number
  total_cost_usd: number
  avg_latency_ms: number
  validator_pass_rate: number
  model_distribution: Record<string, number>
  projections: {
    cost_per_call_usd: number
    daily_projected_cost_usd: number
    monthly_projected_cost_usd: number
    human_agent_labor_benchmark_per_call_usd: number
    cost_savings_multiplier: string
  }
  recent_calls: LlmCallLog[]
}
