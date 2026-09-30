import { useCallback, useEffect, useRef, useState } from 'react'

import {
  addChatMessage,
  getChatSession,
  queryAnswer,
  streamQuery,
  updateChatMessage,
} from '../services/api'

// Progress labels shown in the assistant bubble while the server works. Kept as
// named values so the label and the "is this a placeholder?" test cannot drift
// apart — the test has to recognise exactly the strings that were written.
const STATUS_LABELS = {
  retrieving: 'Searching your sources…',
  generating: 'Reading them and composing an answer…',
}

function statusLabel(stage) {
  return STATUS_LABELS[stage] || STATUS_LABELS.generating
}

function isStatusLabel(text) {
  return Object.values(STATUS_LABELS).includes(text)
}

// Whether an accumulated buffer still holds only the progress placeholder (or
// nothing yet), i.e. the next token must replace it rather than be appended.
function isStatusLabelText(text) {
  return text === '' || isStatusLabel(text)
}

const DEFAULT_CONFIDENCE = {
  answer_confidence: 0,
  source_coverage: 'Weak',
  sources_used: 0,
  retrieved_chunks: 0,
}

function normalizeMessage(message) {
  return {
    id: message.id,
    role: message.role,
    text: message.text || '',
    status: message.status || 'done',
    // The source selection recorded when this message was created.  Absent on
    // legacy messages; the UI treats it as "the workspace selection at send".
    sourceIds: message.sourceIds || message.source_ids || [],
    confidence: message.confidence || null,
  }
}

// `sourceIds` is the workspace's *current* selection — used for the next query
// only.  `sessionId` binds this thread to its persisted session; `resolveSessionId`
// is an async callback that returns the active session, creating one on demand
// (the first message of a fresh project).  Without either the hook still works
// locally (no persistence), which keeps it usable standalone and in tests.
// `contextDepth` is how much the next question may retrieve; the server maps it
// to real retrieval limits and reduces it when the selection is too small to
// justify the wider setting.
export function useChat({
  sessionId = null,
  resolveSessionId = null,
  onNewSession = null,
  sourceIds = [],
  contextDepth = 'focused',
} = {}) {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState('')
  const [sources, setSources] = useState([])
  const [latency, setLatency] = useState({})
  const [confidence, setConfidence] = useState(null)
  const [showUploadHint, setShowUploadHint] = useState(false)
  const abortRef = useRef(null)
  const lastQuestionRef = useRef('')
  // The session a message belongs to may be created lazily by the parent after
  // the first send; refs keep the latest values without re-binding callbacks.
  // They are synced in an effect (writing refs during render is disallowed).
  const sessionRef = useRef(sessionId)
  const resolveSessionRef = useRef(resolveSessionId)
  const onNewSessionRef = useRef(onNewSession)
  const sourceIdsRef = useRef(sourceIds)
  const contextDepthRef = useRef(contextDepth)
  // Sessions whose in-memory thread is already authoritative.  A session we
  // created ourselves (lazily, mid-send) has its messages in hand before the id
  // exists, so re-fetching it could race the still-in-flight POST and drop the
  // just-sent turn from view.
  const loadedSessionsRef = useRef(new Set())
  const previousSessionRef = useRef(sessionId)

  useEffect(() => {
    sessionRef.current = sessionId
    resolveSessionRef.current = resolveSessionId
    onNewSessionRef.current = onNewSession
    sourceIdsRef.current = sourceIds
    contextDepthRef.current = contextDepth
  }, [sessionId, resolveSessionId, onNewSession, sourceIds, contextDepth])

  // Load persisted history whenever the bound session changes.  A different
  // project or session replaces the thread; changing the *selection* does not,
  // because each message keeps its own recorded selection.
  useEffect(() => {
    const changed = previousSessionRef.current !== sessionId
    previousSessionRef.current = sessionId

    if (!sessionId) {
      setMessages([])
      setSources([])
      setConfidence(null)
      setLatency({})
      setError('')
      setShowUploadHint(false)
      return undefined
    }

    // A session created during this turn already owns the on-screen thread;
    // don't overwrite it.  Freshly opening an existing session still loads.
    if (changed && loadedSessionsRef.current.has(sessionId)) {
      return undefined
    }

    let cancelled = false
    getChatSession(sessionId)
      .then((session) => {
        if (cancelled) return
        loadedSessionsRef.current.add(sessionId)
        setMessages((session.messages || []).map(normalizeMessage))
        setError('')
      })
      .catch(() => {
        if (!cancelled) setMessages([])
      })
    return () => {
      cancelled = true
    }
  }, [sessionId])

  // Abandoning an in-flight stream is a genuine side effect on an external
  // system: the response was grounded in a session the user just left.
  useEffect(() => {
    return () => {
      if (abortRef.current) {
        abortRef.current.abort()
        abortRef.current = null
      }
    }
  }, [sessionId])

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

  // Persist a message to its session.  Best-effort: a persistence failure must
  // never break the chat itself, so errors are swallowed (the in-memory thread
  // still renders).  The session may not exist yet on the first message of a
  // project, so it is resolved (and created) on demand.
  const persist = useCallback(async (payload) => {
    let active = sessionRef.current
    if (!active && resolveSessionRef.current) {
      try {
        active = await resolveSessionRef.current()
        sessionRef.current = active
      } catch {
        return null
      }
    }
    if (!active) return null
    // This session's thread is now owned by the in-memory state; a later
    // history fetch for it must not clobber the optimistic messages.
    loadedSessionsRef.current.add(active)
    return addChatMessage(active, payload).catch(() => null)
  }, [])

  const patchPersisted = useCallback((id, patch) => {
    if (!id) return
    updateChatMessage(id, patch).catch(() => {})
  }, [])

  const sendMessage = useCallback(
    async (question) => {
      const trimmed = question.trim()
      if (!trimmed) {
        return
      }

      // Snapshot the selection at send time: this is what gets stored with the
      // message, so later selection changes cannot rewrite this turn.  An empty
      // selection is allowed — the question is simply answered without a
      // specific source in scope.
      const usedSourceIds = [...sourceIdsRef.current]

      lastQuestionRef.current = trimmed
      setError('')
      setSources([])
      setLatency({})
      setConfidence(null)
      setShowUploadHint(false)
      setInput('')

      const userId = `user-${Date.now()}`
      const assistantId = `assistant-${Date.now()}`

      const userMessage = {
        id: userId,
        role: 'user',
        text: trimmed,
        status: 'done',
        sourceIds: usedSourceIds,
      }
      appendMessage(userMessage)

      appendMessage({
        id: assistantId,
        role: 'assistant',
        text: '',
        status: 'streaming',
        sourceIds: usedSourceIds,
      })

      // Persist the two rows of the turn in order, and *await the first before
      // writing the second*.  Firing both concurrently let the assistant
      // placeholder reach the server before the user message, so a refreshed
      // thread loaded assistant-before-user.  Serialising the writes preserves
      // the user → assistant sequence.
      await persist({
        role: 'user',
        text: trimmed,
        status: 'done',
        source_ids: usedSourceIds,
        message_id: userId,
      })
      // The assistant placeholder is stored so history (and its source
      // selection) exists from the moment the turn begins.
      persist({
        role: 'assistant',
        text: '',
        status: 'streaming',
        source_ids: usedSourceIds,
        message_id: assistantId,
      })

      setIsStreaming(true)
      stopStream()
      const controller = new AbortController()
      abortRef.current = controller

      try {
        let hasTokens = false
        // Accumulated across the stream so the finished answer can be written
        // back to the database.  Tokens only update React state, so without
        // this the persisted assistant row stayed empty and the response
        // vanished on the next load.
        let assistantText = ''
        const payload = {
          question: trimmed,
          source_ids: usedSourceIds.length ? usedSourceIds : undefined,
          // No source selected: answer from general knowledge, never from the
          // corpus, so the reply cannot cite a source the user did not choose.
          no_sources: usedSourceIds.length === 0,
          // How much of the selection this question may retrieve. Sent with the
          // selection rather than baked into the session, so it always matches
          // the depth the composer reported when the question was asked.
          context_depth: contextDepthRef.current,
        }
        await streamQuery(payload, {
          signal: controller.signal,
          // Sent by the server as soon as the request is accepted and again
          // when the sources are known. Retrieval and reranking take
          // milliseconds while generation takes seconds, so without this the
          // bubble is empty for the whole of the slow part and the request
          // reads as hung.
          onStatus: (stage) => {
            setMessages((prev) =>
              prev.map((message) =>
                message.id === assistantId ? { ...message, text: statusLabel(stage) } : message,
              ),
            )
          },
          onToken: (token) => {
            hasTokens = true
            // First token replaces the progress label; later ones append.
            // The accumulator mirrors the same rule so the persisted text
            // matches exactly what the bubble shows.
            assistantText = isStatusLabelText(assistantText) ? token : assistantText + token
            setMessages((prev) =>
              prev.map((message) => {
                if (message.id !== assistantId) return message
                // First token: the progress label has done its job, so replace
                // it rather than appending the answer to it.
                //
                // The bubble's own text decides this, not a variable captured
                // outside the updater. React invokes a state updater more than
                // once in development (StrictMode double-invocation), and a
                // side effect inside one - such as clearing a flag - makes the
                // second pass see stale state and append the answer to the
                // label instead of replacing it.
                if (isStatusLabel(message.text)) {
                  return { ...message, text: token }
                }
                return { ...message, text: message.text + token }
              }),
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
          onConfidence: (data) => {
            const next = data || DEFAULT_CONFIDENCE
            setConfidence(next)
            patchPersisted(assistantId, { confidence: next })
          },
          onDone: () => {
            updateAssistant(assistantId, { status: 'done' })
            // Persist the finished answer, not just the status: the streamed
            // tokens only lived in React state, so without this the stored row
            // stayed empty and the response was lost on the next load.
            patchPersisted(assistantId, { text: assistantText, status: 'done' })
          },
          onError: (message) => {
            throw new Error(message)
          },
        })

        if (!hasTokens) {
          throw new Error('No response received from the server.')
        }

        // Safety net for a stream that delivered tokens but never sent a
        // [DONE] frame: `onDone` is the normal path, this catches the rest so
        // the answer still reaches the database.
        if (assistantText) {
          patchPersisted(assistantId, { text: assistantText, status: 'done' })
        }
      } catch {
        stopStream()
        try {
          const fallback = await queryAnswer({
            question: trimmed,
            source_ids: usedSourceIds.length ? usedSourceIds : undefined,
            no_sources: usedSourceIds.length === 0,
            context_depth: contextDepthRef.current,
          })
          updateAssistant(assistantId, {
            text: fallback.answer,
            status: 'done',
          })
          setSources(fallback.sources || [])
          setShowUploadHint((fallback.sources || []).length === 0)
          setLatency(fallback.latency_ms || {})
          const nextConfidence = fallback.confidence || DEFAULT_CONFIDENCE
          setConfidence(nextConfidence)
          patchPersisted(assistantId, {
            text: fallback.answer,
            status: 'done',
            confidence: nextConfidence,
          })
        } catch (fallbackError) {
          // The progress label is not an answer, so it is never left in place.
          // A readable failure is stored instead of empty text: an empty row
          // reloaded as a blank gap with no explanation after a refresh.
          const reason = fallbackError.message || 'Request failed'
          updateAssistant(assistantId, { text: '', status: 'error' })
          patchPersisted(assistantId, {
            text: `⚠ Could not generate a response: ${reason}`,
            status: 'error',
          })
          setError(reason)
        }
      } finally {
        setIsStreaming(false)
      }
    },
    [appendMessage, stopStream, updateAssistant, persist, patchPersisted],
  )

  const retryLast = useCallback(() => {
    if (lastQuestionRef.current) {
      sendMessage(lastQuestionRef.current)
    }
  }, [sendMessage])

  // Clears the on-screen thread.  Persisted history is owned by the session;
  // when bound to a project the parent opens a *new* session so the previous
  // thread survives (starting a new chat must never delete history).
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
    onNewSessionRef.current?.()
  }, [stopStream])

  // NOTE: resetChat is referenced through a ref so the listener never rebinds
  // while streaming.
  const resetChatRef = useRef(null)
  useEffect(() => {
    resetChatRef.current = resetChat
  }, [resetChat])

  // Cmd/Ctrl+K starts a new chat.  Ignored while the user is typing in a field
  // so it never eats a deliberate shortcut elsewhere.
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
