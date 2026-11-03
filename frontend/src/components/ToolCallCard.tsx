import type { ToolCall } from '../types'

export default function ToolCallCard({ call }: { call: ToolCall }) {
  const running = call.result === null
  return (
    <details className="my-2 rounded-lg border border-gray-200 bg-white text-sm">
      <summary className="flex cursor-pointer items-center gap-2 px-3 py-2">
        <span className="font-mono font-medium">{call.name}</span>
        <span className={running ? 'text-amber-600' : 'text-green-600'}>
          {running ? '运行中...' : '完成'}
        </span>
      </summary>
      <div className="space-y-2 border-t border-gray-100 px-3 py-2 font-mono text-xs">
        <div>
          <div className="mb-1 text-gray-500">参数</div>
          <pre className="overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(call.args, null, 2)}
          </pre>
        </div>
        {call.result !== null && (
          <div>
            <div className="mb-1 text-gray-500">结果</div>
            <pre className="overflow-x-auto whitespace-pre-wrap">{call.result}</pre>
          </div>
        )}
      </div>
    </details>
  )
}
