import { StrictMode } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, act } from '@testing-library/react'

// The streaming client is mocked so the token sequence is deterministic and the
// non-streaming fallback is never reached: the regression below is about how the
// hook folds tokens into the bubble, not about network behaviour.
const streamHandlers = { current: null }
vi.mock('../services/api', () => ({
  queryAnswer: vi.fn(async () => ({ answer: 'fallback', sources: [], latency_ms: {}, confidence: {} })),
  streamQuery: vi.fn(async (_payload, handlers) => {
    streamHandlers.current = handlers
    handlers.onStatus?.('retrieving')
    handlers.onStatus?.('generating')
    for (const token of ['A full-stack ', 'app']) {
      handlers.onToken?.(token)
    }
    handlers.onDone?.({ sources: [], latency_ms: {}, confidence: {} })
  }),
}))

import { useChat } from './useChat'

// Minimal probe component so we can drive the hook through real DOM events.
//
// StrictMode is not optional here. The application mounts inside it
// (src/main.jsx), and StrictMode invokes state updaters twice in development.
// The original bug only reproduced under that double invocation, so a test
// without it would pass against the broken code and prove nothing.
function Probe({ onReady }) {
  const chat = useChat()
  onReady(chat)
  return <div data-testid="messages">{chat.messages.length}</div>
}

function mountChat() {
  let chat
  render(
    <StrictMode>
      <Probe
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
