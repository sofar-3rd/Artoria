import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import 'highlight.js/styles/github-dark.css'
import type { Message } from '../types'
import ReasoningBlock from './ReasoningBlock'
import ToolCallCard from './ToolCallCard'

export default function MessageBubble({ message, streaming = false }: { message: Message; streaming?: boolean }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl bg-blue-600 px-4 py-2 text-white">
          {message.content}
        </div>
      </div>
    )
  }
  return (
    <div className="max-w-full">
      {message.reasoning && (
        <ReasoningBlock
          text={message.reasoning}
          active={streaming && !message.content && !message.tool_calls?.length}
        />
      )}
      {message.tool_calls?.map((tc) => <ToolCallCard key={tc.id} call={tc} />)}
      {message.content && (
        <div className="prose prose-sm max-w-none prose-pre:bg-gray-900">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
            {message.content}
          </ReactMarkdown>
        </div>
      )}
    </div>
  )
}
