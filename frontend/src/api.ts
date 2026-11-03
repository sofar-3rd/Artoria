import { fetchEventSource } from '@microsoft/fetch-event-source'
import type { Message, StreamEvent, Thread } from './types'

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
