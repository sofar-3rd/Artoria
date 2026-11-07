import { buildBars, buildMarkers, ticks } from '../timeline'
import type { BarKind } from '../timeline'
import { fmtMs } from '../format'
import type { TurnDetail } from '../types'

const COLOR: Record<BarKind, string> = {
  model: 'bg-blue-400',
  tool: 'bg-violet-500',
  other: 'bg-gray-400',
}

export default function Timeline({ turn }: { turn: TurnDetail }) {
  const total = Math.max(turn.duration_ms, 1)
  const bars = buildBars(turn)
  const markers = buildMarkers(turn)
  const pct = (ms: number) => `${(ms / total) * 100}%`

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="relative ml-40 mb-2 h-4 text-xs text-gray-400">
        {ticks(total).map((t) => (
          <span
            key={t}
            className={`absolute whitespace-nowrap ${t === ticks(total).at(-1) ? '-translate-x-full' : '-translate-x-1/2'}`}
            style={{ left: pct(t) }}
          >
            {fmtMs(t)}
          </span>
        ))}
      </div>
      <div className="relative">
        {markers.map((m) => (
          <div
            key={m.key}
            className="absolute top-0 bottom-0 z-10 border-l border-dashed border-rose-400"
            style={{ left: `calc(10rem + (100% - 10rem) * ${m.at / total})` }}
            title={`${m.label}: ${fmtMs(m.at)}`}
          />
        ))}
        <div className="space-y-1.5">
          {bars.map((b) => (
            <div key={b.key} className="flex items-center text-xs">
              <div className="w-40 shrink-0 truncate pr-3 text-right text-gray-600" title={b.label}>
                {b.label}
              </div>
              <div className="relative h-5 flex-1 rounded bg-gray-50">
                <div
                  className={`absolute top-0 h-5 rounded ${COLOR[b.kind]} ${
                    b.status === 'cancelled' || b.status === 'error' ? 'opacity-60' : ''
                  } ${b.inferred ? 'border border-dashed border-gray-700' : ''}`}
                  style={{
                    left: pct(b.start),
                    width: `max(${pct(b.end - b.start)}, 2px)`,
                  }}
                  title={`${b.label}: ${fmtMs(b.end - b.start)} (${fmtMs(b.start)} - ${fmtMs(b.end)})${
                    b.inferred ? ' - inferred' : ''
                  }`}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="mt-3 ml-40 flex flex-wrap gap-4 text-xs text-gray-500">
        <span><i className="mr-1 inline-block h-2 w-3 rounded bg-blue-400" />model / other (inferred from gaps)</span>
        <span><i className="mr-1 inline-block h-2 w-3 rounded bg-violet-500" />tool</span>
        <span><i className="mr-1 inline-block h-3 border-l border-dashed border-rose-400" />TTFT / first content</span>
      </div>
    </div>
  )
}
