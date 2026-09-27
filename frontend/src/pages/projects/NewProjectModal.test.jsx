import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

import NewProjectModal from './NewProjectModal'

async function user() {
  const { default: userEvent } = await import('@testing-library/user-event')
  return userEvent.setup()
}

function stubCreateProject(capture) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, options = {}) => {
      if (String(url).endsWith('/projects') && (options.method || 'GET') === 'POST') {
        capture.body = JSON.parse(options.body)
        return {
          ok: true,
          status: 201,
          json: async () => ({
            id: 'proj_new',
            name: capture.body.name,
            description: capture.body.description,
            category: capture.body.category,
            cover: 'aurora',
            source_category: capture.body.source_category,
            source_ids: [],
            source_count: 0,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            last_opened_at: new Date().toISOString(),
          }),
        }
      }
      return { ok: true, status: 200, json: async () => ({}) }
    }),
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.stubGlobal('requestAnimationFrame', (cb) => setTimeout(cb, 0))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('NewProjectModal', () => {
  it('offers the three source families and defaults to Documents & Web', () => {
    render(<NewProjectModal open onClose={vi.fn()} onCreated={vi.fn()} />)

    expect(screen.getByRole('radiogroup', { name: /what will this project hold/i }))
    expect(screen.getByRole('radio', { name: /documents & web/i })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    expect(screen.getByRole('radio', { name: /youtube videos/i })).toHaveAttribute(
      'aria-checked',
      'false',
    )
    expect(screen.getByRole('radio', { name: /code repositories/i })).toHaveAttribute(
      'aria-checked',
      'false',
    )
  })

  it('creates the project with the selected family', async () => {
    const capture = {}
    stubCreateProject(capture)
    const onCreated = vi.fn()
    const u = await user()
    render(<NewProjectModal open onClose={vi.fn()} onCreated={onCreated} />)

    await u.click(screen.getByRole('radio', { name: /youtube videos/i }))
    await u.type(screen.getByLabelText(/project name/i), 'Talks')
    await u.click(screen.getByRole('button', { name: /^create project$/i }))

    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1))
    expect(capture.body.source_category).toBe('youtube')
    expect(capture.body.name).toBe('Talks')
    expect(onCreated.mock.calls[0][0].id).toBe('proj_new')
  })

  it('requires a name before creating', async () => {
    const u = await user()
    render(<NewProjectModal open onClose={vi.fn()} onCreated={vi.fn()} />)

    // The Create button stays disabled without a name; pressing Enter in the
    // empty name field surfaces the inline error instead.
    await u.click(screen.getByLabelText(/project name/i))
    await u.keyboard('{Enter}')
    expect(await screen.findByText(/give your project a name/i)).toBeInTheDocument()
  })
})
