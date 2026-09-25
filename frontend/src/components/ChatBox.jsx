import { useRef, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import MessageBubble from './MessageBubble'

export default function ChatBox({
  messages,
  input,
  onInputChange,
  onSend,
  isStreaming,
  error,
  onRetry,
  uploadHint,
  onNewChat,
}) {
  const MAX_TEXTAREA_HEIGHT = 200
  const textareaRef = useRef(null)
  const messagesEndRef = useRef(null)
  const [isOverflowing, setIsOverflowing] = useState(false)
  const hasMessages = messages.length > 0

  const threadTitle = hasMessages
    ? messages[0].text.length > 60
      ? messages[0].text.slice(0, 60) + '…'
      : messages[0].text
    : ''

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

  const textareaBase =
    'w-full resize-none rounded-2xl px-5 py-4 pr-14 overflow-y-hidden ' +
    'bg-[rgba(255,255,255,0.04)] ' +
    'border border-[rgba(255,255,255,0.08)] ' +
    'text-[#e6e7ea] placeholder-[#a6abb3] ' +
    'text-base leading-relaxed outline-none ' +
    'transition-all duration-200 ' +
    'focus:border-[rgba(122,162,247,0.4)] ' +
    'focus:bg-[rgba(255,255,255,0.06)] ' +
    'focus:shadow-[0_0_0_1px_rgba(122,162,247,0.2)] ' +
    'disabled:opacity-60 disabled:cursor-not-allowed'

  const sendBtnBase =
    'absolute right-2 bottom-2 p-2.5 rounded-xl ' +
    'bg-[linear-gradient(135deg,#7aa2f7,#9aa8ff)] ' +
    'text-[#0b1020] font-semibold ' +
    'disabled:opacity-40 disabled:cursor-not-allowed ' +
    'transition-all duration-200 ' +
    'hover:shadow-[0_0_20px_rgba(122,162,247,0.5)] ' +
    'cursor-pointer'

  const inputArea = (
    <>
      <form onSubmit={handleSubmit}>
        <div className="relative">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything about your documents..."
            rows={1}
            className={textareaBase}
            style={{ overflowY: isOverflowing ? 'auto' : 'hidden' }}
            disabled={isStreaming}
          />
          <motion.button
            type="submit"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            disabled={isStreaming || !input.trim()}
            className={sendBtnBase}
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
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </motion.button>
        </div>
      </form>
      <p className="text-center text-xs text-[#a6abb3] mt-4">
        ContextForge can make mistakes. Please verify important information.
      </p>
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
            className="text-[2.4rem] sm:text-[3rem] font-semibold tracking-tight text-white leading-[1.15] mb-4"
          >
            What would you like to explore?
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2, ease: 'easeOut' }}
            className="text-[#a6abb3] text-base sm:text-lg leading-relaxed max-w-[520px] mx-auto"
          >
            Forge documents, repositories, web pages, and YouTube URLs into one intelligent
            conversation. Ask across every source at once and get answers grounded in your
            knowledge.
          </motion.p>
        </div>

        <div className="flex-1" />

        <div className="w-full max-w-[720px] mx-auto px-2 pb-8">{inputArea}</div>
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
      <div className="flex items-start justify-between gap-4 mb-3 pr-6">
        <div className="min-w-0">
          <div className="text-[10px] tracking-[0.2em] uppercase text-[#a6abb3] mb-1.5">
            Active Thread
          </div>
          <h2 className="text-xl sm:text-2xl font-semibold text-white leading-tight truncate m-0">
            {threadTitle}
          </h2>
        </div>
        <button
          onClick={onNewChat}
          type="button"
          title="Start a new chat and clear this thread"
          aria-label="Start a new chat"
          disabled={!onNewChat}
          className="group inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold
            bg-[rgba(255,255,255,0.06)] text-[#e6e7ea]
            border border-[rgba(255,255,255,0.12)]
            cursor-pointer shrink-0
            hover:bg-[rgba(122,162,247,0.16)] hover:border-[rgba(122,162,247,0.45)]
            hover:text-white
            disabled:opacity-40 disabled:cursor-not-allowed
            transition-all duration-200"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="transition-transform duration-200 group-hover:-rotate-12"
            aria-hidden="true"
          >
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
          </svg>
          <span>New Chat</span>
          <kbd
            className="hidden sm:inline-block font-mono text-[0.62rem] leading-none px-1.5 py-1 rounded-md
              text-[#a6abb3] bg-[rgba(255,255,255,0.06)] border border-[rgba(255,255,255,0.1)]"
          >
            ⌘K
          </kbd>
        </button>
      </div>

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
            className="flex items-center justify-between gap-3 px-4 py-3 rounded-xl
              bg-[rgba(239,83,80,0.1)] border border-[rgba(239,83,80,0.3)]
              text-[#f5b5b4] text-sm"
          >
            <span>{error}</span>
            <button
              onClick={onRetry}
              className="px-3 py-1 rounded-lg text-xs font-medium
                bg-[rgba(255,255,255,0.08)] text-[#e6e7ea]
                border border-[rgba(255,255,255,0.12)]
                hover:bg-[rgba(255,255,255,0.14)] transition-colors cursor-pointer"
            >
              Retry
            </button>
          </div>
        ) : null}

        {uploadHint ? (
          <div
            className="rounded-xl border border-[rgba(122,162,247,0.3)]
              bg-[rgba(122,162,247,0.06)] p-4 space-y-2"
          >
            <div className="font-semibold text-sm text-white">
              No sources were used for this answer.
            </div>
            <p className="text-xs text-[#a6abb3] leading-relaxed m-0">
              For grounded answers, upload a PDF or DOCX, paste a URL, or link a GitHub repo.
            </p>
            <div className="flex flex-wrap gap-2">
              {['PDF', 'DOCX', 'URL', 'GitHub Repo'].map((tag) => (
                <span
                  key={tag}
                  className="px-2.5 py-1 rounded-full text-[10px] font-mono
                    bg-[rgba(122,162,247,0.12)] text-[#d6e8ff]
                    border border-[rgba(122,162,247,0.3)]"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <div className="sticky bottom-0 pr-6">{inputArea}</div>
    </motion.section>
  )
}
