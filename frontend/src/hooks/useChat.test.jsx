import { describe, it, expect } from 'vitest'
import { render, act } from '@testing-library/react'

import { useChat } from './useChat'

// Minimal probe component so we can drive the hook through real DOM events.
function Probe({ onReady }) {
  const chat = useChat()
  onReady(chat)
  return <div data-testid="messages">{chat.messages.length}</div>
}

function mountChat() {
  let chat
  render(
    <Probe
      onReady={(value) => {
        chat = value
      }}
    />,
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
