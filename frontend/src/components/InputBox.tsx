import { useState } from 'react'

interface Props {
  streaming: boolean
  onSend: (text: string) => void
  onStop: () => void
}

export default function InputBox({ streaming, onSend, onStop }: Props) {
  const [text, setText] = useState('')

  const submit = () => {
    const value = text.trim()
    if (!value || streaming) return
    onSend(value)
    setText('')
  }

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <textarea
          className="max-h-40 min-h-[44px] flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 focus:border-blue-500 focus:outline-none"
          rows={1}
          placeholder="输入消息, Enter 发送, Shift+Enter 换行"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              submit()
            }
          }}
        />
        {streaming ? (
          <button
            className="h-[44px] rounded-lg bg-gray-800 px-4 text-white hover:bg-gray-700"
            onClick={onStop}
          >
            停止
          </button>
        ) : (
          <button
            className="h-[44px] rounded-lg bg-blue-600 px-4 text-white hover:bg-blue-500 disabled:opacity-50"
            disabled={!text.trim()}
            onClick={submit}
          >
            发送
          </button>
        )}
      </div>
    </div>
  )
}
