import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

function MarkdownRenderer({ content }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        // Keep links from capturing the chat scroll; open in a new tab.
        a: ({ node: _node, ...props }) => (
          <a {...props} target="_blank" rel="noopener noreferrer" />
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  )
}

export default function MessageBubble({ role, text, status }) {
  if (role === 'user') {
    return (
      <div className="flex justify-end">
        <div
          className="max-w-[78%] rounded-[8px] px-4 py-3
            bg-[#1a1a1a]
            border border-[#3d3a39]"
        >
          <p className="text-base text-[#f2f2f2] leading-relaxed m-0 whitespace-pre-line">{text}</p>
        </div>
      </div>
    )
  }

  const isStreamingEmpty = status === 'streaming' && !text

  return (
    <div className="rounded-[8px] p-4">
      {isStreamingEmpty ? (
        <span className="inline-flex items-center gap-0.5 text-[#8b949e]">
          <span className="animate-pulse duration-1000">Thinking</span>
          <span className="animate-pulse duration-1000 delay-150">.</span>
          <span className="animate-pulse duration-1000 delay-300">.</span>
          <span className="animate-pulse duration-1000 delay-450">.</span>
        </span>
      ) : (
        <div className="font-sans text-base leading-relaxed text-[#f2f2f2] markdown-body">
          <MarkdownRenderer content={text || ''} />
        </div>
      )}
    </div>
  )
}
