import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

export type Role = 'MANAGER' | 'ADMIN'
export type Session = { account_id: number; login: string; roles: Role[]; csrf_token: string }
export type Page<T> = { items: T[]; total: number; limit: number; offset: number }
export type Versioned = { id: number; version: number }
export type Direction = 'IN' | 'OUT'
export type Concert = Versioned & {
  name: string; starts_at: string; ends_at: string; venue_id: number | null;
  proposed_organizer_id: number | null; responsible_id: number; expense_budget: string;
  status: 'NEGOTIATING' | 'CONFIRMED' | 'COMPLETED' | 'CANCELLED'; cancel_reason: string | null
}
export type Contract = Versioned & {
  number: string; signed_on: string; counterparty_id: number; concert_id: number;
  kind: 'MAIN_SHOW' | 'SERVICE'; subject: string; amount: string; direction: Direction; status: string
}
export type Engagement = Versioned & {
  counterparty_id: number; concert_id: number; description: string; due_at: string;
  agreed_amount: string; contract_id: number | null; status: string; cancel_reason: string | null
}
export type Entry = Versioned & {
  category_id: number; contract_id: number | null; occurred_on: string; amount: string;
  direction: Direction; basis: string; original_id: number | null;
  status: 'DRAFT' | 'POSTED' | 'VOID'; void_reason: string | null
}
export type CatalogRow = Versioned & {
  name: string; archived: boolean; normal_direction?: Direction
} & Record<string, unknown>
export type Account = Versioned & {
  employee_id: number; full_name: string; position: string; login: string; active: boolean; roles: Role[]
}
export type Responsible = { id: number; full_name: string }

let csrfToken: string | undefined
export function setSession(session: Session | null) { csrfToken = session?.csrf_token }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

function errorDetails(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item) => {
    const loc = Array.isArray(item.loc) ? item.loc.slice(1).join('.') : ''
    return [loc, item.msg].filter(Boolean).join(': ')
  }).join(' · ')
  return `Сервер вернул HTTP ${status}`
}

export async function api<T>(path: string, method = 'GET', payload?: unknown, signal?: AbortSignal): Promise<T> {
  const headers = new Headers({ Accept: 'application/json' })
  if (payload !== undefined) headers.set('Content-Type', 'application/json')
  if (path === '/auth/login') headers.set('X-Requested-With', 'ConcertCRM')
  else if (method !== 'GET' && csrfToken) headers.set('X-CSRF-Token', csrfToken)
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      headers, method, credentials: 'same-origin', signal,
      body: payload === undefined ? undefined : JSON.stringify(payload),
    })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new Error('Нет соединения с API.')
  }
  const body = res.headers.get('content-type')?.includes('application/json') ? await res.json() : undefined
  if (!res.ok) {
    if (res.status === 401 && path !== '/auth/login' && path !== '/auth/me') {
      window.dispatchEvent(new Event('session-expired'))
    }
    throw new ApiError(res.status, errorDetails(body, res.status))
  }
  if (res.status !== 204 && body === undefined) throw new Error('API вернул неожиданный формат ответа.')
  return body as T
}

type Params = Record<string, string | number | boolean | undefined>
export function url(path: string, params: Params) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== '' && value !== undefined) search.set(key, String(value))
  }
  return search.size ? `${path}?${search}` : path
}
export function useRead<T>(path: string | null) {
  return useQuery({ queryKey: ['api', path], queryFn: ({ signal }) => api<T>(path!, 'GET', undefined, signal), enabled: path !== null })
}
export function useOptions<T>(path: string | null) {
  return useQuery({ queryKey: ['api', 'options', path], enabled: path !== null, queryFn: async ({ signal }) => {
    const rows: T[] = []
    let offset = 0
    do {
      const page: Page<T> = await api(`${path}${path!.includes('?') ? '&' : '?'}limit=100&offset=${offset}`, 'GET', undefined, signal)
      rows.push(...page.items)
      offset += page.items.length
      if (!page.items.length || offset >= page.total) break
    } while (true)
    return rows
  } })
}
export function useWrite<T = unknown>() {
  const cache = useQueryClient()
  return useMutation({
    mutationFn: ({ path, method = 'POST', body }: { path: string; method?: string; body?: unknown }) =>
      api<T>(path, method, body),
    onSuccess: (_, { path }) => {
      void cache.invalidateQueries({ queryKey: ['api'] })
      if (path.startsWith('/admin/accounts/')) void cache.invalidateQueries({ queryKey: ['session'] })
    },
  })
}
