import { useCallback, useEffect, useState } from 'react'
import * as api from '../api'
import { fmtMs, fmtNum, fmtTime } from '../format'
import { navigate } from '../router'
import StatusBadge from '../components/StatusBadge'
import Timeline from '../components/Timeline'
import type { TurnDetail } from '../types'

const Stat = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded-lg border border-gray-200 bg-white px-3 py-2">
    <div className="text-xs text-gray-500">{label}</div>
    <div className="text-sm font-medium">{value}</div>
  </div>
)

export default function TraceDetailPage({ id }: { id: string }) {
  const [turn, setTurn] = useState<TurnDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      setTurn(await api.getTurn(id))
    } catch (e) {
      setTurn(null)
      setError(String(e))
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  const back = () => (history.length > 1 ? history.back() : navigate('/traces'))

  return (
    <div className="mx-auto h-screen max-w-6xl space-y-4 overflow-y-auto px-4 py-6">
      <div className="flex items-center gap-3">
        <button className="text-sm text-blue-600 hover:underline" onClick={back}>
          &larr; 返回列表
        </button>
        <button
          className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-100"
          onClick={load}
        >
          刷新
        </button>
      </div>
      {error && <div className="text-sm text-red-600">{error}</div>}
      {turn && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-lg font-semibold">{turn.thread_title}</h1>
            <StatusBadge status={turn.status} />
            <span className="text-sm text-gray-500">{fmtTime(turn.started_at)}</span>
            <button
              className="text-sm text-blue-600 hover:underline"
              onClick={() => navigate(`/traces?thread=${turn.thread_id}`)}
            >
              该会话的全部 turn
            </button>
          </div>
          {turn.error && (
            <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {turn.error}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="总耗时" value={fmtMs(turn.duration_ms)} />
            <Stat label="TTFT" value={fmtMs(turn.ttft_ms)} />
            <Stat label="首个正文" value={fmtMs(turn.first_content_ms)} />
            <Stat label="模型" value={turn.model ?? '-'} />
            <Stat label="输入 tokens" value={fmtNum(turn.input_tokens)} />
            <Stat label="输出 tokens" value={fmtNum(turn.output_tokens)} />
            <Stat label="总 tokens" value={fmtNum(turn.total_tokens)} />
            <Stat label="模型调用 / 工具" value={`${turn.llm_calls} / ${turn.tool_calls_count}`} />
          </div>
          <Timeline turn={turn} />
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500">
                <tr>
                  <th className="px-3 py-2">#</th>
                  <th className="px-3 py-2">工具</th>
                  <th className="px-3 py-2">状态</th>
                  <th className="px-3 py-2 text-right">开始偏移</th>
                  <th className="px-3 py-2 text-right">耗时</th>
                  <th className="px-3 py-2 text-right">结果字符数</th>
                  <th className="px-3 py-2">参数</th>
                </tr>
              </thead>
              <tbody>
                {turn.tools.map((t) => (
                  <tr key={t.id} className="border-t border-gray-100 align-top">
                    <td className="px-3 py-2">{t.seq + 1}</td>
                    <td className="px-3 py-2 font-medium">{t.name}</td>
                    <td className="px-3 py-2">
                      <StatusBadge status={t.status} />
                      {t.error && <div className="mt-1 text-xs text-red-600">{t.error}</div>}
                    </td>
                    <td className="px-3 py-2 text-right">{fmtMs(t.started_offset_ms)}</td>
                    <td className="px-3 py-2 text-right">{fmtMs(t.duration_ms)}</td>
                    <td className="px-3 py-2 text-right">{fmtNum(t.result_chars)}</td>
                    <td className="px-3 py-2">
                      <pre className="max-w-md overflow-x-auto whitespace-pre-wrap text-xs text-gray-600">
                        {JSON.stringify(t.args, null, 2)}
                      </pre>
                    </td>
                  </tr>
                ))}
                {turn.tools.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-3 py-6 text-center text-gray-400">
                      本次没有调用工具
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
