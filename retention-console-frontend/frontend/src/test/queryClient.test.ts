import { describe, expect, it } from 'vitest'
import { qk, queryClient } from '@/lib/queryClient'
import { ApiError } from '@/lib/api'

describe('lib/queryClient — retry policy, cache defaults, and key factory', () => {
  describe('qk query-key factory', () => {
    it('generates exact query key tuples for all resource types', () => {
      expect(qk.queue(1)).toEqual(['queue', 1])
      expect(qk.queue(3)).toEqual(['queue', 3])
      expect(qk.customer('0295-PPHDO')).toEqual(['customer', '0295-PPHDO'])
      expect(qk.summary()).toEqual(['summary'])
      expect(qk.catalog()).toEqual(['catalog'])
    })
  })

  describe('queryClient cache defaults', () => {
    it('configures memory-only staleTime and gcTime with no window focus refetch', () => {
      const defaultQueries = queryClient.getDefaultOptions().queries
      expect(defaultQueries?.staleTime).toBe(60_000)
      expect(defaultQueries?.gcTime).toBe(5 * 60_000)
      expect(defaultQueries?.refetchOnWindowFocus).toBe(false)
    })

    it('sets mutation retry count to 0 (no optimistic retry)', () => {
      const defaultMutations = queryClient.getDefaultOptions().mutations
      expect(defaultMutations?.retry).toBe(0)
    })
  })

  describe('retry policy', () => {
    const retryFn = queryClient.getDefaultOptions().queries?.retry as (
      failureCount: number,
      error: unknown,
    ) => boolean

    it('never retries 4xx ApiErrors (contract errors must surface immediately)', () => {
      const error400 = new ApiError(400, { code: 'BAD_REQUEST', message: 'Bad request', request_id: 'req_1' })
      const error404 = new ApiError(404, { code: 'NOT_FOUND', message: 'Customer not found', request_id: 'req_2' })
      const error422 = new ApiError(422, { code: 'VALIDATION_ERROR', message: 'Invalid payload', request_id: 'req_3' })

      // At failure count 0
      expect(retryFn(0, error400)).toBe(false)
      expect(retryFn(0, error404)).toBe(false)
      expect(retryFn(0, error422)).toBe(false)

      // At failure count 1
      expect(retryFn(1, error400)).toBe(false)
      expect(retryFn(1, error404)).toBe(false)
      expect(retryFn(1, error422)).toBe(false)
    })

    it('retries transient 5xx server errors up to 2 times', () => {
      const error500 = new ApiError(500, { code: 'HTTP_500', message: 'Internal Server Error', request_id: 'req_4' })
      const error503 = new ApiError(503, { code: 'HTTP_503', message: 'Service Unavailable', request_id: 'req_5' })

      expect(retryFn(0, error500)).toBe(true)
      expect(retryFn(1, error500)).toBe(true)
      expect(retryFn(2, error500)).toBe(false)

      expect(retryFn(0, error503)).toBe(true)
      expect(retryFn(1, error503)).toBe(true)
      expect(retryFn(2, error503)).toBe(false)
    })

    it('retries non-ApiError / network failures up to 2 times', () => {
      const networkError = new TypeError('Failed to fetch')

      expect(retryFn(0, networkError)).toBe(true)
      expect(retryFn(1, networkError)).toBe(true)
      expect(retryFn(2, networkError)).toBe(false)
    })
  })
})
