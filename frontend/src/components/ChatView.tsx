import { useEffect, useRef } from 'react'
import type { Message } from '../types'
import MessageBubble from './MessageBubble'

interface Props {
  messages: Message[]
  streaming: boolean
}

export default function ChatView({ messages, streaming }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const waiting = streaming && messages[messages.length - 1]?.role === 'user'

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
        {messages.length === 0 && (
          <div className="pt-24 text-center text-gray-400">有什么可以帮你的?</div>
        )}
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}
        {waiting && <div className="text-sm text-gray-400">思考中...</div>}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
