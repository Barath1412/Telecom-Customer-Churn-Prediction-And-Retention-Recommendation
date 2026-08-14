import { describe, expect, it } from 'vitest'
import { deltaWithRange, pct, usd } from '@/lib/format'

describe('formatting is the contract for anything an agent reads aloud', () => {
  it('always shows two decimals on money', () => {
    expect(usd(120.5)).toBe('$120.50')
    expect(usd(705.816)).toBe('$705.82')
  })

  it('never prints a delta without its range', () => {
    // The whole point: a component cannot render half of this.
    expect(deltaWithRange(0.14, [0.05, 0.24])).toBe('14% assumed (range 5%–24%)')
  })

  it('formats probabilities to one decimal by default', () => {
    expect(pct(0.9227)).toBe('92.3%')
  })
})
