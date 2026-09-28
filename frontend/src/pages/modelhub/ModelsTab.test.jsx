import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

import ModelsTab from './ModelsTab'

const BASE_MODEL = {
  id: 'm1',
  name: 'GPT-4o mini',
  model_type: 'llm',
  runtime: 'api',
  provider: 'openai',
  model_id: 'gpt-4o-mini',
  base_url: null,
  dimension: null,
  local_backend: null,
  device: null,
  has_api_key: true,
  status: 'ready',
  status_detail: null,
}

const EMBEDDING_MODEL = {
  ...BASE_MODEL,
  id: 'e1',
  name: 'Small embeddings',
  model_type: 'embedding',
  model_id: 'text-embedding-3-small',
  dimension: 1536,
}

describe('ModelsTab', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function stubTestEndpoint(response, { ok = true, status = 200 } = {}) {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok, status, json: async () => response })),
    )
  }

  async function user() {
    const { default: userEvent } = await import('@testing-library/user-event')
    return userEvent.setup()
  }

  it('shows the empty state when no models exist', () => {
    render(<ModelsTab models={[]} onChanged={vi.fn()} onDeleted={vi.fn()} />)
    expect(screen.getByText(/no models configured yet/i)).toBeInTheDocument()
  })

  it('renders one card per model with type, provider and status', () => {
    render(
      <ModelsTab models={[BASE_MODEL, EMBEDDING_MODEL]} onChanged={vi.fn()} onDeleted={vi.fn()} />,
    )
    expect(screen.getByText('GPT-4o mini')).toBeInTheDocument()
    expect(screen.getByText('Small embeddings')).toBeInTheDocument()
    expect(screen.getAllByText('OpenAI').length).toBe(2)
    expect(screen.getAllByText('Connected').length).toBe(2)
  })

  it('shows the detected embedding dimension', () => {
    render(<ModelsTab models={[EMBEDDING_MODEL]} onChanged={vi.fn()} onDeleted={vi.fn()} />)
    expect(screen.getByText('1536 dims')).toBeInTheDocument()
  })

  it('filters to only embedding models', async () => {
    const { userEvent } = await import('@testing-library/user-event')
    const user = userEvent.setup()
    render(
      <ModelsTab models={[BASE_MODEL, EMBEDDING_MODEL]} onChanged={vi.fn()} onDeleted={vi.fn()} />,
    )
    await user.click(screen.getByRole('button', { name: 'Embedding' }))
    expect(screen.getByText('Small embeddings')).toBeInTheDocument()
    expect(screen.queryByText('GPT-4o mini')).not.toBeInTheDocument()
  })

  it('shows a custom provider name instead of the generic Custom label', async () => {
    const { userEvent } = await import('@testing-library/user-event')
    const user = userEvent.setup()
    const custom = {
      ...BASE_MODEL,
      id: 'm9',
      name: 'Local 70B',
      provider: 'custom',
      provider_label: 'My vLLM server',
    }
    render(<ModelsTab models={[custom]} onChanged={vi.fn()} onDeleted={vi.fn()} />)
    expect(screen.getByText('My vLLM server')).toBeInTheDocument()
    expect(screen.queryByText('Custom (OpenAI-compatible)')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Edit' }))
    expect(screen.getByLabelText(/custom provider name/i)).toHaveValue('My vLLM server')
  })

  it('reports a successful test as a toast and leaves the card intact', async () => {
    stubTestEndpoint({ ok: true, latency_ms: 231 })
    const u = await user()
    render(<ModelsTab models={[BASE_MODEL]} onChanged={vi.fn()} onDeleted={vi.fn()} />)

    await u.click(screen.getByRole('button', { name: /^test$/i }))

    expect(await screen.findByText('GPT-4o mini · 231 ms')).toBeInTheDocument()
    // The card keeps its actions — nothing expanded inline.
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
  })

  it('surfaces API errors like 429 as an error toast without touching the card', async () => {
    stubTestEndpoint(
      { detail: '429 Too Many Requests: rate limit exceeded' },
      { ok: false, status: 429 },
    )
    const u = await user()
    render(<ModelsTab models={[BASE_MODEL]} onChanged={vi.fn()} onDeleted={vi.fn()} />)

    await u.click(screen.getByRole('button', { name: /^test$/i }))

    expect(await screen.findByText('Test failed')).toBeInTheDocument()
    expect(await screen.findByText(/429 Too Many Requests/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument()
  })

  it('opens Edit in a modal and closes it on Cancel', async () => {
    const u = await user()
    render(<ModelsTab models={[BASE_MODEL]} onChanged={vi.fn()} onDeleted={vi.fn()} />)

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await u.click(screen.getByRole('button', { name: 'Edit' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('Edit model')
    await u.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    // The card grid is untouched.
    expect(screen.getByText('GPT-4o mini')).toBeInTheDocument()
  })

  it('reveals the typed key when the eye toggle is clicked', async () => {
    const u = await user()
    render(<ModelsTab models={[BASE_MODEL]} onChanged={vi.fn()} onDeleted={vi.fn()} />)

    await u.click(screen.getByRole('button', { name: 'Edit' }))
    const keyInput = screen.getByLabelText('API Key')
    expect(keyInput).toHaveAttribute('type', 'password')

    await u.type(keyInput, 'sk-new-secret')
    await u.click(screen.getByRole('button', { name: /show api key/i }))
    expect(keyInput).toHaveAttribute('type', 'text')
    expect(keyInput).toHaveValue('sk-new-secret')

    await u.click(screen.getByRole('button', { name: /hide api key/i }))
    expect(keyInput).toHaveAttribute('type', 'password')
  })
})
