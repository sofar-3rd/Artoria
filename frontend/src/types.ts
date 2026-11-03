export interface Thread {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ToolCall {
  id: string
  name: string
  args: Record<string, unknown>
  result: string | null
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
  tool_calls?: ToolCall[]
}

export type StreamEvent =
  | { event: 'token'; data: { text: string } }
  | { event: 'tool_call'; data: { id: string; name: string; args: Record<string, unknown> } }
  | { event: 'tool_result'; data: { id: string; name: string; result: string } }
  | { event: 'done'; data: Record<string, never> }
  | { event: 'error'; data: { message: string } }
