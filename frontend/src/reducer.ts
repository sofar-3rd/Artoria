import type { Message, StreamEvent } from './types'

const hasResolvedCall = (m: Message) =>
  (m.tool_calls ?? []).some((tc) => tc.result !== null)

// Mirrors the backend history view: one assistant item per model step.
export function applyEvent(messages: Message[], ev: StreamEvent): Message[] {
  const last = messages[messages.length - 1]
  switch (ev.event) {
    case 'reasoning': {
      // Thinking belongs to the assistant item of the current model step.
      if (last?.role === 'assistant' && !last.content && !last.tool_calls?.length) {
        return [
          ...messages.slice(0, -1),
          { ...last, reasoning: (last.reasoning ?? '') + ev.data.text },
        ]
      }
      return [
        ...messages,
        { role: 'assistant', content: '', tool_calls: [], reasoning: ev.data.text },
      ]
    }
    case 'token': {
      if (last?.role === 'assistant' && !last.tool_calls?.length) {
        return [...messages.slice(0, -1), { ...last, content: last.content + ev.data.text }]
      }
      return [...messages, { role: 'assistant', content: ev.data.text, tool_calls: [] }]
    }
    case 'tool_call': {
      const call = { ...ev.data, result: null }
      if (last?.role === 'assistant' && !hasResolvedCall(last)) {
        return [
          ...messages.slice(0, -1),
          { ...last, tool_calls: [...(last.tool_calls ?? []), call] },
        ]
      }
      return [...messages, { role: 'assistant', content: '', tool_calls: [call] }]
    }
    case 'tool_result':
      return messages.map((m) =>
        m.role !== 'assistant' || !m.tool_calls
          ? m
          : {
              ...m,
              tool_calls: m.tool_calls.map((tc) =>
                tc.id === ev.data.id ? { ...tc, result: ev.data.result } : tc,
              ),
            },
      )
    default:
      return messages
  }
}
