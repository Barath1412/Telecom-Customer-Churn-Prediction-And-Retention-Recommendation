import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { SelectField, TextField } from '@/components/ui/Field'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState, ErrorState } from '@/components/States'
import { RiskBadge } from '@/components/RiskBadge'
import { LeverChips } from '@/components/LeverChips'
import { EVBreakdown } from '@/components/EVBreakdown'
import { PolicyTrace } from '@/components/PolicyTrace'
import { NarrationPanel } from '@/components/NarrationPanel'
import { months, usd } from '@/lib/format'
import { useAct, useCustomer } from './useCustomer'
import type { ActionKind } from '@/types/api'

const ACTION_LABEL: Record<ActionKind, string> = {
  approve: 'Approve recommendation',
  edit: 'Change the offer',
  reject: 'Reject recommendation',
}

const REASONS = [
  { value: 'already_contacted', label: 'Already contacted' },
  { value: 'offer_not_suitable', label: 'Offer not suitable' },
  { value: 'customer_unreachable', label: 'Customer unreachable' },
  { value: 'account_closing', label: 'Account closing' },
  { value: 'data_looks_wrong', label: 'Data looks wrong' },
  { value: 'other', label: 'Other' },
]

export function CustomerPage() {
  const { id = '' } = useParams()
  const { data, isPending, error, refetch } = useCustomer(id)
  const act = useAct(id)
  const [pending, setPending] = useState<ActionKind | null>(null)
  const [reason, setReason] = useState(REASONS[0]!.value)
  const [note, setNote] = useState('')
  const [touched, setTouched] = useState(false)

  if (isPending) return <Skeleton className="h-96 w-full" />
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />

  const rec = data.recommendation
  const noteRequired = pending === 'reject' && reason === 'other'
  const noteError = touched && noteRequired && note.trim().length < 5 ? 'Add a short note.' : undefined

  const submit = () => {
    setTouched(true)
    if (noteError || !pending) return
    act.mutate(
      {
        action: pending,
        actor: 'agent_42',
        reason_code: pending === 'reject' ? reason : null,
        modified_offer_id: null,
        note: note.trim() || null,
      },
      { onSuccess: () => setPending(null) },
    )
  }

  return (
    <div className="space-y-4 pb-24">
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

      <div className="grid gap-4 lg:grid-cols-3">
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

        <div className="space-y-4">
          <Card title="Levers">
            <LeverChips levers={data.levers} max={99} />
          </Card>
          <Card title="Policy trace">
            <PolicyTrace rules={data.policy_trace} />
          </Card>
          <Card title="Provenance">
            <dl className="space-y-1 text-xs">
              <Line k="Model" v={`${data.provenance.model_name} ${data.provenance.model_version}`} />
              <Line k="Catalog" v={`v${data.provenance.catalog_version}`} />
              <Line k="Knowledge base" v={`v${data.provenance.kb_version}`} />
              <Line k="Evidence shown" v={`${data.evidence.count} documents`} />
            </dl>
          </Card>
        </div>
      </div>

      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface">
        <div className="mx-auto flex max-w-[1400px] flex-wrap gap-2 px-4 py-3">
        <Button variant="primary" onClick={() => setPending('approve')} disabled={!rec.offer_id}>
          Approve
        </Button>
        <Button onClick={() => setPending('edit')} disabled={!rec.offer_id}>
          Edit offer
        </Button>
        <Button variant="danger" onClick={() => setPending('reject')}>
          Reject
        </Button>
          {!rec.offer_id && (
            <p className="self-center text-xs text-ink-3">
              Approve is unavailable because no offer qualified.
            </p>
          )}
        </div>
      </div>

      <Modal
        open={pending !== null}
        onClose={() => setPending(null)}
        title={pending ? ACTION_LABEL[pending] : ''}
        description={`This writes an audit record against ${data.customer_id}. It cannot be undone.`}
        footer={
          <>
            <Button onClick={() => setPending(null)}>Cancel</Button>
            <Button variant="primary" loading={act.isPending} onClick={submit}>
              Confirm
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {pending === 'reject' && (
            <SelectField
              label="Reason"
              options={REASONS}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required
            />
          )}
          <TextField
            label="Note"
            hint="Stored in the audit log."
            required={noteRequired}
            error={noteError}
            value={note}
            onBlur={() => setTouched(true)}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
      </Modal>
    </div>
  )
}

function Line({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-ink-3">{k}</dt>
      <dd className="num">{v}</dd>
    </div>
  )
}
