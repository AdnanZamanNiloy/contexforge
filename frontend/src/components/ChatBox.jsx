import { useRef, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import MessageBubble from './MessageBubble'

// The context meter used to live under the composer.  It is a readout of the
// *sidebar* selection, so it now sits at the foot of the sidebar next to the
// controls that change that selection — see Home.jsx.

export default function ChatBox({
  messages,
  input,
  onInputChange,
  onSend,
  isStreaming,
  error,
  onRetry,
  uploadHint,
  sourceCount = null,
  focusRequest = 0,
}) {
  const MAX_TEXTAREA_HEIGHT = 200
  const textareaRef = useRef(null)
  const messagesEndRef = useRef(null)
  const [isOverflowing, setIsOverflowing] = useState(false)
  const hasMessages = messages.length > 0

  const handleSubmit = (e) => {
    e.preventDefault()
    if (input.trim() && !isStreaming) {
      onSend(input)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  useEffect(() => {
    if (textareaRef.current) {
      const element = textareaRef.current
      textareaRef.current.style.height = 'auto'
      const nextHeight = Math.min(element.scrollHeight, MAX_TEXTAREA_HEIGHT)
      element.style.height = nextHeight + 'px'
      setIsOverflowing(element.scrollHeight > MAX_TEXTAREA_HEIGHT)
    }
  }, [input])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (focusRequest > 0) textareaRef.current?.focus()
  }, [focusRequest])

  const textareaBase =
    'chat-composer-input flex-1 min-w-0 resize-none bg-transparent border-none outline-none ' +
    'focus:outline-none focus-visible:outline-none focus:ring-0 ' +
    'text-[#f2f2f2] placeholder-[#8b949e] ' +
    'text-[0.95rem] leading-relaxed py-2 ' +
    'disabled:opacity-60 disabled:cursor-not-allowed'

  const sendBtnBase =
    'flex-none p-2.5 rounded-full ' +
    'bg-[#4377FD] ' +
    'text-[#101010] font-semibold ' +
    'disabled:opacity-40 disabled:cursor-not-allowed ' +
    'transition-all duration-200 ' +
    'hover:brightness-110 ' +
    'cursor-pointer'

  const inputArea = (
    <>
      <form onSubmit={handleSubmit}>
        <div
          className="flex items-center gap-3 rounded-full pl-6 pr-2 py-2
            bg-[#1a1a1a]
            border border-[#3d3a39]
            transition-all duration-200
            focus-within:border-[rgba(67,119,253,0.6)]
            focus-within:bg-[#1e1e1e]"
        >
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question or create something"
            rows={1}
            className={textareaBase}
            style={{ overflowY: isOverflowing ? 'auto' : 'hidden' }}
            disabled={isStreaming}
            aria-label="Ask a question or create something"
          />
          {sourceCount !== null && sourceCount !== undefined ? (
            <span className="flex-none text-xs text-[#8b949e] whitespace-nowrap">
              {sourceCount} source{sourceCount === 1 ? '' : 's'}
            </span>
          ) : null}
          <motion.button
            type="submit"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            disabled={isStreaming || !input.trim()}
            className={sendBtnBase}
            aria-label="Send message"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 19V5M5 12l7-7 7 7" />
            </svg>
          </motion.button>
        </div>
      </form>
      {sourceCount === 0 ? (
        <p className="text-center text-xs text-[#c9a227] mt-4">
          No source selected — answers come from general knowledge only. Select a source in the
          sidebar to ground the answer in it.
        </p>
      ) : (
        <p className="text-center text-xs text-[#8b949e] mt-4">
          ContextForge can make mistakes. Please verify important information.
        </p>
      )}
    </>
  )

  if (!hasMessages) {
    return (
      <motion.section
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5 }}
        className="flex flex-col items-center flex-1 min-h-0"
      >
        <div className="flex-1 min-h-[8vh]" />

        <div className="w-full max-w-[720px] mx-auto px-2 text-center">
          <motion.h1
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1, ease: 'easeOut' }}
            className="text-[2.4rem] sm:text-[3rem] font-normal tracking-tight text-[#ffffff] leading-[1.15] mb-4"
          >
            What would you like to explore?
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2, ease: 'easeOut' }}
            className="text-[#8b949e] text-base sm:text-lg leading-relaxed max-w-[520px] mx-auto"
          >
            Forge documents, repositories, web pages, and YouTube URLs into one intelligent
            conversation. Ask across every source at once and get answers grounded in your
            knowledge.
          </motion.p>
        </div>

        <div className="flex-1" />

        <div className="w-full max-w-[768px] mx-auto px-2 pb-8">{inputArea}</div>
      </motion.section>
    )
  }

  return (
    <motion.section
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className="flex flex-col flex-1 min-h-0"
    >
      <div className="flex-1 overflow-y-auto space-y-4 mb-5 pr-6 scroll-smooth">
        <AnimatePresence>
          {messages.map((message, index) => (
            <motion.div
              key={message.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: Math.min(index * 0.04, 0.4) }}
            >
              <MessageBubble
                role={message.role}
                title="ContextForge"
                text={message.text}
                status={message.status}
              />
            </motion.div>
          ))}
        </AnimatePresence>

        <div ref={messagesEndRef} />

        {error ? (
          <div
            className="flex items-center justify-between gap-3 px-5 py-3.5 rounded-[16px]
              bg-[rgba(139,148,158,0.1)] border border-[rgba(139,148,158,0.3)]
              text-[#bdbdbd] text-sm"
          >
            <span>{error}</span>
            <button
              onClick={onRetry}
              className="px-4 py-1.5 rounded-full text-xs font-medium
                bg-[rgba(255,255,255,0.05)] text-[#f2f2f2]
                border border-[#3d3a39]
                hover:bg-[rgba(255,255,255,0.1)] transition-colors cursor-pointer"
            >
              Retry
            </button>
          </div>
        ) : null}

        {uploadHint ? (
          <div
            className="rounded-[20px] border border-[#3d3a39]
              bg-[#1a1a1a] p-5 space-y-2"
          >
            <div className="font-semibold text-sm text-white">
              No sources were used for this answer.
            </div>
            <p className="text-xs text-[#8b949e] leading-relaxed m-0">
              For grounded answers, upload a PDF or DOCX, paste a URL, or link a GitHub repo.
            </p>
            <div className="flex flex-wrap gap-2">
              {['PDF', 'DOCX', 'URL', 'GitHub Repo'].map((tag) => (
                <span
                  key={tag}
                  className="px-2.5 py-1 rounded-[9999px] text-[10px] font-mono
                    bg-[#242424] text-[#bdbdbd]
                    border border-[#3d3a39]"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <div className="sticky bottom-0 pr-6">
        <div className="mx-auto w-full max-w-[768px]">{inputArea}</div>
      </div>
    </motion.section>
  )
}
