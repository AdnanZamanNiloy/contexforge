import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'

import ChatBox from './ChatBox'
import { STUDIO_TOOLS } from './RepoStudio'

// jsdom does not implement scrollIntoView, which ChatBox calls on new messages.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

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

describe('ChatBox does not duplicate the studio tools', () => {
  it('offers no tool grid, because the Studio rail already carries them', () => {
    // The chat used to render a row of the same four tool cards as the rail
    // beside it. Two identical entry points to the same four views is one too
    // many, and the chat one is the one that goes.
    render(<ChatBox {...baseProps()} />)
    expect(screen.queryByRole('group', { name: /studio previews/i })).not.toBeInTheDocument()
    for (const tool of STUDIO_TOOLS) {
      expect(screen.queryByRole('button', { name: new RegExp(tool.label) })).not.toBeInTheDocument()
    }
  })

  it('focuses the composer when focusRequest bumps (Repo Chat shortcut)', () => {
    const { rerender } = render(<ChatBox {...baseProps()} focusRequest={0} />)
    const input = screen.getByLabelText(/ask a question or create something/i)
    expect(document.activeElement).not.toBe(input)

    rerender(<ChatBox {...baseProps()} focusRequest={1} />)
    expect(document.activeElement).toBe(input)
  })
})
