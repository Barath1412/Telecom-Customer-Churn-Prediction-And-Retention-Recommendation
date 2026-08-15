import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api, ApiError } from '@/lib/api'
import { ScoreForm } from './ScoreForm'
import { assertNoQuarantinedFields, LeakageGuardError } from './leakageGuard'
import type { ScoreFormData } from './fieldSpec'
import type { ScoreResponse } from '@/types/api'
import { Card } from '@/components/ui/Card'
import { RiskBadge } from '@/components/RiskBadge'
import { LeverChips } from '@/components/LeverChips'
import { EmptyState } from '@/components/EmptyState'
import { Skeleton } from '@/components/ui/Skeleton'
import { usd, deltaWithRange } from '@/lib/format'

export function ScorePage() {
  const [serverFieldErrors, setServerFieldErrors] = useState<Record<string, string>>({})
  const [generalError, setGeneralError] = useState<string | null>(null)

  const mutation = useMutation<ScoreResponse, Error, ScoreFormData>({
    mutationFn: async (formData) => {
      setServerFieldErrors({})
      setGeneralError(null)

      const payload: Record<string, string | number> = { ...formData }
      assertNoQuarantinedFields(payload)

      return api.score(payload)
    },
    onError: (err) => {
      if (err instanceof LeakageGuardError) {
        setGeneralError('Internal error: request blocked by data leakage guard.')
        return
      }

      if (err instanceof ApiError) {
        if (err.status === 400 && err.fields.length > 0) {
          const fieldMap: Record<string, string> = {}
          for (const f of err.fields) {
            fieldMap[f.field] = f.message
          }
          setServerFieldErrors(fieldMap)
          return
        }

        if (err.status === 503 || err.code === 'MODEL_UNAVAILABLE') {
          setGeneralError('Model service is temporarily unavailable. Please retry in a moment.')
          return
        }

        setGeneralError(err.message || 'Scoring request failed.')
        return
      }

      setGeneralError(err.message || 'An unexpected error occurred.')
    },
  })

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-bold tracking-tight text-ink">Manual scoring</h1>
        <p className="mt-1 text-sm text-ink-3">
          Evaluate retention risk, driving levers, and recommended offers for ad-hoc customer profiles.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
        {/* Left Column: Form (7 cols) */}
        <div className="lg:col-span-7">
          <ScoreForm
            onSubmit={(data) => {
              mutation.mutate(data)
            }}
            isSubmitting={mutation.isPending}
            serverFieldErrors={serverFieldErrors}
          />
        </div>

        {/* Right Column: Results (5 cols) */}
        <div className="space-y-6 lg:col-span-5">
          {generalError && (
            <div role="alert" className="rounded-lg border border-danger/40 bg-surface p-4 text-sm text-danger">
              <p className="font-semibold">Unable to calculate score</p>
              <p className="mt-1 text-xs text-ink-2">{generalError}</p>
            </div>
          )}

          {mutation.isPending && (
            <Card title="Evaluating customer profile..." subtitle="Calculating churn risk and qualifying offers">
              <div className="space-y-4">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-24 w-full" />
                <Skeleton className="h-32 w-full" />
              </div>
            </Card>
          )}

          {!mutation.isPending && !mutation.data && (
            <EmptyState
              title="No score calculated"
              body="Fill in the customer attributes on the left and select Calculate score to evaluate retention risk and recommendations."
            />
          )}

          {!mutation.isPending && mutation.data && (
            <div className="space-y-6">
              {/* Risk Assessment Card */}
              <Card title="Risk assessment" subtitle="Predicted churn probability and risk tier">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-xs text-ink-3">Risk classification</span>
                    <div className="mt-1">
                      <RiskBadge band={mutation.data.risk_band} p={mutation.data.p_churn} />
                    </div>
                  </div>
                </div>
              </Card>

              {/* Driving Levers Card */}
              <Card title="Driving levers" subtitle="Behaviors and contract terms contributing to retention risk">
                {mutation.data.levers.length > 0 ? (
                  <LeverChips levers={mutation.data.levers} max={99} />
                ) : (
                  <p className="text-xs text-ink-3">No risk levers identified for this profile.</p>
                )}
              </Card>

              {/* Recommendation Card */}
              <Card
                title="Recommended offer"
                subtitle="Optimal retention intervention approved by the policy engine"
              >
                {mutation.data.recommendation.offer_id ? (
                  <div className="space-y-4">
                    <div>
                      <h3 className="text-sm font-semibold text-ink">
                        {mutation.data.recommendation.offer_name}
                      </h3>
                      <p className="text-micro font-mono text-ink-3">
                        {mutation.data.recommendation.offer_id}
                      </p>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div className="rounded border border-line bg-canvas p-3">
                        <span className="text-micro text-ink-3">Expected value</span>
                        <p className="num text-base font-semibold text-ink">
                          {usd(mutation.data.recommendation.expected_value)}
                        </p>
                      </div>
                      <div className="rounded border border-line bg-canvas p-3">
                        <span className="text-micro text-ink-3">Offer cost</span>
                        <p className="num text-base font-semibold text-ink">
                          {usd(mutation.data.recommendation.cost)}
                        </p>
                      </div>
                    </div>

                    <div className="rounded border border-line bg-canvas p-3">
                      <span className="text-micro text-ink-3">Assumed retention uplift</span>
                      <p className="text-xs font-medium text-ink">
                        {deltaWithRange(
                          mutation.data.recommendation.delta_prior,
                          mutation.data.recommendation.delta_ci,
                        )}
                      </p>
                      {mutation.data.recommendation.delta_source && (
                        <p className="mt-1 text-micro text-ink-3">
                          {`Source: ${mutation.data.recommendation.delta_source}`}
                        </p>
                      )}
                    </div>
                  </div>
                ) : (
                  <EmptyState
                    title="No qualifying offer"
                    body="No retention offer in the catalog met margin and policy eligibility criteria for this profile."
                  />
                )}
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
