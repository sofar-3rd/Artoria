import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from './api'
import { applyEvent } from './reducer'
import type { Message, Thread } from './types'
import ChatView from './components/ChatView'
import InputBox from './components/InputBox'
import Sidebar from './components/Sidebar'

export default function App() {
  const [threads, setThreads] = useState<Thread[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const refreshThreads = useCallback(async () => {
    setThreads(await api.listThreads())
  }, [])

  useEffect(() => {
    refreshThreads().catch((e) => setError(String(e)))
  }, [refreshThreads])

  const stop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  const newChat = () => {
    stop()
    setActiveId(null)
    setMessages([])
    setError(null)
  }

  const selectThread = async (id: string) => {
    if (id === activeId) return
    stop()
    setError(null)
    setActiveId(id)
    setMessages([])
    try {
      setMessages(await api.getMessages(id))
    } catch (e) {
      setError(String(e))
    }
  }

  const removeThread = async (id: string) => {
    if (!window.confirm('删除这个会话?')) return
    try {
      await api.deleteThread(id)
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
    setMessages((prev) => [...prev, { role: 'user', content: text }])

    const ctrl = new AbortController()
    abortRef.current = ctrl
    setStreaming(true)
    try {
      await api.streamChat(
        id,
        text,
        (ev) => {
          if (ctrl.signal.aborted) return
          if (ev.event === 'error') setError(ev.data.message)
          else setMessages((prev) => applyEvent(prev, ev))
        },
        ctrl.signal,
      )
    } catch (e) {
      if (!ctrl.signal.aborted) setError(String(e))
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null
      setStreaming(false)
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
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <ChatView messages={messages} streaming={streaming} />
        {error && (
          <div className="mx-auto w-full max-w-3xl px-4 pb-2 text-sm text-red-600">{error}</div>
        )}
        <InputBox streaming={streaming} onSend={send} onStop={stop} />
      </main>
    </div>
  )
}
