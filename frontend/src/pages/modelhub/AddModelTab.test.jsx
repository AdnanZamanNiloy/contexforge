import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

import AddModelTab from './AddModelTab'

async function user() {
  const { default: userEvent } = await import('@testing-library/user-event')
  return userEvent.setup()
}

function stubApi({
  created = { id: 'm1', name: 'Test Model' },
  test = { ok: true, latency_ms: 42 },
} = {}) {
  return vi.stubGlobal(
    'fetch',
    vi.fn(async (url, options = {}) => {
      const path = String(url)
      const method = (options.method || 'GET').toUpperCase()
      if (path.endsWith('/models') && method === 'POST') {
        return { ok: true, status: 201, json: async () => created }
      }
      if (path.endsWith(`/models/${created.id}/test`) && method === 'POST') {
        return { ok: true, status: 200, json: async () => test }
      }
      return { ok: true, status: 200, json: async () => ({}) }
    }),
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('AddModelTab wizard', () => {
  it('walks type → runtime → details and hides Google for embeddings', async () => {
    const u = await user()
    render(<AddModelTab onCreated={vi.fn()} />)

    // Step 1: pick embedding, continue.
    await u.click(screen.getByRole('button', { name: /embedding/i }))
    await u.click(screen.getByRole('button', { name: /^continue$/i }))

    // Step 2: runtime choices are shown; continue to details.
    expect(screen.getByRole('button', { name: /hosted provider endpoint/i })).toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: /^continue$/i }))

    // Step 3: provider chips exclude Google for embeddings.
    expect(screen.getByRole('radiogroup', { name: /provider/i })).toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: /google gemini/i })).not.toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /voyage ai/i })).toBeInTheDocument()
    expect(screen.getByText(/dimensions are detected automatically/i)).toBeInTheDocument()
  })

  it('requires a name before creating', async () => {
    const u = await user()
    render(<AddModelTab onCreated={vi.fn()} />)

    await u.click(screen.getByRole('button', { name: /^continue$/i }))
    await u.click(screen.getByRole('button', { name: /^continue$/i }))
    await u.click(screen.getByRole('button', { name: /^add model$/i }))

    expect(await screen.findByText(/model name is required/i)).toBeInTheDocument()
  })

  it('creates the model and reports the connection on Add & Test', async () => {
    stubApi()
    const onCreated = vi.fn()
    const u = await user()
    render(<AddModelTab onCreated={onCreated} />)

    await u.click(screen.getByRole('button', { name: /^continue$/i }))
    await u.click(screen.getByRole('button', { name: /^continue$/i }))
    await u.type(screen.getByLabelText(/model name/i), 'Test Model')
    await u.type(screen.getByLabelText(/^model id$/i), 'gpt-4o-mini')
    await u.click(screen.getByRole('button', { name: /add & test/i }))

    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1))
    expect(await screen.findByText(/connected in 42 ms/i)).toBeInTheDocument()
  })

  it('resets an invalid Google provider when switching to embedding', async () => {
    const u = await user()
    render(<AddModelTab onCreated={vi.fn()} />)

    // Pick Google on the API path first via details step.
    await u.click(screen.getByRole('button', { name: /^continue$/i }))
    await u.click(screen.getByRole('button', { name: /^continue$/i }))
    await u.click(screen.getByRole('radio', { name: /google gemini/i }))
    expect(screen.getByRole('radio', { name: /google gemini/i })).toHaveAttribute(
      'aria-checked',
      'true',
    )

    // Go back to step 1 and switch to embedding: Google must be gone and the
    // selection must fall back to a valid provider.
    await u.click(screen.getByRole('button', { name: /model type/i }))
    await u.click(screen.getByRole('button', { name: /embedding/i }))
    await u.click(screen.getByRole('button', { name: /^continue$/i }))
    await u.click(screen.getByRole('button', { name: /^continue$/i }))
    expect(screen.queryByRole('radio', { name: /google gemini/i })).not.toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /^openai$/i })).toHaveAttribute('aria-checked', 'true')
  })
})
