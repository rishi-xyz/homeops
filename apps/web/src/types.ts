// Shared types mirroring the FastAPI responses. The browser never talks to the
// MCP server directly; everything below comes from the orchestrator API.

export interface ToolTraceEntry {
  name: string
  status: 'success' | 'error' | string
  duration_ms: number
  record_ids: string[]
  summary?: string | null
  error?: string | null
}

export interface Card {
  type: string
  id: string
  title: string
  is_demo: boolean
  [key: string]: unknown
}

export interface AssistantTurn {
  reply: string
  cards: Card[]
  tool_trace: ToolTraceEntry[]
  summary_provider: string
  follow_up: string | null
  intent: string | null
}

export interface WarrantyInfo {
  status: string
  warranty_start?: string | null
  warranty_end?: string | null
  days_remaining?: number | null
  basis_note?: string
  source_type?: string | null
}

export interface Asset {
  asset_id: string
  name: string
  category: string
  location?: string | null
  brand?: string | null
  model?: string | null
  warranty_status: string
  warranty_end?: string | null
  is_demo: boolean
}

export interface AssetDetailResponse {
  detail: {
    asset: Asset & { purchase_date?: string | null; manual_ref?: string | null; receipt_ref?: string | null }
    warranty: WarrantyInfo
    recent_event_ids: string[]
    open_reminder_ids: string[]
  }
  warranty_basis_note: string
}

export interface Reminder {
  reminder_id: string
  title: string
  due_at: string
  timezone: string
  status: string
  is_overdue: boolean
  asset_id?: string | null
  asset_name?: string | null
  is_demo: boolean
}

export interface MaintenanceEvent {
  event_id: string
  asset_id?: string | null
  event_type: string
  description: string
  occurred_at?: string | null
  created_at?: string | null
  outcome?: string | null
  source_type: string
  is_demo: boolean
}

export interface HandoffAction {
  action_type: 'maps_search' | 'whatsapp' | 'tel' | 'mailto' | 'booking_page'
  label: string
  url: string
  recipient?: string | null
  message_preview?: string | null
  requires_user_action: boolean
  note?: string | null
}

export interface Provider {
  provider_id: string
  name: string
  service_categories: string[]
  phone?: string | null
  email?: string | null
  booking_url?: string | null
  locality?: string | null
  has_phone: boolean
  has_email: boolean
  has_booking_page: boolean
  is_demo: boolean
}

export interface HandoffPayload {
  provider: Provider | null
  actions: HandoffAction[]
  unavailable_actions: string[]
  message_draft: string | null
  disclaimer: string
  technician_brief?: unknown
}

export interface ServiceSlot {
  slot_id: string
  provider_id: string
  service_type: string
  starts_at: string
  ends_at: string
  is_demo: boolean
}

export interface ServiceRequest {
  request_id: string
  slot_id: string
  event_id?: string | null
  status: string
  note?: string | null
  created_at: string
  updated_at?: string | null
  is_demo: boolean
}

export interface DemoRequestResponse {
  request: ServiceRequest
  confirmation_token: string
  notice: string
}

export interface HealthResponse {
  status: string
  service: string
  version: string
  mcp: {
    url: string
    connected: boolean
    protocol_version: string | null
    server_info: Record<string, unknown>
    last_error: string | null
  }
  summary_provider: string
  demo_mode: boolean
  household_timezone: string
  database: string
}

export interface McpTool {
  name: string
  title?: string | null
  description?: string | null
  input_schema?: Record<string, unknown> | null
}
