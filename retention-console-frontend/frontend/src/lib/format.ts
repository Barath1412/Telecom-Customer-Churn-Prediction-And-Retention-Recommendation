/**
 * The only place a number becomes a string.
 *
 * Why a module and not toFixed() at the call site: this screen shows money that
 * a human then says out loud to a customer. "$120.5" and "$120.50" are the same
 * number and different sentences. ESLint forbids Number.prototype.toFixed
 * outside this file.
 */

const money2 = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

/** Costs and expected values an agent may quote. Always two decimals. */
export const usd = (n: number): string => money2.format(n)

/** Probabilities. One decimal — the model is not precise enough for two. */
export const pct = (p: number, digits = 1): string =>
  `${(p * 100).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}%`

/**
 * A Δ is never shown alone. This returns the assumption AND its range in one
 * string so a component physically cannot render half of it.
 */
export const deltaWithRange = (prior: number, ci: [number, number]): string =>
  `${pct(prior, 0)} assumed (range ${pct(ci[0], 0)}–${pct(ci[1], 0)})`

export const months = (n: number): string => (n === 1 ? '1 month' : `${n} months`)

export const shortDateTime = (iso: string): string =>
  new Date(iso).toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
