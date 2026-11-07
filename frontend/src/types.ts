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
  reasoning?: string
}

export type StreamEvent =
  | { event: 'reasoning'; data: { text: string } }
  | { event: 'token'; data: { text: string } }
  | { event: 'tool_call'; data: { id: string; name: string; args: Record<string, unknown> } }
  | { event: 'tool_result'; data: { id: string; name: string; result: string } }
  | { event: 'done'; data: Record<string, never> }
  | { event: 'error'; data: { message: string } }

export type TurnStatus = 'ok' | 'error' | 'cancelled'

export interface Turn {
  id: string
  thread_id: string
  thread_title: string | null
  status: TurnStatus
  started_at: string
  duration_ms: number
  ttft_ms: number | null
  first_content_ms: number | null
  llm_calls: number
  tool_calls_count: number
  input_tokens: number | null
  output_tokens: number | null
  total_tokens: number | null
  model: string | null
  error: string | null
}

export interface TurnTool {
  id: string
  tool_call_id: string | null
  name: string
  args: Record<string, unknown> | null
  status: string
  seq: number
  started_offset_ms: number
  duration_ms: number | null
  result_chars: number | null
  error: string | null
}

export interface TurnDetail extends Turn {
  tools: TurnTool[]
}

export interface TurnPage {
  items: Turn[]
  next_cursor: string | null
}
