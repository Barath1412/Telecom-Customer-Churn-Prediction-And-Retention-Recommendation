import {
  INTERNET_ADDONS,
  type InternetAddon,
  type ScoreFormData,
} from './fieldSpec'

/**
 * Pure function executing conditional rules across form transitions.
 *
 * Rule A: Internet Service === "No" forces all 6 add-ons to "No internet service".
 * Rule A Reverse: Internet Service transitioning from "No" to "DSL" | "Fiber optic"
 * unconditionally resets ALL 6 add-ons to "No".
 *
 * Rule B: Phone Service === "No" forces Multiple Lines to "No phone service".
 * Rule B Reverse: Phone Service transitioning from "No" to "Yes"
 * unconditionally resets Multiple Lines to "No".
 */
export function applyConditionalLogic<K extends keyof ScoreFormData>(
  prevState: ScoreFormData,
  changedField: K,
  nextValue: ScoreFormData[K],
): ScoreFormData {
  const nextState: ScoreFormData = {
    ...prevState,
    [changedField]: nextValue,
  }

  // Rule A & Rule A Reverse
  if (changedField === 'Internet Service') {
    if (nextValue === 'No') {
      for (const addon of INTERNET_ADDONS) {
        nextState[addon] = 'No internet service'
      }
    } else if (prevState['Internet Service'] === 'No') {
      // Reverse transition: Unconditionally reset all 6 add-ons to "No"
      for (const addon of INTERNET_ADDONS) {
        nextState[addon] = 'No'
      }
    }
  }

  // Rule B & Rule B Reverse
  if (changedField === 'Phone Service') {
    if (nextValue === 'No') {
      nextState['Multiple Lines'] = 'No phone service'
    } else if (prevState['Phone Service'] === 'No') {
      // Reverse transition: Unconditionally reset Multiple Lines to "No"
      nextState['Multiple Lines'] = 'No'
    }
  }

  // Rule C: Monthly Charges or Tenure Months changing recomputes Total Charges,
  // UNLESS the agent has manually edited Total Charges themselves (tracked by
  // the caller — see `totalChargesTouched` below). Total Charges stays
  // editable; this only supplies a sensible default, it does not lock the
  // field the way Rules A/B lock the internet add-ons.
  if (
    (changedField === 'Monthly Charges' || changedField === 'Tenure Months') &&
    !prevState.__totalChargesTouched
  ) {
    const monthly = Number(nextState['Monthly Charges']) || 0
    const tenure = Number(nextState['Tenure Months']) || 0
    nextState['Total Charges'] = Math.round(monthly * tenure * 100) / 100
  }

  if (changedField === 'Total Charges') {
    nextState.__totalChargesTouched = true
  }

  return nextState
}

/**
 * Computes disabled state and helper text for fields governed by conditional rules.
 */
export function getFieldControlState(
  formState: ScoreFormData,
  fieldName: keyof ScoreFormData,
): { disabled: boolean; helperText?: string } {
  if (INTERNET_ADDONS.includes(fieldName as InternetAddon)) {
    if (formState['Internet Service'] === 'No') {
      return {
        disabled: true,
        helperText: 'Not applicable — no internet service on this account',
      }
    }
  }

  if (fieldName === 'Multiple Lines') {
    if (formState['Phone Service'] === 'No') {
      return {
        disabled: true,
        helperText: 'Not applicable — no phone service on this account',
      }
    }
  }

  return { disabled: false }
}