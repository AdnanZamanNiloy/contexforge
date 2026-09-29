import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import ToolSourcePicker from './ToolSourcePicker'

const SOURCES = [
  { id: 'repo:a/x', title: 'a/x' },
  { id: 'repo:b/y', title: 'b/y' },
]

describe('ToolSourcePicker', () => {
  it('is always shown, even for a single source, so a choice is required', () => {
    render(<ToolSourcePicker sources={SOURCES.slice(0, 1)} value="" onChange={vi.fn()} />)
    const select = screen.getByLabelText(/select the source this tool analyses/i)
    // Starts on the placeholder, not silently on the only source.
    expect(select).toHaveValue('')
    expect(screen.getByRole('option', { name: /select a source/i })).toBeInTheDocument()
  })

  it('lists the project sources and reports a change', async () => {
    const onChange = vi.fn()
    const actor = userEvent.setup()
    render(<ToolSourcePicker sources={SOURCES} value="repo:a/x" onChange={onChange} />)

    const select = screen.getByLabelText(/select the source this tool analyses/i)
    expect(select).toHaveValue('repo:a/x')

    await actor.selectOptions(select, 'repo:b/y')
    expect(onChange).toHaveBeenCalledWith('repo:b/y')
  })
})
