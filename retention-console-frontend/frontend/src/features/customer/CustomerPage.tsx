import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Card } from '@/components/ui/Card'
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

export function CustomerPage({ customerId }: CustomerPageProps = {}) {
  const { id: paramId } = useParams()
  const id = customerId ?? paramId ?? '0295-PPHDO'
  const { data, isPending, error, refetch } = useCustomer(id)
  const act = useAct(id)
  const [pendingAction, setPendingAction] = useState<ActionKind | null>(null)

  if (isPending) {
    return <Skeleton className="h-96 w-full" label="Loading customer" />
  }

  if (error) {
    return <ErrorState error={error} onRetry={() => void refetch()} />
  }

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
            {data.arm === 'control' ? 'CONTROL — do not contact' : 'treatment'}
          </p>
        </div>
        <RiskBadge band={data.risk.risk_band} p={data.risk.p_churn} />
      </div>

      {/* 2-Column Responsive Layout (2/1 split at lg) */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* Left Column (2 cols): Recommendation, Agent Note, Attribution */}
        <div className="space-y-4 lg:col-span-2">
          <Card title="Recommendation" subtitle={rec.offer_name ?? undefined}>
            {rec.offer_id ? (
              <EVBreakdown risk={data.risk} value={data.value} rec={rec} />
            ) : (
              <EmptyState
                title="No qualifying offer"
                body="No catalog offer matched this customer's levers at a positive expected value."
              />
            )}
          </Card>

          <Card title="Agent note" subtitle="The only AI-generated text in this product">
            <NarrationPanel narration={data.narration} />
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

      {/* Sticky Bottom Action Bar */}
      <ActionBar
        hasOffer={hasOffer}
        hasAlternatives={hasAlternatives}
        onApprove={() => setPendingAction('approve')}
        onEdit={() => setPendingAction('edit')}
        onReject={() => setPendingAction('reject')}
      />

      {/* Audit Confirmation Dialog */}
      <ConfirmDialog
        open={pendingAction !== null}
        onClose={() => setPendingAction(null)}
        customerId={data.customer_id}
        action={pendingAction}
        alternatives={data.alternatives}
        loading={act.isPending}
        serverError={act.error}
        onSubmit={(payload) => {
          act.mutate(payload, {
            onSuccess: () => setPendingAction(null),
          })
        }}
      />
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
