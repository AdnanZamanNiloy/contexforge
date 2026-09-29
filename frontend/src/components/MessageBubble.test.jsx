import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'

import MessageBubble from './MessageBubble'

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

function assistant(text) {
  return { role: 'assistant', text, status: 'done' }
}

describe('citation markers', () => {
  it('renders a numbered marker as an interactive chip', () => {
    render(<MessageBubble {...assistant('Accuracy is 97.06% [1].')} />)
    const chip = screen.getByLabelText('Citation to source 1')
    expect(chip).toBeTruthy()
    expect(chip.textContent).toBe('1')
  })

  it('keeps the surrounding prose intact', () => {
    render(<MessageBubble {...assistant('Accuracy is 97.06% [1] in testing.')} />)
    expect(screen.getByText(/Accuracy is 97\.06%/)).toBeTruthy()
    expect(screen.getByText(/in testing\./)).toBeTruthy()
  })

  it('renders one chip per marker in a multi-source answer', () => {
    render(<MessageBubble {...assistant('Loads a pipeline [1] and validates input [2][3].')} />)
    expect(screen.getAllByLabelText('Citation to source 1')).toHaveLength(1)
    expect(screen.getAllByLabelText('Citation to source 2')).toHaveLength(1)
    expect(screen.getAllByLabelText('Citation to source 3')).toHaveLength(1)
  })

  it('leaves an answer without markers as ordinary prose', () => {
    render(<MessageBubble {...assistant('No citations appear in this answer at all.')} />)
    expect(screen.queryByLabelText(/Citation to source/)).toBeNull()
  })

  it('does not convert an array subscript into a citation', () => {
    // The backend strips markers pointing at sources that do not exist, so a
    // bare number reaching the renderer is a real reference. A subscript is
    // glued to an identifier and must survive as text.
    render(<MessageBubble {...assistant('The value lives at model[0] in the frame.')} />)
    expect(screen.getByText(/model\[0\]/)).toBeTruthy()
    expect(screen.queryByLabelText(/Citation to source 0/)).toBeNull()
  })

  it('renders markers inside list items', () => {
    render(<MessageBubble {...assistant('- first point [1]\n- second point [2]')} />)
    expect(screen.getByLabelText('Citation to source 1')).toBeTruthy()
    expect(screen.getByLabelText('Citation to source 2')).toBeTruthy()
  })

  it('exposes the source number to assistive technology', () => {
    render(<MessageBubble {...assistant('The model reports 97.06% [2].')} />)
    const chip = screen.getByRole('button', { name: 'Citation to source 2' })
    expect(chip.getAttribute('title')).toBe('Source 2')
  })
})
