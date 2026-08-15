export interface ScoreFormData {
  Gender: 'Female' | 'Male'
  'Senior Citizen': 'No' | 'Yes'
  Partner: 'No' | 'Yes'
  Dependents: 'No' | 'Yes'
  'Phone Service': 'No' | 'Yes'
  'Multiple Lines': 'No' | 'Yes' | 'No phone service'
  'Internet Service': 'DSL' | 'Fiber optic' | 'No'
  'Online Security': 'No' | 'Yes' | 'No internet service'
  'Online Backup': 'No' | 'Yes' | 'No internet service'
  'Device Protection': 'No' | 'Yes' | 'No internet service'
  'Tech Support': 'No' | 'Yes' | 'No internet service'
  'Streaming TV': 'No' | 'Yes' | 'No internet service'
  'Streaming Movies': 'No' | 'Yes' | 'No internet service'
  'Paperless Billing': 'No' | 'Yes'
  'Payment Method':
    | 'Bank transfer (automatic)'
    | 'Credit card (automatic)'
    | 'Electronic check'
    | 'Mailed check'
  Contract: 'Month-to-month' | 'One year' | 'Two year'
  'Tenure Months': number
  'Monthly Charges': number
  'Total Charges': number
  cltv: number
}

export const INTERNET_ADDONS = [
  'Online Security',
  'Online Backup',
  'Device Protection',
  'Tech Support',
  'Streaming TV',
  'Streaming Movies',
] as const

export type InternetAddon = (typeof INTERNET_ADDONS)[number]

export const GENDER_OPTIONS = [
  { value: 'Female', label: 'Female' },
  { value: 'Male', label: 'Male' },
]

export const TOGGLE_OPTIONS = [
  { value: 'No', label: 'No' },
  { value: 'Yes', label: 'Yes' },
]

export const MULTIPLE_LINES_OPTIONS = [
  { value: 'No', label: 'No' },
  { value: 'Yes', label: 'Yes' },
  { value: 'No phone service', label: 'No phone service' },
]

export const INTERNET_SERVICE_OPTIONS = [
  { value: 'DSL', label: 'DSL' },
  { value: 'Fiber optic', label: 'Fiber optic' },
  { value: 'No', label: 'No' },
]

export const ADDON_OPTIONS = [
  { value: 'No', label: 'No' },
  { value: 'Yes', label: 'Yes' },
  { value: 'No internet service', label: 'No internet service' },
]

export const PAYMENT_METHOD_OPTIONS = [
  { value: 'Bank transfer (automatic)', label: 'Bank transfer (automatic)' },
  { value: 'Credit card (automatic)', label: 'Credit card (automatic)' },
  { value: 'Electronic check', label: 'Electronic check' },
  { value: 'Mailed check', label: 'Mailed check' },
]

export const CONTRACT_OPTIONS: Array<ScoreFormData['Contract']> = [
  'Month-to-month',
  'One year',
  'Two year',
]
