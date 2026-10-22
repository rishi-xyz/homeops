import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from './api'
import { formatDate, formatDateTime, titleCase, warrantyTone } from './format'
import type {
  Asset,
  AssistantTurn,
  Card,
  HandoffPayload,
  HealthResponse,
  MaintenanceEvent,
  McpTool,
  Reminder,
  ServiceRequest,
  ServiceSlot,
  ToolTraceEntry,
} from './types'

const SUGGESTIONS = [
  'Is my washing machine still under warranty?',
  'Remind me a month before it expires',
  'Has the washing machine leaked before?',
  'Prepare a brief for the technician',
  'Help me contact a technician',
  'What appointment slots are available?',
]

type Message = {
  id: string
  role: 'user' | 'assistant'
  text: string
  turn?: AssistantTurn
  followUp?: string | null
  error?: string
}

type Tab = 'chat' | 'assets' | 'reminders' | 'history' | 'handoff' | 'booking'

function newId() {
  return Math.random().toString(36).slice(2)
}

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)
  const [tools, setTools] = useState<McpTool[]>([])
  const [tab, setTab] = useState<Tab>('chat')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [toolFeed, setToolFeed] = useState<ToolTraceEntry[]>([])
  const conversationId = useRef(`web-${newId()}`)

  const refreshHealth = useCallback(async () => {
    try {
      const result = await api.health()
      setHealth(result)
      setHealthError(null)
      try {
        const listed = await api.mcpTools()
        setTools(listed.tools)
      } catch {
        setTools([])
      }
    } catch (error) {
      setHealth(null)
      setHealthError(error instanceof ApiError ? error.message : 'Health check failed.')
    }
  }, [])

  useEffect(() => {
    void refreshHealth()
    const timer = window.setInterval(() => void refreshHealth(), 15000)
    return () => window.clearInterval(timer)
  }, [refreshHealth])

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim()
      if (!text || busy) return
      setBusy(true)
      setInput('')
      setMessages((current) => [...current, { id: newId(), role: 'user', text }])
      try {
        const turn = await api.sendMessage(text, conversationId.current)
        setToolFeed((current) => [...turn.tool_trace, ...current].slice(0, 60))
        setMessages((current) => [
          ...current,
          { id: newId(), role: 'assistant', text: turn.reply, turn, followUp: turn.follow_up },
        ])
      } catch (error) {
        const message = error instanceof ApiError ? error.message : 'The assistant call failed.'
        setMessages((current) => [...current, { id: newId(), role: 'assistant', text: message, error: message }])
      } finally {
        setBusy(false)
      }
    },
    [busy],
  )

  const mcpState = useMemo(() => {
    if (healthError) return { label: 'API offline', tone: 'bad' as const, detail: healthError }
    if (!health) return { label: 'Connecting...', tone: 'warn' as const, detail: 'Checking the orchestrator.' }
    if (!health.mcp.connected)
      return { label: 'MCP disconnected', tone: 'bad' as const, detail: health.mcp.last_error ?? 'No MCP session.' }
    return {
      label: 'MCP connected',
      tone: 'ok' as const,
      detail: `${health.mcp.server_info?.name ?? 'homeops'} v${health.mcp.server_info?.version ?? '?'} - protocol ${health.mcp.protocol_version ?? 'unknown'}`,
    }
  }, [health, healthError])

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">HO</span>
          <div>
            <h1>HomeOps</h1>
            <p>Household maintenance assistant - Alexa+-style simulation over a real MCP server</p>
          </div>
        </div>
        <div className="status-cluster">
          <span className={`pill ${mcpState.tone}`}>{mcpState.label}</span>
          <span className="status-detail">{mcpState.detail}</span>
          {health && (
            <span className="status-detail">
              summary: {health.summary_provider} - tz: {health.household_timezone}
            </span>
          )}
          <button className="ghost" onClick={() => void refreshHealth()}>
            Refresh
          </button>
        </div>
      </header>

      <div className="demo-banner">
        Demo data only: every household record, provider and appointment slot is fictional. Opening a
        link is a handoff - HomeOps never sends a message or books an appointment.
      </div>

      <nav className="tabs">
        {(
          [
            ['chat', 'Assistant'],
            ['assets', 'Assets and warranty'],
            ['reminders', 'Reminders'],
            ['history', 'Maintenance history'],
            ['handoff', 'Provider handoff'],
            ['booking', 'Demo booking'],
          ] as [Tab, string][]
        ).map(([value, label]) => (
          <button key={value} className={tab === value ? 'tab active' : 'tab'} onClick={() => setTab(value)}>
            {label}
          </button>
        ))}
      </nav>

      <main className="layout">
        <section className="main-panel">
          {tab === 'chat' && (
            <ChatPanel
              messages={messages}
              input={input}
              busy={busy}
              onInput={setInput}
              onSend={send}
              followUp={messages[messages.length - 1]?.followUp ?? null}
            />
          )}
          {tab === 'assets' && <AssetsPanel />}
          {tab === 'reminders' && <RemindersPanel onTool={setToolFeed} />}
          {tab === 'history' && <HistoryPanel onTool={setToolFeed} onAsk={send} />}
          {tab === 'handoff' && <HandoffPanel onTool={setToolFeed} />}
          {tab === 'booking' && <BookingPanel onTool={setToolFeed} />}
        </section>

        <aside className="side-panel">
          <McpPanel health={health} tools={tools} feed={toolFeed} />
        </aside>
      </main>
    </div>
  )
}

/* ------------------------------------------------------------------ chat */

function ChatPanel({
  messages,
  input,
  busy,
  onInput,
  onSend,
  followUp,
}: {
  messages: Message[]
  input: string
  busy: boolean
  onInput: (value: string) => void
  onSend: (value: string) => void
  followUp: string | null
}) {
  const endRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  return (
    <div className="chat">
      <div className="chat-scroll">
        {messages.length === 0 && (
          <div className="empty-state">
            <h2>Ask about your home</h2>
            <p>
              Warranty checks, reminders, previous incidents, technician briefs and provider handoffs all run
              through the MCP server. Try one of these:
            </p>
            <div className="suggestions">
              {SUGGESTIONS.map((item) => (
                <button key={item} className="chip" onClick={() => onSend(item)} disabled={busy}>
                  {item}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message) => (
          <div key={message.id} className={`bubble-row ${message.role}`}>
            <div className={`bubble ${message.role}${message.error ? ' error' : ''}`}>
              <pre className="reply">{message.text}</pre>
              {message.followUp && <p className="follow-up">Suggested next: {message.followUp}</p>}
              {message.turn && message.turn.cards.length > 0 && (
                <div className="cards">
                  {message.turn.cards.map((card, index) => (
                    <CardView key={`${card.type}-${card.id}-${index}`} card={card} />
                  ))}
                </div>
              )}
              {message.turn && (
                <div className="trace">
                  <span className="trace-label">MCP tools:</span>
                  {message.turn.tool_trace.length === 0 && <em>none</em>}
                  {message.turn.tool_trace.map((entry, index) => (
                    <span key={`${entry.name}-${index}`} className={`tool-pill ${entry.status}`}>
                      {entry.name} - {entry.status}
                      {entry.record_ids.length > 0 ? ` (${entry.record_ids.length})` : ''}
                    </span>
                  ))}
                  <span className="trace-label">intent: {message.turn.intent ?? 'n/a'}</span>
                </div>
              )}
            </div>
          </div>
        ))}

        {busy && (
          <div className="bubble-row assistant">
            <div className="bubble assistant">
              <span className="typing">Running the MCP tool call...</span>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault()
          onSend(input)
        }}
      >
        <input
          value={input}
          maxLength={500}
          placeholder={followUp ?? 'Ask about a warranty, reminder, incident or provider handoff...'}
          onChange={(event) => onInput(event.target.value)}
          disabled={busy}
        />
        <button type="submit" disabled={busy || input.trim().length === 0}>
          Send
        </button>
      </form>
    </div>
  )
}

function CardView({ card }: { card: Card }) {
  const payload = card as Record<string, unknown>
  return (
    <div className={`card card-${card.type}`}>
      <div className="card-head">
        <span className="card-type">{titleCase(card.type)}</span>
        {card.is_demo && <span className="demo-tag">demo data</span>}
      </div>
      <strong>{card.title}</strong>
      {card.type === 'asset' && typeof payload.warranty === 'object' && payload.warranty !== null && (
        <WarrantyBlock warranty={payload.warranty as Record<string, unknown>} />
      )}
      {card.type === 'reminder' && (
        <p className="card-meta">
          due {formatDateTime(payload.due_at as string)} - {String(payload.status ?? 'scheduled')}
        </p>
      )}
      {card.type === 'maintenance_event' && (
        <p className="card-meta">
          {formatDateTime(payload.occurred_at as string)} - {String(payload.event_type ?? '')}
        </p>
      )}
      {card.type === 'service_slot' && <p className="card-meta">{String(payload.provider_id ?? '')}</p>}
      {card.type === 'handoff' && (
        <p className="card-meta">
          {Array.isArray(payload.actions) ? `${payload.actions.length} prepared actions` : 'handoff'}
        </p>
      )}
      <code className="card-id">{card.id}</code>
    </div>
  )
}

function WarrantyBlock({ warranty }: { warranty: Record<string, unknown> }) {
  const status = String(warranty.status ?? 'unknown')
  return (
    <div className="warranty">
      <span className={`pill ${warrantyTone(status)}`}>{titleCase(status)}</span>
      <span>ends {formatDate(warranty.warranty_end as string)}</span>
      {typeof warranty.days_remaining === 'number' && <span>{warranty.days_remaining} days remaining</span>}
    </div>
  )
}

/* ---------------------------------------------------------------- assets */

function AssetsPanel() {
  const [assets, setAssets] = useState<Asset[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<Awaited<ReturnType<typeof api.asset>> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .assets()
      .then((result) => {
        setAssets(result.assets)
        setError(null)
      })
      .catch((cause) => setError(cause instanceof ApiError ? cause.message : 'Could not load assets.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selected) {
      setDetail(null)
      return
    }
    api
      .asset(selected)
      .then(setDetail)
      .catch((cause) => setError(cause instanceof ApiError ? cause.message : 'Could not load the asset.'))
  }, [selected])

  if (loading) return <PanelEmpty title="Loading household assets..." />

  return (
    <div className="panel-grid">
      <div className="list">
        <h2>Household assets</h2>
        {error && <p className="error-text">{error}</p>}
        {assets.length === 0 && <PanelEmpty title="No assets stored" body="Run `make seed` to load the fictional demo household." />}
        {assets.map((asset) => (
          <button
            key={asset.asset_id}
            className={selected === asset.asset_id ? 'list-item active' : 'list-item'}
            onClick={() => setSelected(asset.asset_id)}
          >
            <div>
              <strong>{asset.name}</strong>
              {asset.is_demo && <span className="demo-tag">demo</span>}
              <p className="muted">
                {[asset.brand, asset.model].filter(Boolean).join(' ') || 'brand unknown'} - {asset.location ?? 'location unknown'}
              </p>
            </div>
            <span className={`pill ${warrantyTone(asset.warranty_status)}`}>{titleCase(asset.warranty_status)}</span>
          </button>
        ))}
      </div>

      <div className="detail">
        {!detail && <PanelEmpty title="Select an asset" body="Records, warranty dates, provenance and linked history appear here." />}
        {detail && (
          <>
            <h2>{detail.detail.asset.name}</h2>
            <dl className="facts">
              <Fact label="Asset ID" value={detail.detail.asset.asset_id} />
              <Fact label="Category / location" value={`${titleCase(detail.detail.asset.category)} at ${detail.detail.asset.location ?? 'unknown'}`} />
              <Fact label="Brand / model" value={[detail.detail.asset.brand, detail.detail.asset.model].filter(Boolean).join(' / ') || 'unknown'} />
              <Fact label="Purchase date (as saved)" value={formatDate(detail.detail.asset.purchase_date)} />
              <Fact label="Warranty start (as saved)" value={formatDate(detail.detail.warranty.warranty_start)} />
              <Fact label="Warranty end (as saved)" value={formatDate(detail.detail.warranty.warranty_end)} />
              <Fact label="Manual reference" value={detail.detail.asset.manual_ref ?? 'unknown'} />
              <Fact label="Receipt reference" value={detail.detail.asset.receipt_ref ?? 'unknown'} />
            </dl>
            <div className={`notice ${warrantyTone(detail.detail.warranty.status)}`}>
              <strong>{titleCase(detail.detail.warranty.status)}</strong>
              <p>{detail.detail.warranty.basis_note ?? detail.warranty_basis_note}</p>
            </div>
            <h3>Linked records</h3>
            <p className="muted">Recent events: {detail.detail.recent_event_ids.join(', ') || 'none'}</p>
            <p className="muted">Open reminders: {detail.detail.open_reminder_ids.join(', ') || 'none'}</p>
          </>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------- reminders */

function RemindersPanel({ onTool }: { onTool: (entries: ToolTraceEntry[]) => void }) {
  const [reminders, setReminders] = useState<Reminder[]>([])
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [dueAt, setDueAt] = useState('')

  const load = useCallback(() => {
    api
      .reminders()
      .then((result) => {
        setReminders(result.reminders)
        setError(null)
      })
      .catch((cause) => setError(cause instanceof ApiError ? cause.message : 'Could not load reminders.'))
  }, [])

  useEffect(load, [load])

  const create = async () => {
    if (!title.trim() || !dueAt) {
      setError('A title and a due date are required.')
      return
    }
    try {
      const created = await api.createReminder({ title: title.trim(), due_at: new Date(dueAt).toISOString() })
      setTitle('')
      setDueAt('')
      setMessage(`Reminder saved: ${created.title} (${created.reminder_id})`)
      setError(null)
      onTool([
        {
          name: 'create_reminder',
          status: 'success',
          duration_ms: 0,
          record_ids: [created.reminder_id],
          summary: created.title,
        },
      ])
      load()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not create the reminder.')
    }
  }

  const complete = async (reminderId: string) => {
    try {
      await api.completeReminder(reminderId)
      onTool([{ name: 'complete_reminder', status: 'success', duration_ms: 0, record_ids: [reminderId] }])
      load()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not complete the reminder.')
    }
  }

  return (
    <div className="panel-single">
      <h2>Reminders</h2>
      <p className="muted">
        Due state is recomputed by the MCP server on every call, so a completed reminder never reappears as due.
        Dates are timezone-aware; the household timezone is used when a reminder is created from the assistant.
      </p>

      <div className="form-row">
        <input placeholder="Reminder title" value={title} maxLength={200} onChange={(event) => setTitle(event.target.value)} />
        <input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} />
        <button onClick={() => void create()}>Create reminder</button>
      </div>
      {message && <p className="success-text">{message}</p>}
      {error && <p className="error-text">{error}</p>}

      <div className="table">
        <div className="table-head">
          <span>Title</span>
          <span>Due</span>
          <span>Timezone</span>
          <span>Status</span>
          <span>Asset</span>
          <span />
        </div>
        {reminders.length === 0 && <PanelEmpty title="No reminders stored" body="Create one above or ask the assistant." />}
        {reminders.map((reminder) => (
          <div key={reminder.reminder_id} className="table-row">
            <span>
              {reminder.title}
              {reminder.is_demo && <span className="demo-tag">demo</span>}
            </span>
            <span>{formatDateTime(reminder.due_at)}</span>
            <span>{reminder.timezone}</span>
            <span className={`pill ${reminder.is_overdue ? 'bad' : reminder.status === 'completed' ? 'ok' : 'warn'}`}>
              {reminder.is_overdue ? 'overdue' : titleCase(reminder.status)}
            </span>
            <span className="muted">{reminder.asset_name ?? 'unlinked'}</span>
            <span>
              {reminder.status === 'completed' ? (
                <em className="muted">completed</em>
              ) : (
                <button className="ghost" onClick={() => void complete(reminder.reminder_id)}>
                  Complete
                </button>
              )}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* --------------------------------------------------------------- history */

function HistoryPanel({ onTool, onAsk }: { onTool: (entries: ToolTraceEntry[]) => void; onAsk: (text: string) => void }) {
  const [assets, setAssets] = useState<Asset[]>([])
  const [assetId, setAssetId] = useState('')
  const [query, setQuery] = useState('')
  const [events, setEvents] = useState<MaintenanceEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [searched, setSearched] = useState(false)
  const [description, setDescription] = useState('')

  useEffect(() => {
    api.assets().then((result) => setAssets(result.assets)).catch(() => undefined)
    void run('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const run = async (search: string) => {
    try {
      const result = await api.maintenance({ asset_id: assetId || undefined, query: search || undefined })
      setEvents(result.events)
      setSearched(true)
      setError(null)
      onTool([
        {
          name: 'search_maintenance_history',
          status: 'success',
          duration_ms: 0,
          record_ids: result.events.map((event) => event.event_id),
          summary: `${result.events.length} record(s)`,
        },
      ])
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not search the maintenance history.')
    }
  }

  const logEvent = async () => {
    if (!description.trim()) return
    try {
      const event = await api.logMaintenance({
        event_type: 'issue',
        description: description.trim(),
        asset_id: assetId || null,
      })
      setDescription('')
      onTool([
        { name: 'log_maintenance_event', status: 'success', duration_ms: 0, record_ids: [event.event_id] },
      ])
      void run(query)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not log the event.')
    }
  }

  return (
    <div className="panel-single">
      <h2>Maintenance history</h2>
      <p className="muted">
        An empty result is a valid answer: it means HomeOps has no stored record, not that nothing happened.
      </p>

      <div className="form-row">
        <select value={assetId} onChange={(event) => setAssetId(event.target.value)}>
          <option value="">All assets</option>
          {assets.map((asset) => (
            <option key={asset.asset_id} value={asset.asset_id}>
              {asset.name}
            </option>
          ))}
        </select>
        <input placeholder="Search text (for example: leak)" value={query} onChange={(event) => setQuery(event.target.value)} />
        <button onClick={() => void run(query)}>Search</button>
      </div>

      {error && <p className="error-text">{error}</p>}

      <div className="timeline">
        {searched && events.length === 0 && (
          <PanelEmpty title="No matching record" body="HomeOps found no stored record for that search." />
        )}
        {events.map((event) => (
          <div key={event.event_id} className="timeline-item">
            <div className="timeline-head">
              <span className={`pill ${event.event_type === 'issue' ? 'bad' : 'ok'}`}>{titleCase(event.event_type)}</span>
              <span className="muted">{formatDateTime(event.occurred_at ?? event.created_at)}</span>
              {event.is_demo && <span className="demo-tag">demo</span>}
            </div>
            <p>{event.description}</p>
            {event.outcome && <p className="muted">Outcome: {event.outcome}</p>}
            <code className="card-id">{event.event_id}</code>
            <button className="ghost" onClick={() => onAsk(`Prepare a brief for the event ${event.event_id}`)}>
              Ask for a brief
            </button>
          </div>
        ))}
      </div>

      <h3>Log a new record</h3>
      <div className="form-row">
        <input placeholder="What happened?" value={description} maxLength={500} onChange={(event) => setDescription(event.target.value)} />
        <button onClick={() => void logEvent()}>Log issue</button>
      </div>
    </div>
  )
}

/* --------------------------------------------------------------- handoff */

function HandoffPanel({ onTool }: { onTool: (entries: ToolTraceEntry[]) => void }) {
  const [assets, setAssets] = useState<Asset[]>([])
  const [category, setCategory] = useState('appliance_repair')
  const [assetId, setAssetId] = useState('')
  const [issue, setIssue] = useState('')
  const [payload, setPayload] = useState<HandoffPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [opened, setOpened] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    api.assets().then((result) => setAssets(result.assets)).catch(() => undefined)
  }, [])

  const prepare = async () => {
    try {
      const result = await api.prepareHandoff({
        service_category: category,
        asset_id: assetId || null,
        issue_description: issue || null,
      })
      setPayload(result)
      setError(null)
      onTool([
        {
          name: 'prepare_service_handoff',
          status: 'success',
          duration_ms: 0,
          record_ids: result.provider ? [result.provider.provider_id] : [],
          summary: `${result.actions.length} action(s)`,
        },
      ])
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not prepare the handoff.')
    }
  }

  const openLink = (action: { label: string; url: string }) => {
    setOpened(action.label)
    window.open(action.url, '_blank', 'noopener,noreferrer')
  }

  const copyDraft = async () => {
    if (!payload) return
    try {
      await navigator.clipboard.writeText(payload.message_draft ?? '')
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="panel-single">
      <h2>Provider handoff</h2>
      <p className="muted">
        Nothing here sends a message or books anything. HomeOps prepares links and a message draft; you review
        the recipient and the content before opening anything.
      </p>

      <div className="form-row">
        <select value={category} onChange={(event) => setCategory(event.target.value)}>
          <option value="appliance_repair">Appliance repair</option>
          <option value="plumbing">Plumbing</option>
          <option value="electrical">Electrical</option>
          <option value="heating">Heating</option>
          <option value="garden">Garden</option>
        </select>
        <select value={assetId} onChange={(event) => setAssetId(event.target.value)}>
          <option value="">No specific asset</option>
          {assets.map((asset) => (
            <option key={asset.asset_id} value={asset.asset_id}>
              {asset.name}
            </option>
          ))}
        </select>
        <input placeholder="Short issue summary" value={issue} maxLength={500} onChange={(event) => setIssue(event.target.value)} />
        <button onClick={() => void prepare()}>Prepare handoff</button>
      </div>

      {error && <p className="error-text">{error}</p>}

      {payload && (
        <div className="handoff">
          <div className="handoff-head">
            <h3>{payload.provider?.name ?? 'Service provider search'}</h3>
            {payload.provider?.is_demo && <span className="demo-tag">fictional provider</span>}
            <span className="muted">
              {payload.provider?.locality ?? 'locality unknown'} - {payload.provider?.service_categories.map(titleCase).join(', ') ?? ''}
            </span>
          </div>

          <div className="actions">
            {payload.actions.map((action) => (
              <button key={action.action_type + action.url} className="action" onClick={() => openLink(action)}>
                <strong>{action.label}</strong>
                <span className="muted">{action.recipient ?? action.url.slice(0, 60)}</span>
              </button>
            ))}
            {payload.actions.length === 0 && (
              <p className="muted">
                No contact details are stored for this provider, so HomeOps only offers a Maps search. It will not
                invent a phone number or an email address.
              </p>
            )}
          </div>

          {payload.unavailable_actions.length > 0 && (
            <p className="muted">Not available for this provider: {payload.unavailable_actions.join(', ')}</p>
          )}

          <div className="draft">
            <div className="draft-head">
              <h4>Message draft (preview before sending)</h4>
              <button className="ghost" onClick={() => void copyDraft()}>
                {copied ? 'Copied' : 'Copy draft'}
              </button>
            </div>
            <pre>{payload.message_draft}</pre>
          </div>

          {opened && (
            <p className="muted">
              Opened &quot;{opened}&quot;. That only hands control to an external app. It is recorded as a handoff, never
              as a sent message or a confirmed booking.
            </p>
          )}
          <div className="notice warn">
            <p>{payload.disclaimer}</p>
          </div>
        </div>
      )}
    </div>
  )
}

/* --------------------------------------------------------------- booking */

function BookingPanel({ onTool }: { onTool: (entries: ToolTraceEntry[]) => void }) {
  const [category, setCategory] = useState('appliance_repair')
  const [slots, setSlots] = useState<ServiceSlot[]>([])
  const [notice, setNotice] = useState('')
  const [draft, setDraft] = useState<{ request: ServiceRequest; confirmation_token: string; notice: string } | null>(null)
  const [requests, setRequests] = useState<ServiceRequest[]>([])
  const [error, setError] = useState<string | null>(null)

  const loadRequests = useCallback(() => {
    api
      .demoRequests()
      .then((result) => setRequests(result.requests))
      .catch(() => undefined)
  }, [])

  const loadSlots = useCallback(async (value: string) => {
    try {
      const result = await api.slots(value)
      setSlots(result.slots)
      setNotice(result.notice)
      setDraft(null)
      setError(null)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not load demo slots.')
    }
  }, [])

  useEffect(() => {
    void loadSlots(category)
    loadRequests()
  }, [category, loadSlots, loadRequests])

  const draftRequest = async (slotId: string) => {
    try {
      const result = await api.draftDemoRequest({ slot_id: slotId })
      setDraft(result)
      setError(null)
      onTool([{ name: 'draft_demo_service_request', status: 'success', duration_ms: 0, record_ids: [result.request.request_id] }])
      loadRequests()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not draft the request.')
    }
  }

  const confirmRequest = async () => {
    if (!draft) return
    try {
      const request = await api.confirmDemoRequest(draft.request.request_id, draft.confirmation_token)
      setDraft({ ...draft, request })
      onTool([{ name: 'confirm_demo_service_request', status: 'success', duration_ms: 0, record_ids: [request.request_id] }])
      loadRequests()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not confirm the request.')
    }
  }

  return (
    <div className="panel-single">
      <h2>Demo booking</h2>
      <p className="muted">
        {notice || 'These slots are fictional and do not represent real availability.'}
      </p>

      <div className="form-row">
        <select value={category} onChange={(event) => setCategory(event.target.value)}>
          <option value="appliance_repair">Appliance repair</option>
          <option value="plumbing">Plumbing</option>
          <option value="electrical">Electrical</option>
          <option value="heating">Heating</option>
          <option value="garden">Garden</option>
        </select>
      </div>

      {error && <p className="error-text">{error}</p>}

      <div className="slot-grid">
        {slots.length === 0 && <PanelEmpty title="No demo slots" body="The demo ships fictional slots for a few services only." />}
        {slots.map((slot) => (
          <div key={slot.slot_id} className="slot">
            <span className="demo-tag">simulated slot</span>
            <strong>{formatDateTime(slot.starts_at)}</strong>
            <p className="muted">
              ends {formatDateTime(slot.ends_at)} - {slot.provider_id}
            </p>
            <code className="card-id">{slot.slot_id}</code>
            <button onClick={() => void draftRequest(slot.slot_id)}>Draft request</button>
          </div>
        ))}
      </div>

      {draft && (
        <div className="notice warn">
          <h4>Simulated booking - not confirmed</h4>
          <p>{draft.notice}</p>
          <dl className="facts">
            <Fact label="Request" value={draft.request.request_id} />
            <Fact label="Slot" value={draft.request.slot_id} />
            <Fact label="Status" value={titleCase(draft.request.status)} />
            <Fact label="Confirmation reference" value={draft.confirmation_token} />
          </dl>
          {draft.request.status === 'confirmed_demo' ? (
            <p className="success-text">
              Confirmed as a local demo record. No real service provider has been contacted and no real appointment
              exists.
            </p>
          ) : (
            <button onClick={() => void confirmRequest()}>Confirm this simulated request</button>
          )}
        </div>
      )}

      <h3>All simulated requests</h3>
      <div className="table">
        <div className="table-head">
          <span>Request</span>
          <span>Slot</span>
          <span>Status</span>
          <span>Created</span>
        </div>
        {requests.length === 0 && <PanelEmpty title="No simulated requests yet" body="Draft one from a slot above." />}
        {requests.map((request) => (
          <div key={request.request_id} className="table-row">
            <span>{request.request_id}</span>
            <span className="muted">{request.slot_id}</span>
            <span className={`pill ${request.status === 'confirmed_demo' ? 'warn' : 'unknown'}`}>{titleCase(request.status)}</span>
            <span className="muted">{formatDateTime(request.created_at)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* -------------------------------------------------------------- mcp side */

function McpPanel({ health, tools, feed }: { health: HealthResponse | null; tools: McpTool[]; feed: ToolTraceEntry[] }) {
  return (
    <div className="mcp">
      <h2>MCP server</h2>
      {/* Everything here is read back from the running MCP session and the trace
          the API returned - the UI does not fabricate tool activity. */}
      {!health && <p className="error-text">The orchestrator is not reachable.</p>}
      {health && (
        <dl className="facts">
          <Fact label="Endpoint" value={health.mcp.url} />
          <Fact label="Connected" value={health.mcp.connected ? 'yes' : 'no'} />
          <Fact label="Protocol version" value={health.mcp.protocol_version ?? 'unknown'} />
          <Fact label="Server" value={`${health.mcp.server_info?.name ?? '?'} v${health.mcp.server_info?.version ?? '?'}`} />
          <Fact label="Transport" value="Streamable HTTP" />
          <Fact label="Summary provider" value={health.summary_provider} />
          <Fact label="Demo mode" value={health.demo_mode ? 'on' : 'off'} />
          <Fact label="Database" value={health.database} />
        </dl>
      )}

      <h3>Discovered tools ({tools.length})</h3>
      <ul className="tool-list">
        {tools.map((tool) => (
          <li key={tool.name}>
            <code>{tool.name}</code>
            <span className="muted">{tool.title ?? ''}</span>
          </li>
        ))}
        {tools.length === 0 && <li className="muted">No tools discovered yet.</li>}
      </ul>

      <h3>Recent tool calls</h3>
      <ul className="feed">
        {feed.length === 0 && <li className="muted">No tool calls in this session yet.</li>}
        {feed.map((entry, index) => (
          <li key={`${entry.name}-${index}`} className={entry.status}>
            <code>{entry.name}</code>
            <span className={`pill ${entry.status === 'success' ? 'ok' : 'bad'}`}>{entry.status}</span>
            {entry.record_ids.length > 0 && <span className="muted">{entry.record_ids.join(', ')}</span>}
            {entry.error && <span className="error-text">{entry.error}</span>}
          </li>
        ))}
      </ul>
    </div>
  )
}

/* --------------------------------------------------------------- helpers */

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  )
}

function PanelEmpty({ title, body }: { title: string; body?: string }) {
  return (
    <div className="empty-state small">
      <strong>{title}</strong>
      {body && <p className="muted">{body}</p>}
    </div>
  )
}
