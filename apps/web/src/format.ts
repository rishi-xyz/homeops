// Small display helpers shared by the panels.

export function titleCase(value: string): string {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export function formatDateTime(value?: string | null): string {
  if (!value) return 'not recorded'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatDate(value?: string | null): string {
  if (!value) return 'unknown'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' })
}

export function warrantyTone(status: string): 'ok' | 'warn' | 'bad' | 'unknown' {
  switch (status) {
    case 'active':
      return 'ok'
    case 'expiring_soon':
      return 'warn'
    case 'expired':
      return 'bad'
    default:
      return 'unknown'
  }
}
