import { describe, expect, it } from 'vitest'
import { api, ApiError } from '@/lib/api'
import { qk, queryClient } from '@/lib/queryClient'
import { cn } from '@/lib/cn'
import { server } from '@/mocks/server'
import { failureHandlers } from '@/mocks/handlers'

describe('ApiError and api client', () => {
  it('instantiates ApiError with code, fields, and requestId', () => {
    const err = new ApiError(422, {
      code: 'VALIDATION_ERROR',
      message: 'Invalid field',
      fields: [{ field: 'Monthly Charges', message: 'Too high' }],
      request_id: 'req_123',
    })
    expect(err.status).toBe(422)
    expect(err.message).toBe('Invalid field')
    expect(err.code).toBe('VALIDATION_ERROR')
    expect(err.fields).toHaveLength(1)
    expect(err.requestId).toBe('req_123')
  })

  it('fetches queue data successfully via api.queue', async () => {
    const res = await api.queue(1, 40)
    expect(res.items.length).toBeGreaterThan(0)
    expect(res.run_id).toBeDefined()
  })

  it('fetches customer detail successfully via api.customer', async () => {
    const res = await api.customer('0295-PPHDO')
    expect(res.customer_id).toBe('0295-PPHDO')
    expect(res.policy_trace.length).toBeGreaterThan(0)
  })

  it('fetches a no-offer customer detail via api.customer', async () => {
    const res = await api.customer('5461-QKNTN')
    expect(res.customer_id).toBe('5461-QKNTN')
    expect(res.status).toBe('review_no_profitable_offer')
  })

  it('fetches summary data via api.summary', async () => {
    const res = await api.summary()
    expect(res.funnel).toBeDefined()
    expect(res.economics).toBeDefined()
  })

  it('fetches catalog data via api.catalog', async () => {
    const res = await api.catalog()
    expect(res.catalog_version).toBe(3)
    expect(res.offers).toHaveLength(6)
  })

  it('posts action via api.act', async () => {
    const res = await api.act('0295-PPHDO', {
      action: 'approve',
      actor: 'agent_42',
      reason_code: null,
      modified_offer_id: null,
      note: 'Customer agreed',
    })
    expect(res.status).toBe('recorded')
    expect(res.audit_id).toBeDefined()
  })

  it('posts score via api.score', async () => {
    const res = await api.score({
      Gender: 'Male',
      'Senior Citizen': 'No',
    })
    expect(res.p_churn).toBeDefined()
    expect(res.risk_band).toBe('critical')
  })

  it('throws ApiError on validation failure', async () => {
    server.use(failureHandlers.validation)
    await expect(api.queue(1)).rejects.toThrow(ApiError)
  })

  it('throws ApiError with LEAKAGE_REJECTED code and request_id on leakage failure', async () => {
    server.use(failureHandlers.leakage)
    try {
      await api.queue(1)
      expect.unreachable('Should have thrown')
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      const apiErr = e as ApiError
      expect(apiErr.code).toBe('LEAKAGE_REJECTED')
      expect(apiErr.requestId).toBe('req_01J8XYZ')
    }
  })
})

describe('queryClient and query keys', () => {
  it('generates consistent query keys from qk factory', () => {
    expect(qk.queue(1)).toEqual(['queue', 1])
    expect(qk.customer('123')).toEqual(['customer', '123'])
    expect(qk.summary()).toEqual(['summary'])
    expect(qk.catalog()).toEqual(['catalog'])
  })

  it('enforces retry policy: never retry 4xx errors', () => {
    const retryFn = queryClient.getDefaultOptions().queries?.retry as (
      failureCount: number,
      error: unknown,
    ) => boolean
    const err400 = new ApiError(400, { code: 'BAD_REQUEST', message: 'Bad', request_id: '1' })
    const err500 = new ApiError(500, { code: 'SERVER_ERROR', message: 'Error', request_id: '2' })
    const errNetwork = new Error('Network error')

    expect(retryFn(0, err400)).toBe(false)
    expect(retryFn(1, err400)).toBe(false)
    expect(retryFn(0, err500)).toBe(true)
    expect(retryFn(1, err500)).toBe(true)
    expect(retryFn(2, err500)).toBe(false)
    expect(retryFn(0, errNetwork)).toBe(true)
  })
})

describe('cn helper', () => {
  it('combines class names correctly', () => {
    expect(cn('base', 'active')).toBe('base active')
    expect(cn('base', false && 'hidden', 'visible')).toBe('base visible')
  })
})
