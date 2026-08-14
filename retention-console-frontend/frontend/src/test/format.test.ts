import { describe, expect, it } from 'vitest'
import { deltaWithRange, months, pct, shortDateTime, usd, usdCompact } from '@/lib/format'

describe('formatting is the contract for anything an agent reads aloud', () => {
  it('always shows two decimals on money', () => {
    expect(usd(120.5)).toBe('$120.50')
    expect(usd(705.816)).toBe('$705.82')
  })

  it('formats compact usd without cents', () => {
    expect(usdCompact(120.5)).toBe('$121')
    expect(usdCompact(5962)).toBe('$5,962')
  })

  it('never prints a delta without its range', () => {
    // The whole point: a component cannot render half of this.
    expect(deltaWithRange(0.14, [0.05, 0.24])).toBe('14% assumed (range 5%–24%)')
  })

  it('formats probabilities to one decimal by default', () => {
    expect(pct(0.9227)).toBe('92.3%')
    expect(pct(0.14, 0)).toBe('14%')
    expect(pct(0.9227, 2)).toBe('92.27%')
  })

  it('formats tenure months correctly for singular and plural', () => {
    expect(months(1)).toBe('1 month')
    expect(months(17)).toBe('17 months')
  })

  it('formats ISO timestamps to readable short date time', () => {
    const formatted = shortDateTime('2026-08-13T09:14:22Z')
    expect(formatted).toBeTruthy()
    expect(typeof formatted).toBe('string')
  })
})
