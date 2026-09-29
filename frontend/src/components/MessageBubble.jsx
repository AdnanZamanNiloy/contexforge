import React, { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// A citation marker, e.g. "[1]". Must not match a subscript such as "model[0]":
// the backend already skips those, so the same rule is applied here rather than
// trusting upstream. A marker stands on its own; a subscript is glued to an
// identifier. "]" is an allowed lead so adjacent markers like "[1][2]" both
// match, which is the form the model emits most often.
const CITATION = /(^|[\s([{'"\]-])\[(\d{1,2})\]/g

function CitationMarker({ index }) {
  const [active, setActive] = useState(false)
  return (
    <button
      type="button"
      onMouseEnter={() => setActive(true)}
      onMouseLeave={() => setActive(false)}
      onFocus={() => setActive(true)}
      onBlur={() => setActive(false)}
      title={`Source ${index}`}
      aria-label={`Citation to source ${index}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        minWidth: '1.15em',
        height: '1.15em',
        margin: '0 0.15em',
        padding: '0 0.25em',
        borderRadius: '4px',
        border: '1px solid rgba(255,255,255,0.18)',
        background: active ? 'rgba(255,255,255,0.18)' : 'rgba(255,255,255,0.08)',
        color: 'rgba(255,255,255,0.82)',
        fontSize: '0.68em',
        fontWeight: '600',
        lineHeight: 1,
        verticalAlign: 'super',
        cursor: 'pointer',
      }}
    >
      {index}
    </button>
  )
}

/**
 * Replace "[n]" markers with interactive chips while leaving the rest of the
 * text untouched.
 *
 * ReactMarkdown hands plain text through as a single string child, so the
 * marker substitution happens here rather than in a remark plugin. Splitting on
 * the match keeps every non-marker fragment as its own key, which is what stops
 * React from re-rendering the whole answer when a chip is hovered.
 */
function withCitationChips(content) {
  if (!content || !content.includes('[')) {
    return content
  }
  const parts = []
  let lastIndex = 0
  let match
  CITATION.lastIndex = 0
  while ((match = CITATION.exec(content)) !== null) {
    // The capture group is the character preceding the bracket; it is part of
    // the match but not part of the marker, so the start offset is shifted by
    // its length to keep the surrounding text in order.
    const lead = match[1] || ''
    const markerStart = match.index + lead.length
    if (markerStart > lastIndex) {
      parts.push(content.slice(lastIndex, markerStart))
    }
    parts.push(<CitationMarker key={`cite-${markerStart}`} index={match[2]} />)
    lastIndex = markerStart + match[0].length - lead.length
    // Rewind one character so the closing bracket can serve as the lead for an
    // adjacent marker. Without this, "[2][3]" only ever yields [2], because
    // the scan resumes past the bracket that [3] needs to be recognised by.
    CITATION.lastIndex = Math.max(0, lastIndex - 1)
  }
  if (parts.length === 0) {
    return content
  }
  if (lastIndex < content.length) {
    parts.push(content.slice(lastIndex))
  }
  return parts
}

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

/**
 * Walk rendered markdown children, substituting chips into plain text only.
 *
 * Returns the children unchanged when they hold no marker, so the common case
 * (an answer with no citations) costs one `includes` check per string node and
 * renders exactly as before.
 */
function renderWithChips(children) {
  let found = false
  React.Children.forEach(children, (child) => {
    if (typeof child === 'string' && child.includes('[')) {
      found = true
    }
  })
  if (!found) {
    return children
  }
  return React.Children.map(children, (child) =>
    typeof child === 'string' ? withCitationChips(child) : child,
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
        // Plain text is where citation markers live, so the chips are built
        // here. Code spans and links deliberately pass through untouched - a
        // marker inside `arr[0]` is a subscript, not a citation.
        p: ({ node: _node, children }) => <p>{renderWithChips(children)}</p>,
        li: ({ node: _node, children }) => <li>{renderWithChips(children)}</li>,
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
    <div className="px-1 py-1">
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
