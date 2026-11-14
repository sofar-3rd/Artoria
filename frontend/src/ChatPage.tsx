import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from './api'
import { applyEvent } from './reducer'
import { navigate } from './router'
import type { Message, Thread } from './types'
import ChatView from './components/ChatView'
import InputBox from './components/InputBox'
import Sidebar from './components/Sidebar'

export default function ChatPage() {
  const [threads, setThreads] = useState<Thread[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  // Messages per thread, so a background run keeps updating its own thread.
  const [chats, setChats] = useState<Record<string, Message[]>>({})
  const [streamingIds, setStreamingIds] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const ctrls = useRef<Map<string, AbortController>>(new Map())
  const activeRef = useRef<string | null>(null)
  activeRef.current = activeId

  const messages = activeId ? (chats[activeId] ?? []) : []
  const streaming = activeId !== null && streamingIds.has(activeId)

  const refreshThreads = useCallback(async () => {
    setThreads(await api.listThreads())
  }, [])

  useEffect(() => {
    refreshThreads().catch((e) => setError(String(e)))
  }, [refreshThreads])

  // Explicit stop (stop button, thread deletion): aborts only that thread's run.
  const stopThread = useCallback((id: string | null) => {
    if (id) ctrls.current.get(id)?.abort()
  }, [])

  const newChat = () => {
    setActiveId(null)
    setError(null)
  }

  const selectThread = async (id: string) => {
    if (id === activeId) return
    setError(null)
    setActiveId(id)
    // A running thread already holds the live messages; do not overwrite them.
    if (ctrls.current.has(id)) return
    try {
      const loaded = await api.getMessages(id)
      if (!ctrls.current.has(id)) setChats((prev) => ({ ...prev, [id]: loaded }))
    } catch (e) {
      setError(String(e))
    }
  }

  const removeThread = async (id: string) => {
    if (!window.confirm('删除这个会话?')) return
    try {
      stopThread(id)
      await api.deleteThread(id)
      setChats((prev) => {
        const { [id]: _removed, ...rest } = prev
        return rest
      })
      if (id === activeId) newChat()
      await refreshThreads()
    } catch (e) {
      setError(String(e))
    }
  }

  const send = async (text: string) => {
    setError(null)
    let id = activeId
    if (!id) {
      try {
        const thread = await api.createThread()
        id = thread.id
        setActiveId(id)
        setThreads((prev) => [thread, ...prev])
      } catch (e) {
        setError(String(e))
        return
      }
    }
    const threadId = id
    const patch = (fn: (m: Message[]) => Message[]) =>
      setChats((prev) => ({ ...prev, [threadId]: fn(prev[threadId] ?? []) }))
    const setRunning = (on: boolean) =>
      setStreamingIds((prev) => {
        const next = new Set(prev)
        if (on) next.add(threadId)
        else next.delete(threadId)
        return next
      })
    const report = (msg: string) => {
      if (activeRef.current === threadId) setError(msg)
    }

    patch((prev) => [...prev, { role: 'user', content: text }])

    const ctrl = new AbortController()
    ctrls.current.set(threadId, ctrl)
    setRunning(true)
    try {
      await api.streamChat(
        threadId,
        text,
        (ev) => {
          if (ctrl.signal.aborted) return
          if (ev.event === 'error') report(ev.data.message)
          else patch((prev) => applyEvent(prev, ev))
        },
        ctrl.signal,
      )
    } catch (e) {
      if (!ctrl.signal.aborted) report(String(e))
    } finally {
      if (ctrls.current.get(threadId) === ctrl) ctrls.current.delete(threadId)
      setRunning(false)
      refreshThreads().catch(() => {})
    }
  }

  return (
    <div className="flex h-screen bg-gray-50 text-gray-900">
      <Sidebar
        threads={threads}
        activeId={activeId}
        onSelect={selectThread}
        onNew={newChat}
        onDelete={removeThread}
        onOpenTraces={() => navigate(activeId ? `/traces?thread=${activeId}` : '/traces')}
        onOpenKbs={() => navigate('/kbs')}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <ChatView messages={messages} streaming={streaming} />
        {error && (
          <div className="mx-auto w-full max-w-3xl px-4 pb-2 text-sm text-red-600">{error}</div>
        )}
        <InputBox streaming={streaming} onSend={send} onStop={() => stopThread(activeId)} />
      </main>
    </div>
  )
}
