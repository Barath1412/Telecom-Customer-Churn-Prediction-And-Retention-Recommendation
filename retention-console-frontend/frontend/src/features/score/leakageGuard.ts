export const QUARANTINED_FIELDS = [
  'Churn Score',
  'Churn Reason',
  'Churn Label',
  'Churn Value',
  'CustomerID',
  'Count',
  'Country',
  'State',
  'City',
  'Zip Code',
  'Lat Long',
  'Latitude',
  'Longitude',
] as const

export class LeakageGuardError extends Error {
  constructor(readonly quarantinedKey: string) {
    super(`Leakage guard violation: quarantined field "${quarantinedKey}" detected in payload.`)
    this.name = 'LeakageGuardError'
  }
}

/**
 * Asserts that no quarantined leakage field is present in the payload.
 * Throws LeakageGuardError if any forbidden key is found.
 */
export function assertNoQuarantinedFields(payload: Record<string, unknown>): void {
  for (const key of Object.keys(payload)) {
    if ((QUARANTINED_FIELDS as readonly string[]).includes(key)) {
      throw new LeakageGuardError(key)
    }
  }
}
