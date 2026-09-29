import { StrictMode } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, act } from '@testing-library/react'

// The streaming client is mocked so the token sequence is deterministic and the
// non-streaming fallback is never reached: the regression below is about how the
// hook folds tokens into the bubble, not about network behaviour.
const streamHandlers = { current: null }
const addCalls = { current: [] }
const patchCalls = { current: [] }
// Set by the failure test to make both the stream and the fallback reject.
const failEverything = { current: false }
vi.mock('../services/api', () => ({
  queryAnswer: vi.fn(async () => {
    if (failEverything.current) throw new Error('Provider unreachable')
    return {
      answer: 'fallback',
      sources: [],
      latency_ms: {},
      confidence: {},
    }
  }),
  streamQuery: vi.fn(async (_payload, handlers) => {
    if (failEverything.current) throw new Error('Provider unreachable')
    streamHandlers.current = handlers
    handlers.onStatus?.('retrieving')
    handlers.onStatus?.('generating')
    for (const token of ['A full-stack ', 'app']) {
      handlers.onToken?.(token)
    }
    handlers.onDone?.({ sources: [], latency_ms: {}, confidence: {} })
  }),
  // Persistence is mocked out: these tests exercise the in-memory thread and
  // the exact per-message source selection handed to the API.
  getChatSession: vi.fn(async (id) => ({ id, project_id: 'p', messages: [] })),
  addChatMessage: vi.fn(async (id, payload) => {
    addCalls.current.push({ sessionId: id, payload })
    return { id: payload.message_id, ...payload }
  }),
  updateChatMessage: vi.fn(async (id, payload) => {
    patchCalls.current.push({ id, payload })
    return { id, ...payload }
  }),
}))

import { useChat } from './useChat'

// Minimal probe component so we can drive the hook through real DOM events.
//
// StrictMode is not optional here. The application mounts inside it
// (src/main.jsx), and StrictMode invokes state updaters twice in development.
// The original bug only reproduced under that double invocation, so a test
// without it would pass against the broken code and prove nothing.
function Probe({ onReady, options = {} }) {
  const chat = useChat(options)
  onReady(chat)
  return <div data-testid="messages">{chat.messages.length}</div>
}

function mountChat(options = {}) {
  // Chat now requires an explicit source selection; default one so tests that
  // are not about that requirement still exercise the send path.
  const withSource = { sourceIds: ['src-a'], ...options }
  let chat
  render(
    <StrictMode>
      <Probe
        options={withSource}
        onReady={(value) => {
          chat = value
        }}
      />
    </StrictMode>,
  )
  return () => chat
}

function press(key, opts = {}) {
  act(() => {
    window.dispatchEvent(
      new KeyboardEvent('keydown', {
        key,
        metaKey: false,
        ctrlKey: false,
        shiftKey: false,
        altKey: false,
        bubbles: true,
        cancelable: true,
        ...opts,
      }),
    )
  })
}

describe('useChat New Chat shortcut', () => {
  it('exposes resetChat', () => {
    const chat = mountChat()
    expect(typeof chat().resetChat).toBe('function')
  })

  it('clears the thread on Cmd+K', () => {
    const chat = mountChat()
    act(() => {
      chat().sendMessage('hello world')
    })
    // sendMessage appends the user message immediately.
    expect(chat().messages.length).toBeGreaterThan(0)

    press('k', { metaKey: true })
    expect(chat().messages).toHaveLength(0)
  })

  it('clears the thread on Ctrl+K', () => {
    const chat = mountChat()
    act(() => {
      chat().sendMessage('another question')
    })
    expect(chat().messages.length).toBeGreaterThan(0)

    press('k', { ctrlKey: true })
    expect(chat().messages).toHaveLength(0)
  })

  it('ignores plain "k" so typing is never hijacked', () => {
    const chat = mountChat()
    act(() => {
      chat().sendMessage('keep me')
    })
    const before = chat().messages.length

    press('k')
    expect(chat().messages).toHaveLength(before)
  })

  it('ignores modified shortcuts such as Cmd+Shift+K', () => {
    const chat = mountChat()
    act(() => {
      chat().sendMessage('keep me too')
    })
    const before = chat().messages.length

    press('k', { metaKey: true, shiftKey: true })
    expect(chat().messages).toHaveLength(before)
  })
})

describe('chat with no source selected', () => {
  it('sends the message unscoped instead of blocking it', async () => {
    addCalls.current = []
    const getChat = mountChat({ sessionId: 'chat_1', sourceIds: [] })
    await act(async () => {
      await getChat().sendMessage('hello without a source')
    })
    // The turn still runs and is persisted; its source selection is simply empty.
    const userMsg = addCalls.current.find((c) => c.payload.role === 'user')
    expect(userMsg).toBeTruthy()
    expect(userMsg.payload.source_ids).toEqual([])
    expect(userMsg.payload.text).toBe('hello without a source')
  })
})

describe('per-message source selection persistence', () => {
  // Each turn must record the selection that was active when it was sent, so
  // changing the workspace selection mid-session never rewrites history.
  it('stores the current selection on both the user and assistant messages', async () => {
    addCalls.current = []
    const chat = mountChat({ sessionId: 'chat_1', sourceIds: ['src-a'] })
    await act(async () => {
      await chat().sendMessage('first question')
    })

    const persisted = addCalls.current.map((call) => call.payload)
    const userMsg = persisted.find((p) => p.role === 'user')
    const assistantMsg = persisted.find((p) => p.role === 'assistant')
    expect(userMsg.source_ids).toEqual(['src-a'])
    expect(assistantMsg.source_ids).toEqual(['src-a'])
    expect(addCalls.current.every((call) => call.sessionId === 'chat_1')).toBe(true)
  })

  it('persists the user message before the assistant placeholder', async () => {
    addCalls.current = []
    const chat = mountChat({ sessionId: 'chat_1', sourceIds: ['src-a'] })
    await act(async () => {
      await chat().sendMessage('ordering matters')
    })
    // Regression: both rows used to be written concurrently, letting the
    // assistant land first so a refreshed thread showed assistant-before-user.
    const roles = addCalls.current.map((call) => call.payload.role)
    expect(roles.indexOf('user')).toBeLessThan(roles.indexOf('assistant'))
    expect(roles[0]).toBe('user')
  })

  it('records a different selection for a later turn', async () => {
    addCalls.current = []
    const chat = mountChat({ sessionId: 'chat_1', sourceIds: ['src-a'] })
    await act(async () => {
      await chat().sendMessage('turn one')
    })

    // The workspace selection grows before the second turn.
    const chat2 = mountChat({ sessionId: 'chat_1', sourceIds: ['src-a', 'src-b'] })
    await act(async () => {
      await chat2().sendMessage('turn two')
    })

    const byText = new Map(
      addCalls.current
        .filter((c) => c.payload.role === 'user')
        .map((c) => [c.payload.text, c.payload]),
    )
    expect(byText.get('turn one').source_ids).toEqual(['src-a'])
    expect(byText.get('turn two').source_ids).toEqual(['src-a', 'src-b'])
  })

  it('resolves (and reuses) a session when none is bound yet', async () => {
    addCalls.current = []
    const ensureSession = vi.fn(async () => 'chat_lazy')
    const chat = mountChat({ resolveSessionId: ensureSession, sourceIds: ['src-x'] })
    await act(async () => {
      await chat().sendMessage('hello')
    })
    expect(ensureSession).toHaveBeenCalled()
    expect(addCalls.current[0].sessionId).toBe('chat_lazy')
    expect(addCalls.current[0].payload.source_ids).toEqual(['src-x'])
  })

  it('persists the streamed assistant text, not just the status', async () => {
    addCalls.current = []
    patchCalls.current = []
    const chat = mountChat({ sessionId: 'chat_1', sourceIds: ['src-a'] })
    await act(async () => {
      await chat().sendMessage('what is this?')
    })

    // Regression: the assistant row was written as an empty placeholder and only
    // ever patched with `status`, so the answer lived in React state alone and
    // came back blank after a refresh.
    const assistantPatch = patchCalls.current.find(
      (call) => typeof call.payload?.text === 'string' && call.payload.text.length > 0,
    )
    expect(assistantPatch).toBeTruthy()
    // The progress label must not be baked into the stored answer.
    expect(assistantPatch.payload.text).toBe('A full-stack app')
    expect(assistantPatch.payload.status).toBe('done')
  })

  it('persists a readable failure instead of an empty errored message', async () => {
    addCalls.current = []
    patchCalls.current = []
    failEverything.current = true
    try {
      const chat = mountChat({ sessionId: 'chat_1', sourceIds: ['src-a'] })
      await act(async () => {
        await chat().sendMessage('this will fail')
      })

      // Regression: the failed turn was stored with empty text, so after a
      // refresh it reloaded as a blank gap with no explanation.
      const errorPatch = patchCalls.current.find((call) => call.payload?.status === 'error')
      expect(errorPatch).toBeTruthy()
      expect(errorPatch.payload.text).toMatch(/could not generate a response/i)
      expect(errorPatch.payload.text).not.toBe('')
    } finally {
      failEverything.current = false
    }
  })
})

describe('streaming progress label', () => {
  // Regression: the label was cleared by a side effect inside a state updater.
  // React invokes an updater twice in development, and on the second pass the
  // flag was already false, so the answer was appended to the label instead of
  // replacing it. Users saw "Reading them and composing an answer…This is a
  // small full-stack web application…".
  it('replaces the progress label with the first token', async () => {
    const chat = mountChat()
    await act(async () => {
      await chat().sendMessage('what is this project?')
    })

    const assistant = chat().messages.find((m) => m.role === 'assistant')
    expect(assistant).toBeTruthy()
    expect(assistant.text).not.toMatch(/Searching your sources|composing an answer/)
    expect(assistant.text).toContain('A full-stack app')
  })

  it('never leaves a status label anywhere in the answer', async () => {
    const chat = mountChat()
    await act(async () => {
      await chat().sendMessage('describe the stack')
    })
    for (const message of chat().messages) {
      expect(message.text).not.toMatch(/Searching your sources|composing an answer/)
    }
  })
})
