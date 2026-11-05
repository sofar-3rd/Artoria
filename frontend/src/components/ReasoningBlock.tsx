interface Props {
  text: string
  // True while the model is still thinking; the block stays open to show progress.
  active: boolean
}

export default function ReasoningBlock({ text, active }: Props) {
  return (
    <details open={active} className="my-2 rounded-lg border border-dashed border-gray-300 bg-gray-50 text-sm">
      <summary className="cursor-pointer px-3 py-2 text-gray-500">
        {active ? '思考中...' : '思考过程'}
      </summary>
      <div className="max-h-64 overflow-y-auto whitespace-pre-wrap border-t border-gray-200 px-3 py-2 text-xs text-gray-500">
        {text}
      </div>
    </details>
  )
}
