import { useCallback, useEffect, useState } from 'react'
import * as api from '../api'
import { fmtMs, fmtNum, fmtTime } from '../format'
import { navigate } from '../router'
import StatusBadge from '../components/StatusBadge'
import type { Thread, Turn, TurnStatus } from '../types'

const STATUSES: TurnStatus[] = ['ok', 'error', 'cancelled']

export default function TracesPage({ threadId }: { threadId: string | null }) {
  const [threads, setThreads] = useState<Thread[]>([])
  const [status, setStatus] = useState<TurnStatus | ''>('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.listThreads().then(setThreads).catch((e) => setError(String(e)))
  }, [])

  const load = useCallback(
    async (more: string | null) => {
      setLoading(true)
      setError(null)
      try {
        const page = await api.listTurns({
          status: status || undefined,
          threadId: threadId ?? undefined,
          cursor: more,
        })
        setTurns((prev) => (more ? [...prev, ...page.items] : page.items))
        setCursor(page.next_cursor)
      } catch (e) {
        setError(String(e))
      } finally {
        setLoading(false)
      }
    },
    [status, threadId],
  )

  useEffect(() => {
    load(null)
  }, [load])

  const setThreadFilter = (id: string) =>
    navigate(id ? `/traces?thread=${encodeURIComponent(id)}` : '/traces')

  return (
    <div className="mx-auto h-screen max-w-6xl overflow-y-auto px-4 py-6">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <button className="text-sm text-blue-600 hover:underline" onClick={() => navigate('/')}>
          &larr; 聊天
        </button>
        <h1 className="text-lg font-semibold">Traces</h1>
        <select
          className="rounded border border-gray-300 bg-white px-2 py-1 text-sm"
          value={threadId ?? ''}
          onChange={(e) => setThreadFilter(e.target.value)}
        >
          <option value="">全部会话</option>
          {threads.map((t) => (
            <option key={t.id} value={t.id}>
              {t.title}
            </option>
          ))}
        </select>
        <select
          className="rounded border border-gray-300 bg-white px-2 py-1 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value as TurnStatus | '')}
        >
          <option value="">全部状态</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <button
          className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-100 disabled:opacity-50"
          disabled={loading}
          onClick={() => load(null)}
        >
          刷新
        </button>
      </div>
      {error && <div className="mb-3 text-sm text-red-600">{error}</div>}
      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500">
            <tr>
              <th className="px-3 py-2">时间</th>
              <th className="px-3 py-2">会话</th>
              <th className="px-3 py-2">状态</th>
              <th className="px-3 py-2 text-right">耗时</th>
              <th className="px-3 py-2 text-right">TTFT</th>
              <th className="px-3 py-2 text-right">Tokens (in/out)</th>
              <th className="px-3 py-2 text-right">工具</th>
              <th className="px-3 py-2 text-right">模型调用</th>
              <th className="px-3 py-2">错误</th>
            </tr>
          </thead>
          <tbody>
            {turns.map((t) => (
              <tr
                key={t.id}
                className="cursor-pointer border-t border-gray-100 hover:bg-blue-50"
                onClick={() => navigate(`/traces/${t.id}`)}
              >
                <td className="whitespace-nowrap px-3 py-2">{fmtTime(t.started_at)}</td>
                <td className="max-w-48 truncate px-3 py-2" title={t.thread_title ?? ''}>
                  {t.thread_title}
                </td>
                <td className="px-3 py-2"><StatusBadge status={t.status} /></td>
                <td className="px-3 py-2 text-right">{fmtMs(t.duration_ms)}</td>
                <td className="px-3 py-2 text-right">{fmtMs(t.ttft_ms)}</td>
                <td className="px-3 py-2 text-right">
                  {fmtNum(t.input_tokens)} / {fmtNum(t.output_tokens)}
                </td>
                <td className="px-3 py-2 text-right">{t.tool_calls_count}</td>
                <td className="px-3 py-2 text-right">{t.llm_calls}</td>
                <td className="max-w-64 truncate px-3 py-2 text-red-600" title={t.error ?? ''}>
                  {t.error}
                </td>
              </tr>
            ))}
            {!loading && turns.length === 0 && (
              <tr>
                <td colSpan={9} className="px-3 py-8 text-center text-gray-400">
                  没有记录
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {cursor && (
        <div className="mt-3 text-center">
          <button
            className="rounded border border-gray-300 px-4 py-1.5 text-sm hover:bg-gray-100 disabled:opacity-50"
            disabled={loading}
            onClick={() => load(cursor)}
          >
            加载更多
          </button>
        </div>
      )}
    </div>
  )
}
