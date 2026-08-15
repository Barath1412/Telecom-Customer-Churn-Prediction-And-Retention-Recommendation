import type { ScoreFormData } from './fieldSpec'

/**
 * Initial defaults sourced directly from POST_score.json fixture's request_example.
 */
export const INITIAL_SCORE_FORM: ScoreFormData = {
  Gender: 'Male',
  'Senior Citizen': 'No',
  Partner: 'No',
  Dependents: 'No',
  'Phone Service': 'Yes',
  'Multiple Lines': 'Yes',
  'Internet Service': 'Fiber optic',
  'Online Security': 'No',
  'Online Backup': 'No',
  'Device Protection': 'No',
  'Tech Support': 'No',
  'Streaming TV': 'Yes',
  'Streaming Movies': 'Yes',
  'Paperless Billing': 'Yes',
  'Payment Method': 'Electronic check',
  Contract: 'Month-to-month',
  'Tenure Months': 1,
  'Monthly Charges': 95.45,
  'Total Charges': 95.45,
  cltv: 5962.0,
}
