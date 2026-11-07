import type { TurnDetail } from './types'

export type BarKind = 'model' | 'tool' | 'other'

export interface Bar {
  key: string
  kind: BarKind
  label: string
  start: number
  end: number
  status: string
  inferred: boolean
}

// Tool bars are real measurements; the gaps between them are attributed to the
// model (or to "other" once the turn has produced content) because no per-call
// model timing is recorded.
export function buildBars(turn: TurnDetail): Bar[] {
  const total = Math.max(turn.duration_ms, 1)
  const clamp = (v: number) => Math.min(Math.max(v, 0), total)
  const tools = turn.tools
    .map((t) => {
      const start = clamp(t.started_offset_ms)
      const end = clamp(start + (t.duration_ms ?? total - start))
      return { t, start, end }
    })
    .sort((a, b) => a.start - b.start || a.t.seq - b.t.seq)

  const bars: Bar[] = []
  // Merge overlapping tool intervals to find the idle gaps.
  const busy: [number, number][] = []
  for (const { start, end } of tools) {
    const last = busy[busy.length - 1]
    if (last && start <= last[1]) last[1] = Math.max(last[1], end)
    else busy.push([start, end])
  }
  let cursor = 0
  const gap = (from: number, to: number) => {
    if (to - from < 1) return
    bars.push({
      key: `gap-${from}`,
      kind: 'model',
      label: bars.length === 0 ? 'model' : 'model / other',
      start: from,
      end: to,
      status: turn.status,
      inferred: true,
    })
  }
  for (const [s, e] of busy) {
    gap(cursor, s)
    cursor = e
  }
  gap(cursor, total)
  for (const { t, start, end } of tools) {
    bars.push({
      key: t.id,
      kind: 'tool',
      label: t.name || 'tool',
      start,
      end,
      status: t.status,
      inferred: t.duration_ms === null,
    })
  }
  return bars.sort((a, b) => a.start - b.start || a.end - b.end)
}

export interface Marker {
  key: string
  label: string
  at: number
}

export function buildMarkers(turn: TurnDetail): Marker[] {
  const out: Marker[] = []
  if (turn.ttft_ms !== null) out.push({ key: 'ttft', label: 'TTFT', at: turn.ttft_ms })
  if (turn.first_content_ms !== null) {
    out.push({ key: 'content', label: 'first content', at: turn.first_content_ms })
  }
  return out
}

export function ticks(total: number, count = 5): number[] {
  return Array.from({ length: count + 1 }, (_, i) => Math.round((total * i) / count))
}
