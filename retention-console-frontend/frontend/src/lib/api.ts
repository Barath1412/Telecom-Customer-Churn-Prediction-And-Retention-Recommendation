import type {
  ActionRequest,
  ActionResponse,
  ApiErrorBody,
  CatalogResponse,
  CustomerDetail,
  LlmTelemetryResponse,
  NarrateResponse,
  QueueResponse,
  QueueStatusFilter,
  ScoreRequest,
  ScoreResponse,
  SummaryResponse,
  UploadBatchResponse,
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
  get requestId(): string {
    return this.body.request_id
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
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
  queue: (page = 1, pageSize = 40, status: QueueStatusFilter = 'pending', search?: string) => {
    const params = new URLSearchParams({
      status,
      page: String(page),
      page_size: String(pageSize),
    })
    if (search && search.trim()) {
      params.set('search', search.trim())
    }
    return request<QueueResponse>(`/queue?${params.toString()}`)
  },
  customer: (id: string) => request<CustomerDetail>(`/customers/${encodeURIComponent(id)}`),
  summary: () => request<SummaryResponse>('/summary'),
  catalog: () => request<CatalogResponse>('/catalog'),
  /**
   * Runs the real pipeline for one customer, live. Takes 5-15 seconds against
   * Gemini; the caller must show progress.
   */
  narrate: (id: string, opts?: { force?: boolean }) =>
    request<NarrateResponse>(
      `/customers/${encodeURIComponent(id)}/narrate${opts?.force ? '?force=true' : ''}`,
      { method: 'POST' },
    ),
  act: (id: string, body: ActionRequest) =>
    request<ActionResponse>(`/customers/${encodeURIComponent(id)}/action`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  score: (body: ScoreRequest) =>
    request<ScoreResponse>('/score', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  scoreNarrate: (body: ScoreRequest, opts?: { provider?: string }) =>
    request<NarrateResponse>(
      `/score/narrate${opts?.provider ? `?provider=${encodeURIComponent(opts.provider)}` : ''}`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
    ),
  uploadBatch: async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    const res = await fetch(`${BASE}/queue/upload`, {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) {
      let body: ApiErrorBody['error'] = {
        code: `HTTP_${res.status}`,
        message: res.statusText || 'Upload failed',
        request_id: 'err_upload',
      }
      try {
        body = ((await res.json()) as ApiErrorBody).error ?? body
      } catch {
        /* fallback */
      }
      throw new ApiError(res.status, body)
    }
    return (await res.json()) as UploadBatchResponse
  },
  resetActions: () =>
    request<{ status: string; pending_total: number; approved_total: number; rejected_total: number }>(
      '/actions/reset',
      { method: 'POST' }
    ),
  llmTelemetry: () => request<LlmTelemetryResponse>('/llm/telemetry'),
}
