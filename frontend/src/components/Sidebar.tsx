import type { Thread } from '../types'

interface Props {
  threads: Thread[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
}

export default function Sidebar({ threads, activeId, onSelect, onNew, onDelete }: Props) {
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-gray-200 bg-white">
      <div className="p-3">
        <button
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm hover:bg-gray-50"
          onClick={onNew}
        >
          + 新对话
        </button>
      </div>
      <ul className="flex-1 overflow-y-auto px-2 pb-2">
        {threads.map((t) => (
          <li
            key={t.id}
            className={`group flex cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-sm ${
              t.id === activeId ? 'bg-blue-50 text-blue-700' : 'hover:bg-gray-100'
            }`}
            onClick={() => onSelect(t.id)}
          >
            <span className="truncate">{t.title}</span>
            <button
              className="ml-2 hidden text-gray-400 hover:text-red-600 group-hover:block"
              title="删除"
              onClick={(e) => {
                e.stopPropagation()
                onDelete(t.id)
              }}
            >
              x
            </button>
          </li>
        ))}
      </ul>
    </aside>
  )
}
