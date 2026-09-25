import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

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
})
