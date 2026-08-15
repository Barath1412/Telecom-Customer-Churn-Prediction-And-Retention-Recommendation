import { useId, useState, type FormEvent } from 'react'
import {
  ADDON_OPTIONS,
  CONTRACT_OPTIONS,
  GENDER_OPTIONS,
  INTERNET_ADDONS,
  INTERNET_SERVICE_OPTIONS,
  MULTIPLE_LINES_OPTIONS,
  PAYMENT_METHOD_OPTIONS,
  TOGGLE_OPTIONS,
  type ScoreFormData,
} from './fieldSpec'
import { INITIAL_SCORE_FORM } from './defaults'
import { applyConditionalLogic, getFieldControlState } from './conditionalLogic'
import { Card } from '@/components/ui/Card'
import { TextField } from '@/components/ui/TextField'
import { SelectField } from '@/components/ui/SelectField'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/cn'

export interface ScoreFormProps {
  onSubmit: (data: ScoreFormData) => void
  isSubmitting: boolean
  serverFieldErrors?: Record<string, string>
}

type FieldErrors = Partial<Record<keyof ScoreFormData, string>>
type TouchedFields = Partial<Record<keyof ScoreFormData, boolean>>

export function ScoreForm({ onSubmit, isSubmitting, serverFieldErrors = {} }: ScoreFormProps) {
  const [formState, setFormState] = useState<ScoreFormData>(INITIAL_SCORE_FORM)
  const [clientErrors, setClientErrors] = useState<FieldErrors>({})
  const [touched, setTouched] = useState<TouchedFields>({})
  const contractLabelId = useId()

  const combinedErrors: Record<string, string | undefined> = {
    ...clientErrors,
    ...serverFieldErrors,
  }

  function validateField<K extends keyof ScoreFormData>(
    field: K,
    value: ScoreFormData[K],
  ): string | undefined {
    if (field === 'Tenure Months') {
      const n = Number(value)
      if (isNaN(n) || value === undefined || value === null || String(value).trim() === '') {
        return 'Tenure is required'
      }
      if (!Number.isInteger(n)) {
        return 'Tenure must be a whole number of months'
      }
      if (n < 0 || n > 72) {
        return 'Tenure must be between 0 and 72 months'
      }
    }

    if (field === 'Monthly Charges') {
      const n = Number(value)
      if (isNaN(n) || value === undefined || value === null || String(value).trim() === '') {
        return 'Monthly charges are required'
      }
      if (n < 18.25 || n > 118.75) {
        return 'Monthly charges must be between $18.25 and $118.75'
      }
    }

    if (field === 'Total Charges') {
      const n = Number(value)
      if (isNaN(n) || value === undefined || value === null || String(value).trim() === '') {
        return 'Total charges are required'
      }
      if (n < 0) {
        return 'Total charges must be greater than or equal to 0'
      }
    }

    if (field === 'cltv') {
      const n = Number(value)
      if (isNaN(n) || value === undefined || value === null || String(value).trim() === '') {
        return 'CLTV is required'
      }
      if (n < 2003 || n > 6500) {
        return 'CLTV must be between 2003 and 6500'
      }
    }

    return undefined
  }

  function validateAll(): boolean {
    const nextErrors: FieldErrors = {}
    for (const key of Object.keys(formState) as Array<keyof ScoreFormData>) {
      const err = validateField(key, formState[key])
      if (err) {
        nextErrors[key] = err
      }
    }
    setClientErrors(nextErrors)
    return Object.keys(nextErrors).length === 0
  }

  function handleBlur<K extends keyof ScoreFormData>(field: K) {
    setTouched((prev) => ({ ...prev, [field]: true }))
    const error = validateField(field, formState[field])
    setClientErrors((prev) => ({ ...prev, [field]: error }))
  }

  function handleChange<K extends keyof ScoreFormData>(field: K, nextValue: ScoreFormData[K]) {
    const nextState = applyConditionalLogic(formState, field, nextValue)
    setFormState(nextState)

    if (touched[field]) {
      const error = validateField(field, nextValue)
      setClientErrors((prev) => ({ ...prev, [field]: error }))
    }
  }

  function handleReset() {
    setFormState(INITIAL_SCORE_FORM)
    setClientErrors({})
    setTouched({})
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    // Mark all as touched
    const allTouched: TouchedFields = {}
    for (const key of Object.keys(formState) as Array<keyof ScoreFormData>) {
      allTouched[key] = true
    }
    setTouched(allTouched)

    if (!validateAll()) {
      return
    }

    onSubmit(formState)
  }

  // Non-blocking Total Charges consistency check
  const expectedProduct = formState['Tenure Months'] * formState['Monthly Charges']
  const showTotalChargesWarning =
    expectedProduct > 0 &&
    formState['Total Charges'] >= 0 &&
    Math.abs(formState['Total Charges'] - expectedProduct) > 0.2 * expectedProduct

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-6">
      {/* Section 1: Account */}
      <Card title="Account" subtitle="Customer identity, household, and contract terms">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <SelectField
            label="Gender"
            options={GENDER_OPTIONS}
            value={formState.Gender}
            onChange={(e) =>
              handleChange('Gender', e.target.value as ScoreFormData['Gender'])
            }
            onBlur={() => handleBlur('Gender')}
            error={combinedErrors['Gender']}
          />

          <SelectField
            label="Senior Citizen"
            options={TOGGLE_OPTIONS}
            value={formState['Senior Citizen']}
            onChange={(e) =>
              handleChange(
                'Senior Citizen',
                e.target.value as ScoreFormData['Senior Citizen'],
              )
            }
            onBlur={() => handleBlur('Senior Citizen')}
            error={combinedErrors['Senior Citizen']}
          />

          <SelectField
            label="Partner"
            options={TOGGLE_OPTIONS}
            value={formState.Partner}
            onChange={(e) =>
              handleChange('Partner', e.target.value as ScoreFormData['Partner'])
            }
            onBlur={() => handleBlur('Partner')}
            error={combinedErrors['Partner']}
          />

          <SelectField
            label="Dependents"
            options={TOGGLE_OPTIONS}
            value={formState.Dependents}
            onChange={(e) =>
              handleChange('Dependents', e.target.value as ScoreFormData['Dependents'])
            }
            onBlur={() => handleBlur('Dependents')}
            error={combinedErrors['Dependents']}
          />

          <TextField
            label="Tenure Months"
            type="number"
            min={0}
            max={72}
            step={1}
            value={formState['Tenure Months']}
            onChange={(e) =>
              handleChange(
                'Tenure Months',
                e.target.value === '' ? ('' as unknown as number) : Number(e.target.value),
              )
            }
            onBlur={() => handleBlur('Tenure Months')}
            hint="Customer tenure in whole months (0–72)"
            error={combinedErrors['Tenure Months']}
          />

          {/* Contract Segmented Control */}
          <div
            role="radiogroup"
            aria-labelledby={contractLabelId}
            className="space-y-1 sm:col-span-2"
          >
            <span id={contractLabelId} className="block text-xs font-medium text-ink-2">
              Contract
            </span>
            <div className="grid grid-cols-3 gap-1 rounded-lg border border-line-strong bg-surface p-1">
              {CONTRACT_OPTIONS.map((opt) => {
                const isChecked = formState.Contract === opt
                return (
                  <label
                    key={opt}
                    className={cn(
                      'flex cursor-pointer items-center justify-center rounded px-3 py-1.5 text-xs font-medium transition-colors text-center',
                      isChecked
                        ? 'bg-raised font-semibold text-ink shadow-sm'
                        : 'text-ink-2 hover:bg-raised',
                    )}
                  >
                    <input
                      type="radio"
                      name="Contract"
                      value={opt}
                      checked={isChecked}
                      onChange={() => handleChange('Contract', opt)}
                      className="sr-only"
                    />
                    {opt}
                  </label>
                )
              })}
            </div>
            {combinedErrors['Contract'] && (
              <p role="alert" className="text-micro text-danger">
                {combinedErrors['Contract']}
              </p>
            )}
          </div>
        </div>
      </Card>

      {/* Section 2: Services */}
      <Card title="Services" subtitle="Phone lines, internet access, and active add-ons">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <SelectField
            label="Phone Service"
            options={TOGGLE_OPTIONS}
            value={formState['Phone Service']}
            onChange={(e) =>
              handleChange(
                'Phone Service',
                e.target.value as ScoreFormData['Phone Service'],
              )
            }
            onBlur={() => handleBlur('Phone Service')}
            error={combinedErrors['Phone Service']}
          />

          {(() => {
            const ctrl = getFieldControlState(formState, 'Multiple Lines')
            return (
              <SelectField
                label="Multiple Lines"
                options={MULTIPLE_LINES_OPTIONS}
                value={formState['Multiple Lines']}
                disabled={ctrl.disabled}
                hint={ctrl.helperText}
                onChange={(e) =>
                  handleChange(
                    'Multiple Lines',
                    e.target.value as ScoreFormData['Multiple Lines'],
                  )
                }
                onBlur={() => handleBlur('Multiple Lines')}
                error={combinedErrors['Multiple Lines']}
              />
            )
          })()}

          <div className="sm:col-span-2">
            <SelectField
              label="Internet Service"
              options={INTERNET_SERVICE_OPTIONS}
              value={formState['Internet Service']}
              onChange={(e) =>
                handleChange(
                  'Internet Service',
                  e.target.value as ScoreFormData['Internet Service'],
                )
              }
              onBlur={() => handleBlur('Internet Service')}
              error={combinedErrors['Internet Service']}
            />
          </div>

          {INTERNET_ADDONS.map((addon) => {
            const ctrl = getFieldControlState(formState, addon)
            return (
              <SelectField
                key={addon}
                label={addon}
                options={ADDON_OPTIONS}
                value={formState[addon]}
                disabled={ctrl.disabled}
                hint={ctrl.helperText}
                onChange={(e) =>
                  handleChange(
                    addon,
                    e.target.value as ScoreFormData[typeof addon],
                  )
                }
                onBlur={() => handleBlur(addon)}
                error={combinedErrors[addon]}
              />
            )
          })}
        </div>
      </Card>

      {/* Section 3: Billing */}
      <Card title="Billing" subtitle="Payment preferences, recurring charges, and customer valuation">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <SelectField
            label="Paperless Billing"
            options={TOGGLE_OPTIONS}
            value={formState['Paperless Billing']}
            onChange={(e) =>
              handleChange(
                'Paperless Billing',
                e.target.value as ScoreFormData['Paperless Billing'],
              )
            }
            onBlur={() => handleBlur('Paperless Billing')}
            error={combinedErrors['Paperless Billing']}
          />

          <SelectField
            label="Payment Method"
            options={PAYMENT_METHOD_OPTIONS}
            value={formState['Payment Method']}
            onChange={(e) =>
              handleChange(
                'Payment Method',
                e.target.value as ScoreFormData['Payment Method'],
              )
            }
            onBlur={() => handleBlur('Payment Method')}
            error={combinedErrors['Payment Method']}
          />

          <TextField
            label="Monthly Charges"
            type="number"
            min={18.25}
            max={118.75}
            step={0.01}
            value={formState['Monthly Charges']}
            onChange={(e) =>
              handleChange(
                'Monthly Charges',
                e.target.value === '' ? ('' as unknown as number) : Number(e.target.value),
              )
            }
            onBlur={() => handleBlur('Monthly Charges')}
            hint="Observed range: $18.25–$118.75"
            error={combinedErrors['Monthly Charges']}
          />

          <div className="space-y-1">
            <TextField
              label="Total Charges"
              type="number"
              min={0}
              step={0.01}
              value={formState['Total Charges']}
              onChange={(e) =>
                handleChange(
                  'Total Charges',
                  e.target.value === '' ? ('' as unknown as number) : Number(e.target.value),
                )
              }
              onBlur={() => handleBlur('Total Charges')}
              hint="Cumulative historical charges (>= $0.00)"
              error={combinedErrors['Total Charges']}
            />
            {showTotalChargesWarning && !combinedErrors['Total Charges'] && (
              <p className="text-micro text-ink-3">
                This doesn&apos;t match tenure x monthly charges. Check the value before scoring.
              </p>
            )}
          </div>

          <div className="sm:col-span-2">
            <TextField
              label="Customer Lifetime Value (CLTV)"
              type="number"
              min={2003}
              max={6500}
              step={1}
              value={formState.cltv}
              onChange={(e) =>
                handleChange(
                  'cltv',
                  e.target.value === '' ? ('' as unknown as number) : Number(e.target.value),
                )
              }
              onBlur={() => handleBlur('cltv')}
              hint="Business valuation metric (2003–6500) used for expected value calculation — does not affect churn prediction model score"
              error={combinedErrors['cltv']}
            />
          </div>
        </div>
      </Card>

      {/* Action buttons */}
      <div className="flex items-center gap-3">
        <Button
          type="submit"
          variant="primary"
          loading={isSubmitting}
        >
          Calculate score
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={isSubmitting}
          onClick={handleReset}
        >
          Reset defaults
        </Button>
      </div>
    </form>
  )
}
