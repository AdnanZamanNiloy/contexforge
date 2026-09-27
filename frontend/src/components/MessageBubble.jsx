import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={copied ? 'Copied' : 'Copy answer'}
      title={copied ? 'Copied' : 'Copy answer'}
      className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs
        text-[#8b949e] border border-transparent
        transition-colors hover:text-[#f2f2f2] hover:border-[#3d3a39] hover:bg-[#1a1a1a]"
    >
      {copied ? (
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M20 6L9 17l-5-5" />
        </svg>
      ) : (
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="9" y="9" width="11" height="11" rx="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      )}
      <span>{copied ? 'Copied' : 'Copy'}</span>
    </button>
  )
}

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
          className="max-w-[78%] rounded-[20px] rounded-br-[8px] px-5 py-3.5
            bg-[#222222]
            border border-[rgba(255,255,255,0.07)]"
        >
          <p className="text-base text-[#f2f2f2] leading-relaxed m-0 whitespace-pre-line">{text}</p>
        </div>
      </div>
    )
  }

  const isStreamingEmpty = status === 'streaming' && !text

  return (
    <div className="rounded-[20px] rounded-tl-[8px] px-5 py-4 bg-[rgba(255,255,255,0.025)] border border-[rgba(255,255,255,0.06)]">
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

      {!isStreamingEmpty && text && status !== 'streaming' ? (
        <div className="mt-2 flex">
          <CopyButton text={text} />
        </div>
      ) : null}
    </div>
  )
}
