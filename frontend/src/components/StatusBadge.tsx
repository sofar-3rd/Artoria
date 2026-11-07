const STYLE: Record<string, string> = {
  ok: 'bg-green-100 text-green-700',
  error: 'bg-red-100 text-red-700',
  cancelled: 'bg-amber-100 text-amber-700',
}

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs ${STYLE[status] ?? 'bg-gray-100 text-gray-600'}`}>
      {status}
    </span>
  )
}
