import { fetchEventSource } from '@microsoft/fetch-event-source'
import type {
  KbCreateInput,
  KbDetail,
  KbDocument,
  KbDocumentPage,
  KbSummary,
  Message,
  StreamEvent,
  Thread,
  TurnDetail,
  TurnPage,
  TurnStatus,
} from './types'

const BASE = '/api'

async function expectOk(res: Response): Promise<Response> {
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res
}

export const listThreads = async (): Promise<Thread[]> =>
  (await expectOk(await fetch(`${BASE}/threads`))).json()

export const createThread = async (): Promise<Thread> =>
  (await expectOk(await fetch(`${BASE}/threads`, { method: 'POST' }))).json()

export const deleteThread = async (id: string): Promise<void> => {
  await expectOk(await fetch(`${BASE}/threads/${id}`, { method: 'DELETE' }))
}

export const getMessages = async (id: string): Promise<Message[]> =>
  (await expectOk(await fetch(`${BASE}/threads/${id}/messages`))).json()

export const listTurns = async (opts: {
  status?: TurnStatus
  threadId?: string
  cursor?: string | null
}): Promise<TurnPage> => {
  const q = new URLSearchParams({ limit: '30' })
  if (opts.status) q.set('status', opts.status)
  if (opts.threadId) q.set('thread_id', opts.threadId)
  if (opts.cursor) q.set('cursor', opts.cursor)
  return (await expectOk(await fetch(`${BASE}/traces?${q}`))).json()
}

export const getTurn = async (id: string): Promise<TurnDetail> =>
  (await expectOk(await fetch(`${BASE}/traces/${id}`))).json()

// The admin token is only held for the current tab and only sent on write requests. It is never
// bundled into the frontend build, never stored in localStorage, and never logged.
const ADMIN_TOKEN_KEY = 'sagent.kb.adminToken'

export const getAdminToken = (): string => sessionStorage.getItem(ADMIN_TOKEN_KEY) ?? ''

export const setAdminToken = (token: string): void => {
  if (token) sessionStorage.setItem(ADMIN_TOKEN_KEY, token)
  else sessionStorage.removeItem(ADMIN_TOKEN_KEY)
}

function detailText(raw: string): string {
  try {
    const detail: unknown = JSON.parse(raw).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (typeof item !== 'object' || item === null) return String(item)
          const { loc, msg } = item as { loc?: unknown; msg?: unknown }
          const where = Array.isArray(loc) ? loc.join('.') : ''
          return where ? `${where}: ${String(msg ?? '')}` : String(msg ?? '')
        })
        .join('; ')
    }
  } catch {
    // Plain-text error body: show it as is.
  }
  return raw
}

async function kbFetch(path: string, init?: RequestInit, adminToken?: string): Promise<Response> {
  const headers = new Headers(init?.headers)
  if (init?.body) headers.set('Content-Type', 'application/json')
  if (adminToken) headers.set('X-Admin-Token', adminToken)
  const res = await fetch(`${BASE}${path}`, { ...init, headers })
  if (res.ok) return res
  const text = detailText(await res.text())
  const suffix = text ? ` ${text}` : ''
  switch (res.status) {
    case 503:
      throw new Error('知识库未启用：后端需设置 RAG_ENABLED=true')
    case 403:
      throw new Error(
        text.includes('administration is disabled')
          ? '后端未配置 RAG_ADMIN_TOKEN，管理操作已禁用；请联系运维或使用 CLI'
          : '管理员令牌无效，请在管理员区域重新输入',
      )
    case 409:
      throw new Error(`知识库已存在或该库已在同步中：${text}`)
    case 422:
      throw new Error(`参数校验失败：${text}`)
    case 413:
      throw new Error('请求体过大')
    case 404:
      throw new Error(`知识库或文档不存在：${text}`)
    default:
      throw new Error(`${res.status}${suffix}`)
  }
}

async function kbJson<T>(path: string, init?: RequestInit, adminToken?: string): Promise<T> {
  return (await kbFetch(path, init, adminToken)).json() as Promise<T>
}

export const listKbs = (): Promise<KbSummary[]> => kbJson<KbSummary[]>('/kbs')

export const getKb = (name: string): Promise<KbDetail> =>
  kbJson<KbDetail>(`/kbs/${encodeURIComponent(name)}`)

export const createKb = (body: KbCreateInput, adminToken: string): Promise<KbSummary> =>
  kbJson<KbSummary>('/kbs', { method: 'POST', body: JSON.stringify(body) }, adminToken)

export const syncKb = async (name: string, adminToken: string): Promise<void> => {
  await kbFetch(`/kbs/${encodeURIComponent(name)}/sync`, { method: 'POST' }, adminToken)
}

export const listDocuments = (name: string): Promise<KbDocument[]> =>
  kbJson<KbDocument[]>(`/kbs/${encodeURIComponent(name)}/documents`)

export const readDocument = (name: string, docId: string, offset: number, limit = 6000) => {
  const q = new URLSearchParams({ offset: String(offset), limit: String(limit) })
  return kbJson<KbDocumentPage>(
    `/kbs/${encodeURIComponent(name)}/documents/${encodeURIComponent(docId)}?${q}`,
  )
}

export async function streamChat(
  threadId: string,
  message: string,
  onEvent: (ev: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  await fetchEventSource(`${BASE}/threads/${threadId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
    signal,
    openWhenHidden: true,
    async onopen(res) {
      if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
    },
    onmessage(msg) {
      if (!msg.event) return
      onEvent({ event: msg.event, data: JSON.parse(msg.data) } as StreamEvent)
    },
    onerror(err) {
      // Rethrow so the library does not retry the POST.
      throw err
    },
  })
}
