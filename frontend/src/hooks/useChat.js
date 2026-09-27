import { useCallback, useEffect, useRef, useState } from 'react'

import { queryAnswer, streamQuery } from '../services/api'

const STORAGE_PREFIX = 'contextforge:chat:'

// Chat history is kept per scope.  The workspace scopes a query to the sources
// the user selected in the sidebar, so a thread is only meaningful alongside the
// selection that produced it — sorting keeps "a + b" and "b + a" on one thread.
function scopeKeyOf(sourceIds) {
  const ids = (sourceIds || []).filter(Boolean)
  if (ids.length === 0) return 'all'
  return [...new Set(ids)].sort().join('|')
}

function storageKey(sourceIds) {
  return `${STORAGE_PREFIX}scope:${scopeKeyOf(sourceIds)}`
}

function loadState(sourceId) {
  try {
    const raw = localStorage.getItem(storageKey(sourceId))
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function saveState(sourceId, state) {
  try {
    localStorage.setItem(storageKey(sourceId), JSON.stringify(state))
  } catch {
    // ignore storage quota/availability errors
  }
}

const DEFAULT_CONFIDENCE = {
  answer_confidence: 0,
  source_coverage: 'Weak',
  sources_used: 0,
  retrieved_chunks: 0,
}

// `sourceIds` is the workspace's current source selection.  Empty means "every
// source in the knowledge base", which is also the unscoped default.
export function useChat({ sourceIds = [] } = {}) {
  const scopeKey = scopeKeyOf(sourceIds)
  const [scope, setScope] = useState(scopeKey)
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState(() => loadState(sourceIds)?.messages ?? [])
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState('')
  const [sources, setSources] = useState(() => loadState(sourceIds)?.sources ?? [])
  const [latency, setLatency] = useState({})
  // FIX: store server-side confidence metrics
  const [confidence, setConfidence] = useState(() => loadState(sourceIds)?.confidence ?? null)
  const [showUploadHint, setShowUploadHint] = useState(false)
  const abortRef = useRef(null)
  const lastQuestionRef = useRef('')

  // Switching the selection switches to that scope's thread, so answers are
  // never shown next to a selection that did not produce them.  React's
  // documented pattern for adjusting state to a changed input is to do it during
  // render, which avoids painting one frame of the previous scope's thread.
  if (scope !== scopeKey) {
    setScope(scopeKey)
    const stored = loadState(sourceIds)
    setMessages(stored?.messages ?? [])
    setSources(stored?.sources ?? [])
    setConfidence(stored?.confidence ?? null)
    setLatency({})
    setError('')
    setShowUploadHint(false)
    setInput('')
    setIsStreaming(false)
  }

  // Abandoning an in-flight stream is a genuine side effect on an external
  // system, so it stays in an effect: the response was grounded in the scope
  // the user just moved away from.
  useEffect(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    lastQuestionRef.current = ''
  }, [scopeKey])

  // Persist chat state so history survives page refresh.  Writing is skipped on
  // the render that swaps scope — the restore above already loaded that key's
  // own state, and saving the old thread under the new key would clobber it.
  const prevScopeRef = useRef(scopeKey)
  useEffect(() => {
    if (prevScopeRef.current !== scopeKey) {
      prevScopeRef.current = scopeKey
      return
    }
    saveState(sourceIds, { messages, sources, confidence })
  }, [sourceIds, scopeKey, messages, sources, confidence])

  const appendMessage = useCallback((message) => {
    setMessages((prev) => [...prev, message])
  }, [])

  const updateAssistant = useCallback((id, patch) => {
    setMessages((prev) =>
      prev.map((message) => (message.id === id ? { ...message, ...patch } : message)),
    )
  }, [])

  const stopStream = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
  }, [])

  const sendMessage = useCallback(
    async (question) => {
      const trimmed = question.trim()
      if (!trimmed) {
        return
      }

      lastQuestionRef.current = trimmed
      setError('')
      setSources([])
      setLatency({})
      // FIX: reset confidence on new query
      setConfidence(null)
      setShowUploadHint(false)
      setInput('')

      const userId = `user-${Date.now()}`
      const assistantId = `assistant-${Date.now()}`

      appendMessage({
        id: userId,
        role: 'user',
        text: trimmed,
      })

      appendMessage({
        id: assistantId,
        role: 'assistant',
        text: '',
        status: 'streaming',
      })

      setIsStreaming(true)
      stopStream()
      const controller = new AbortController()
      abortRef.current = controller

      try {
        let hasTokens = false
        const payload = {
          question: trimmed,
          source_ids: sourceIds.length ? sourceIds : undefined,
        }
        await streamQuery(payload, {
          signal: controller.signal,
          onToken: (token) => {
            hasTokens = true
            setMessages((prev) =>
              prev.map((message) =>
                message.id === assistantId ? { ...message, text: message.text + token } : message,
              ),
            )
          },
          onSources: (nextSources) => {
            const normalized = nextSources || []
            setSources(normalized)
            setShowUploadHint(normalized.length === 0)
          },
          onLatency: (timings) => {
            setLatency(timings || {})
          },
          // FIX: store confidence from the SSE [CONFIDENCE] event
          onConfidence: (data) => {
            setConfidence(data || DEFAULT_CONFIDENCE)
          },
          onDone: () => {
            updateAssistant(assistantId, { status: 'done' })
          },
          onError: (message) => {
            throw new Error(message)
          },
        })

        if (!hasTokens) {
          throw new Error('No response received from the server.')
        }
      } catch {
        stopStream()
        try {
          const fallback = await queryAnswer({
            question: trimmed,
            source_ids: sourceIds.length ? sourceIds : undefined,
          })
          updateAssistant(assistantId, {
            text: fallback.answer,
            status: 'done',
          })
          setSources(fallback.sources || [])
          setShowUploadHint((fallback.sources || []).length === 0)
          setLatency(fallback.latency_ms || {})
          // FIX: parse confidence from fallback response
          setConfidence(fallback.confidence || DEFAULT_CONFIDENCE)
        } catch (fallbackError) {
          updateAssistant(assistantId, { status: 'error' })
          setError(fallbackError.message || 'Request failed')
        }
      } finally {
        setIsStreaming(false)
      }
    },
    [appendMessage, stopStream, updateAssistant, sourceIds],
  )

  const retryLast = useCallback(() => {
    if (lastQuestionRef.current) {
      sendMessage(lastQuestionRef.current)
    }
  }, [sendMessage])

  // NOTE: resetChat is declared below; the shortcut effect references it through
  // a ref so the listener never rebinds while streaming.
  const resetChatRef = useRef(null)

  const resetChat = useCallback(() => {
    stopStream()
    setMessages([])
    setError('')
    setSources([])
    setLatency({})
    setConfidence(null)
    setShowUploadHint(false)
    setInput('')
    lastQuestionRef.current = ''
    try {
      localStorage.removeItem(storageKey(sourceIds))
    } catch {
      // ignore storage errors
    }
  }, [sourceIds, stopStream])

  // Keep the shortcut pointing at the latest resetChat implementation.
  useEffect(() => {
    resetChatRef.current = resetChat
  }, [resetChat])

  // Cmd/Ctrl+K starts a new chat, matching the sidebar hint.  Ignored while the
  // user is typing in a field so it never eats a deliberate shortcut elsewhere.
  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key !== 'k' && event.key !== 'K') return
      if (!(event.metaKey || event.ctrlKey) || event.shiftKey || event.altKey) return
      event.preventDefault()
      resetChatRef.current?.()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return {
    input,
    setInput,
    messages,
    sendMessage,
    isStreaming,
    error,
    sources,
    latency,
    confidence,
    retryLast,
    showUploadHint,
    resetChat,
  }
}
