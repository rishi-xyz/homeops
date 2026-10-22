// Thin REST client for the FastAPI orchestrator.
//
// Every primary assistant action goes through `/api/assistant/message`, which
// runs an MCP client call against the running MCP server. The UI shows the real
// tool trace returned by that endpoint and never invents a tool call.

import type {
  Asset,
  AssetDetailResponse,
  AssistantTurn,
  DemoRequestResponse,
  HandoffPayload,
  HealthResponse,
  MaintenanceEvent,
  McpTool,
  Provider,
  Reminder,
  ServiceRequest,
  ServiceSlot,
} from './types'

const BASE = ''

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown, message: string) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(BASE + path, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch (cause) {
    throw new ApiError(0, cause, 'The HomeOps API is not reachable. Start it with `make dev`.')
  }
  const text = await response.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = { raw: text }
    }
  }
  if (!response.ok) {
    const detail = (body as { detail?: unknown })?.detail ?? body
    const message =
      typeof detail === 'object' && detail !== null && 'message' in detail
        ? String((detail as { message: unknown }).message)
        : `Request failed with status ${response.status}`
    throw new ApiError(response.status, detail, message)
  }
  return body as T
}

export const api = {
  health: () => request<HealthResponse>('/health'),

  mcpTools: () => request<{ count: number; tools: McpTool[] }>('/api/mcp/tools'),

  sendMessage: (message: string, conversationId: string) =>
    request<AssistantTurn>('/api/assistant/message', {
      method: 'POST',
      body: JSON.stringify({ message, conversation_id: conversationId }),
    }),

  assets: (query?: string) => {
    const params = new URLSearchParams()
    if (query) params.set('query', query)
    const suffix = params.toString() ? `?${params}` : ''
    return request<{ assets: Asset[]; count: number }>(`/api/assets${suffix}`)
  },

  asset: (assetId: string) => request<AssetDetailResponse>(`/api/assets/${assetId}`),

  reminders: () => request<{ reminders: Reminder[]; count: number }>('/api/reminders'),

  createReminder: (payload: { title: string; due_at: string; asset_id?: string | null }) =>
    request<Reminder>('/api/reminders', { method: 'POST', body: JSON.stringify(payload) }),

  completeReminder: (reminderId: string) =>
    request<Reminder>(`/api/reminders/${reminderId}/complete`, { method: 'POST' }),

  maintenance: (params: { asset_id?: string; query?: string } = {}) => {
    const search = new URLSearchParams()
    if (params.asset_id) search.set('asset_id', params.asset_id)
    if (params.query) search.set('query', params.query)
    const suffix = search.toString() ? `?${search}` : ''
    return request<{ events: MaintenanceEvent[]; count: number }>(`/api/maintenance${suffix}`)
  },

  logMaintenance: (payload: {
    event_type: string
    description: string
    asset_id?: string | null
    outcome?: string | null
  }) => request<MaintenanceEvent>('/api/maintenance', { method: 'POST', body: JSON.stringify(payload) }),

  providers: (serviceCategory?: string) => {
    const suffix = serviceCategory ? `?service_category=${serviceCategory}` : ''
    return request<{ providers: Provider[]; count: number }>(`/api/providers${suffix}`)
  },

  prepareHandoff: (payload: {
    service_category: string
    asset_id?: string | null
    issue_description?: string | null
    provider_id?: string | null
  }) =>
    request<HandoffPayload>('/api/handoff/prepare', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  slots: (serviceCategory: string) =>
    request<{ slots: ServiceSlot[]; count: number; notice: string }>(
      `/api/demo/slots?service_category=${encodeURIComponent(serviceCategory)}`,
    ),

  demoRequests: () => request<{ requests: ServiceRequest[]; count: number }>('/api/demo-requests'),

  draftDemoRequest: (payload: { slot_id: string; event_id?: string | null; note?: string | null }) =>
    request<DemoRequestResponse>('/api/demo-requests', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  confirmDemoRequest: (requestId: string, confirmationToken: string) =>
    request<ServiceRequest>(`/api/demo-requests/${requestId}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ confirmation_token: confirmationToken }),
    }),
}
