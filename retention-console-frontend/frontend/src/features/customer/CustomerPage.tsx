import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { RiskBadge } from '@/components/RiskBadge'
import { LeverChips } from '@/components/LeverChips'
import { EVBreakdown } from '@/components/EVBreakdown'
import { PolicyTrace } from '@/components/PolicyTrace'
import { NarrationPanel } from '@/components/NarrationPanel'
import { months, usd } from '@/lib/format'
import { useCustomer } from './useCustomer'
import { useAct } from './useAct'
import { ActionBar } from './ActionBar'
import { ConfirmDialog } from './ConfirmDialog'
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
  const rec = data.recommendation
  const hasOffer = !!rec.offer_id
  const hasAlternatives = data.alternatives.length > 0

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

      {/* 2-Column Responsive Layout (2/1 split at lg) */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* Left Column (2 cols): Recommendation, Agent Note, Attribution */}
        <div className="space-y-4 lg:col-span-2">
          <Card
            title="Recommendation"
            subtitle={
              isControl
                ? rec.offer_name
                  ? `${rec.offer_name} — withheld, control group`
                  : undefined
                : (rec.offer_name ?? undefined)
            }
          >
            {rec.offer_id ? (
              <>
                <EVBreakdown risk={data.risk} value={data.value} rec={rec} />
                {selectedOfferId && rec.offer_id && selectedOfferId !== rec.offer_id && (
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
                {hasAlternatives && (
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
                            className={`rounded border p-3 space-y-2 text-xs transition-colors ${
                              isSelected
                                ? 'border-accent bg-surface-alt shadow-sm'
                                : 'border-line bg-surface-alt'
                            }`}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-medium text-ink">{alt.offer_name}</span>
                              <span
                                className={`rounded px-1.5 py-0.5 font-mono text-micro border ${
                                  isSelected
                                    ? 'bg-accent/10 border-accent text-accent font-semibold'
                                    : 'bg-surface border-line text-ink-2'
                                }`}
                              >
                                {isSelected ? 'Selected' : 'Alternative'}
                              </span>
                            </div>
                            <div className="flex gap-4 text-ink-2">
                              <span>Cost: <strong className="text-ink">{usd(alt.cost)}</strong></span>
                              <span>EV: <strong className="text-ink">{usd(alt.expected_value)}</strong></span>
                            </div>
                            {alt.talk_track && (
                              <p className="text-ink-3 italic border-l-2 border-line-strong pl-2 text-micro">
                                {alt.talk_track}
                              </p>
                            )}
                            {!isControl && (
                              <div className="pt-1">
                                <Button
                                  variant="secondary"
                                  size="sm"
                                  onClick={() => {
                                    setSelectedOfferId(alt.offer_id)
                                    setPendingAction('edit')
                                  }}
                                >
                                  Present this instead
                                </Button>
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <EmptyState
                title="No qualifying offer"
                body="No catalog offer matched this customer's levers at a positive expected value."
              />
            )}
          </Card>

          <Card title="Agent note" subtitle="The only AI-generated text in this product">
            <NarrationPanel
              narration={data.narration}
              customerId={isControl ? undefined : data.customer_id}
              isControl={isControl}
              selectedOfferId={selectedOfferId}
              recommendedOfferId={rec.offer_id}
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
          onApprove={() => setPendingAction('approve')}
          onEdit={() => setPendingAction('edit')}
          onReject={() => setPendingAction('reject')}
        />
      )}

      {/* Audit Confirmation Dialog */}
      {!isControl && data.actionable !== false && (
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
