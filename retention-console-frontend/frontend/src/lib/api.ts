import type {
  ActionRequest,
  ActionResponse,
  ApiErrorBody,
  CatalogResponse,
  CustomerDetail,
  QueueResponse,
  SummaryResponse,
} from '@/types/api'

const BASE = import.meta.env.VITE_API_BASE ?? '/api'

/**
 * A typed error, so a component can branch on `code` instead of string-matching
 * a message. LEAKAGE_REJECTED in particular must render differently from a
 * normal validation failure: it means an upstream system sent a quarantined
 * field, which is an incident, not a typo.
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: ApiErrorBody['error'],
  ) {
    super(body.message)
    this.name = 'ApiError'
  }
  get code(): string {
    return this.body.code
  }
  get fields() {
    return this.body.fields ?? []
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    let body: ApiErrorBody['error'] = {
      code: `HTTP_${res.status}`,
      message: res.statusText || 'Request failed',
      request_id: 'unknown',
    }
    try {
      body = ((await res.json()) as ApiErrorBody).error ?? body
    } catch {
      /* non-JSON error page — keep the synthesised body */
    }
    throw new ApiError(res.status, body)
  }
  return (await res.json()) as T
}

export const api = {
  queue: (page = 1, pageSize = 40) =>
    request<QueueResponse>(`/queue?page=${page}&page_size=${pageSize}`),
  customer: (id: string) => request<CustomerDetail>(`/customers/${encodeURIComponent(id)}`),
  summary: () => request<SummaryResponse>('/summary'),
  catalog: () => request<CatalogResponse>('/catalog'),
  act: (id: string, body: ActionRequest) =>
    request<ActionResponse>(`/customers/${encodeURIComponent(id)}/action`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}
