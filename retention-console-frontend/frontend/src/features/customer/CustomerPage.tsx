import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Card } from '@/components/ui/Card'
import { RiskBadge } from '@/components/RiskBadge'
import { LeverChips } from '@/components/LeverChips'
import { EVBreakdown } from '@/components/EVBreakdown'
import { PolicyTrace } from '@/components/PolicyTrace'
import { NarrationPanel } from '@/components/NarrationPanel'
import { ActionBar } from './ActionBar'
import { ConfirmDialog } from './ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/Button'
import { useCustomer } from './useCustomer'
import { useAct } from './useAct'
import { months, usd } from '@/lib/format'
import type { ActionKind } from '@/types/api'

export interface CustomerPageProps {
  customerId?: string
}

export function CustomerPage({ customerId: initialCustomerId }: CustomerPageProps = {}) {
  const { id: paramId } = useParams()
  const id = initialCustomerId ?? paramId ?? '0295-PPHDO'
  const { data, isPending, error, refetch } = useCustomer(id)
  const act = useAct(id)
  const [pendingAction, setPendingAction] = useState<ActionKind | null>(null)
  const [selectedOfferId, setSelectedOfferId] = useState<string | null>(null)

  const activeCustomerId = data?.customer_id
  const recOfferId = data?.recommendation?.offer_id

  // Reset selectedOfferId whenever customer or recommendation changes
  useEffect(() => {
    if (recOfferId) {
      setSelectedOfferId(recOfferId)
    }
  }, [activeCustomerId, recOfferId])

  if (isPending) {
    return <Skeleton className="h-96 w-full" label="Loading customer" />
  }

  if (error) {
    return <ErrorState error={error} onRetry={() => void refetch()} />
  }

  const isControl = data.arm === 'control'
  const decision = data.decision
  const isActioned = !!decision
  const rec = data.recommendation
  const hasOffer = !!rec?.offer_id
  const hasAlternatives = (data.alternatives ?? []).length > 0

  return (
    <div className="space-y-4 pb-24">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-mono text-lg font-semibold">{data.customer_id}</h1>
          <p className="text-xs text-ink-3">
            {months(data.value.tenure_months)} · {usd(data.value.monthly_charges)}/mo ·{' '}
            {isControl ? 'CONTROL — do not contact' : 'treatment'}
          </p>
        </div>
        <RiskBadge band={data.risk.risk_band} p={data.risk.p_churn} />
      </div>

      {/* Decision Banner for Actioned Customers (High Contrast & Sharp Typography) */}
      {isActioned && (
        decision.action === 'reject' ? (
          <div className="rounded-xl border-2 border-amber-500 bg-amber-50/90 dark:bg-amber-950/40 p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-3">
                <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-600 text-white font-bold text-sm shadow-xs">✕</span>
                <div>
                  <h3 className="text-sm font-bold text-amber-950 dark:text-amber-200">
                    Rejected — Reason: <span className="font-mono font-semibold">{decision.reason_code ?? 'no reason'}</span>
                  </h3>
                  <p className="mt-0.5 text-xs text-amber-900/90 dark:text-amber-300/80">
                    Recorded on {new Date(decision.acted_at).toLocaleString()} by <span className="font-mono font-semibold">{decision.actor}</span>.
                    {decision.note && ` Note: "${decision.note}"`}
                  </p>
                </div>
              </div>
              <span className="rounded-md bg-amber-700 px-3 py-1 text-micro font-bold uppercase tracking-wider text-white shadow-xs">
                Decision Finalized
              </span>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border-2 border-emerald-600 bg-emerald-50/90 dark:bg-emerald-950/40 p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-3">
                <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-white font-bold text-sm shadow-xs">✓</span>
                <div>
                  <h3 className="text-sm font-bold text-emerald-950 dark:text-emerald-200">
                    Approved — Agreed Offer: {decision.offered_offer_name ?? rec?.offer_name ?? '—'}
                  </h3>
                  <p className="mt-0.5 text-xs text-emerald-900/90 dark:text-emerald-300/80">
                    Recorded on {new Date(decision.acted_at).toLocaleString()} by <span className="font-mono font-semibold">{decision.actor}</span>.
                    {decision.offer_changed && " (Agent customized from model recommendation)"}
                  </p>
                </div>
              </div>
              <span className="rounded-md bg-emerald-700 px-3 py-1 text-micro font-bold uppercase tracking-wider text-white shadow-xs">
                Decision Finalized
              </span>
            </div>
          </div>
        )
      )}

      {/* 2-Column Responsive Layout (2/1 split at lg) */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* Left Column (2 cols): Recommendation, Agent Note, Attribution */}
        <div className="space-y-4 lg:col-span-2">
          <Card
            title="Recommendation"
            subtitle={
              isControl
                ? rec?.offer_name
                  ? `${rec.offer_name} — withheld, control group`
                  : undefined
                : (rec?.offer_name ?? undefined)
            }
          >
            {rec?.offer_id ? (
              <>
                <EVBreakdown risk={data.risk} value={data.value} rec={rec} />
                {selectedOfferId && rec.offer_id && selectedOfferId !== rec.offer_id && !isActioned && (
                  <div className="mt-3 flex items-center justify-between border-t border-line-subtle pt-2">
                    <span className="text-xs text-ink-3">Viewing alternative offer in note</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setSelectedOfferId(rec.offer_id)}
                    >
                      Use recommended offer
                    </Button>
                  </div>
                )}
                {isControl && (
                  <p className="mt-3 text-xs text-ink-3 border-t border-line pt-2" role="note">
                    This customer is in the control group. This is what the model would recommend — it is not presented and no action is taken, so the outcome can be compared against customers who were contacted.
                  </p>
                )}
                {hasAlternatives && !isActioned && (
                  <div className="mt-4 space-y-2 border-t border-line pt-4">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-3">
                      Alternative Offers
                    </h3>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {data.alternatives.slice(0, 2).map((alt) => {
                        const isSelected = selectedOfferId === alt.offer_id
                        return (
                          <div
                            key={alt.offer_id}
                            className={`flex flex-col justify-between rounded-lg border p-3 text-xs transition-all ${
                              isSelected
                                ? 'border-accent bg-accent/10 shadow-sm'
                                : 'border-line bg-surface-2 hover:border-line-subtle'
                            }`}
                          >
                            <div className="space-y-1">
                              <div className="flex items-center justify-between">
                                <span className="font-medium text-ink">{alt.offer_name}</span>
                                <span className="num font-semibold text-emerald-600 dark:text-emerald-400">
                                  +{usd(alt.expected_value)}
                                </span>
                              </div>
                              <p className="text-micro text-ink-3">Cost: {usd(alt.cost)}</p>
                              {alt.talk_track && (
                                <p className="text-micro text-ink-3 italic border-l-2 border-line pl-2 mt-1">
                                  {alt.talk_track}
                                </p>
                              )}
                            </div>
                            <div className="mt-3 flex items-center justify-between pt-2 border-t border-line/40">
                              <Button
                                variant={isSelected ? 'secondary' : 'ghost'}
                                size="sm"
                                onClick={() => {
                                  setSelectedOfferId(alt.offer_id)
                                  setPendingAction('edit')
                                }}
                                className="w-full text-micro py-1"
                              >
                                {isSelected ? '✓ Selected' : 'Present This Instead'}
                              </Button>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="space-y-3">
                {data.status === 'no_action_needed' ? (
                  <div className="rounded-xl border-2 border-sky-500 bg-sky-50/90 dark:bg-sky-950/40 p-4 shadow-sm">
                    <h4 className="font-bold text-sky-950 dark:text-sky-200">Low Churn Risk — No Retention Action Needed</h4>
                    <p className="mt-1 text-xs text-sky-900/90 dark:text-sky-300/80">
                      This account has a calibrated churn probability of {(data.risk.p_churn * 100).toFixed(1)}%, which is below the intervention threshold (50%). Outreach is suppressed to preserve customer satisfaction and protect operating margins.
                    </p>
                  </div>
                ) : data.status === 'review_no_profitable_offer' ? (
                  <div className="rounded-xl border-2 border-amber-500 bg-amber-50/90 dark:bg-amber-950/40 p-4 shadow-sm">
                    <h4 className="font-bold text-amber-950 dark:text-amber-200">No Profitable Retention Offer Available</h4>
                    <p className="mt-1 text-xs text-amber-900/90 dark:text-amber-300/80">
                      While this customer exhibits elevated churn risk, the cost of all applicable catalog retention offers exceeds the expected customer lifetime value retained (EV &lt; $20). Intervening would yield a net economic loss.
                    </p>
                  </div>
                ) : data.status === 'review_no_applicable_offer' ? (
                  <div className="rounded-xl border-2 border-purple-500 bg-purple-50/90 dark:bg-purple-950/40 p-4 shadow-sm">
                    <h4 className="font-bold text-purple-950 dark:text-purple-200">No Applicable Retention Offer in Catalog</h4>
                    <p className="mt-1 text-xs text-purple-900/90 dark:text-purple-300/80">
                      The customer already subscribes to all available services and features in the active offer catalog. No eligible product upgrade or bundle applies.
                    </p>
                  </div>
                ) : null}
                <EmptyState
                  title="No qualifying offer"
                  body="No catalog offer matched this customer's levers at a positive expected value."
                />
              </div>
            )}
          </Card>

          <Card title="Agent note" subtitle="The only AI-generated text in this product">
            <NarrationPanel
              narration={data.narration}
              customerId={isControl || isActioned || !hasOffer ? undefined : data.customer_id}
              isControl={isControl}
              selectedOfferId={selectedOfferId}
              recommendedOfferId={rec?.offer_id ?? null}
              alternatives={data.alternatives}
            />
          </Card>

          <Card title="What drove the score" subtitle={data.attribution_disclaimer}>
            <ul className="space-y-1 text-sm">
              {data.attribution.map((a) => (
                <li key={a.feature} className="flex justify-between gap-4">
                  <span>{a.feature}</span>
                  <span className="num text-ink-2">
                    {a.direction === 'increases_risk' ? '+' : '−'}
                    {Math.abs(a.contribution).toLocaleString('en-US', {
                      minimumFractionDigits: 3,
                      maximumFractionDigits: 3,
                    })}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        {/* Right Column (1 col): Levers, Policy trace, Provenance */}
        <div className="space-y-4 lg:col-span-1">
          <Card title="Levers">
            <LeverChips levers={data.levers} max={99} />
          </Card>

          <Card title="Policy trace">
            <PolicyTrace rules={data.policy_trace} />
          </Card>

          <Card title="Provenance">
            <dl className="space-y-1 text-xs">
              <ProvenanceLine
                k="Model"
                v={`${data.provenance.model_name} ${data.provenance.model_version}`}
              />
              <ProvenanceLine k="Catalog" v={`v${data.provenance.catalog_version}`} />
              <ProvenanceLine k="Knowledge base" v={`v${data.provenance.kb_version}`} />
              <ProvenanceLine k="Evidence shown" v={`${data.evidence.count} documents`} />
            </dl>
          </Card>
        </div>
      </div>

      {/* Sticky Bottom Action Bar or Notice */}
      {isControl ? (
        <aside
          role="status"
          aria-label="Action status"
          className="fixed bottom-0 left-0 right-0 z-10 border-t border-line bg-surface/95 px-6 py-3 backdrop-blur"
        >
          <div className="mx-auto flex max-w-7xl items-center justify-between">
            <span className="text-sm text-ink-3 font-medium">
              No action available — control group.
            </span>
          </div>
        </aside>
      ) : isActioned ? (
        <aside
          role="status"
          aria-label="Action status"
          className="fixed bottom-0 left-0 right-0 z-10 border-t border-line bg-surface/95 px-6 py-3 backdrop-blur"
        >
          <div className="mx-auto flex max-w-7xl items-center justify-between">
            <span className="text-sm text-ink-3 font-medium">
              Decision logged in audit trail — no further action required.
            </span>
          </div>
        </aside>
      ) : data.actionable === false ? (
        <aside
          role="status"
          aria-label="Action status"
          className="fixed bottom-0 left-0 right-0 z-10 border-t border-line bg-surface/95 px-6 py-3 backdrop-blur"
        >
          <div className="mx-auto flex max-w-7xl items-center justify-between">
            <span className="text-sm text-ink-3 font-medium">
              Not in today&apos;s active queue yet
            </span>
          </div>
        </aside>
      ) : (
        <ActionBar
          hasOffer={hasOffer}
          hasAlternatives={hasAlternatives}
          onApprove={() => setPendingAction(selectedOfferId && rec?.offer_id && selectedOfferId !== rec.offer_id ? 'edit' : 'approve')}
          onEdit={() => setPendingAction('edit')}
          onReject={() => setPendingAction('reject')}
        />
      )}

      {/* Audit Confirmation Dialog */}
      {!isControl && !isActioned && data.actionable !== false && (
        <ConfirmDialog
          open={pendingAction !== null}
          onClose={() => setPendingAction(null)}
          customerId={data.customer_id}
          action={pendingAction}
          alternatives={data.alternatives}
          preselectedOfferId={selectedOfferId}
          loading={act.isPending}
          serverError={act.error}
          onSubmit={(payload) => {
            act.mutate(payload, {
              onSuccess: () => setPendingAction(null),
            })
          }}
        />
      )}
    </div>
  )
}

function ProvenanceLine({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-ink-3">{k}</dt>
      <dd className="num">{v}</dd>
    </div>
  )
}
