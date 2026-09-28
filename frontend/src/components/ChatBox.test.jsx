import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'

import ChatBox from './ChatBox'
import { STUDIO_TOOLS } from './RepoStudio'

// jsdom does not implement scrollIntoView, which ChatBox calls on new messages.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

async function user() {
  const { default: userEvent } = await import('@testing-library/user-event')
  return userEvent.setup()
}

function baseProps(overrides = {}) {
  return {
    messages: [],
    input: '',
    onInputChange: vi.fn(),
    onSend: vi.fn(),
    isStreaming: false,
    error: null,
    onRetry: vi.fn(),
    uploadHint: false,
    onNewChat: vi.fn(),
    ...overrides,
  }
}

describe('ChatBox studio previews', () => {
  it('shows one preview card per studio tool when the thread is empty', async () => {
    const onSelect = vi.fn()
    const u = await user()
    render(<ChatBox {...baseProps()} studioPreviews={{ tools: STUDIO_TOOLS, onSelect }} />)

    for (const tool of STUDIO_TOOLS) {
      expect(screen.getByRole('button', { name: new RegExp(tool.label) })).toBeInTheDocument()
    }

    await u.click(screen.getByRole('button', { name: /repo chat/i }))
    expect(onSelect).toHaveBeenCalledWith('chat')
  })

  it('hides previews once messages exist and without studio tools', () => {
    const { rerender } = render(
      <ChatBox {...baseProps()} studioPreviews={{ tools: STUDIO_TOOLS, onSelect: vi.fn() }} />,
    )
    expect(screen.getByRole('group', { name: /studio previews/i })).toBeInTheDocument()

    rerender(
      <ChatBox
        {...baseProps({ messages: [{ id: 'u1', role: 'user', text: 'hi' }] })}
        studioPreviews={{ tools: STUDIO_TOOLS, onSelect: vi.fn() }}
      />,
    )
    expect(screen.queryByRole('group', { name: /studio previews/i })).not.toBeInTheDocument()

    rerender(<ChatBox {...baseProps()} studioPreviews={null} />)
    expect(screen.queryByRole('group', { name: /studio previews/i })).not.toBeInTheDocument()
  })

  it('focuses the composer when focusRequest bumps (Repo Chat shortcut)', () => {
    const { rerender } = render(<ChatBox {...baseProps()} focusRequest={0} />)
    const input = screen.getByLabelText(/ask a question or create something/i)
    expect(document.activeElement).not.toBe(input)

    rerender(<ChatBox {...baseProps()} focusRequest={1} />)
    expect(document.activeElement).toBe(input)
  })
})
