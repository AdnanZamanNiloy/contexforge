import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import ModelHubPage from './ModelHubPage'

const MODEL = {
  id: 'm1',
  name: 'GPT-4o mini',
  model_type: 'llm',
  runtime: 'api',
  provider: 'openai',
  model_id: 'gpt-4o-mini',
  has_api_key: true,
  status: 'ready',
  status_detail: null,
}

function stubFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url) => {
      const path = String(url)
      if (path.endsWith('/ingest/sources')) {
        return { ok: true, status: 200, json: async () => ({ sources: [] }) }
      }
      if (path.endsWith('/models')) {
        return { ok: true, status: 200, json: async () => [MODEL] }
      }
      if (path.endsWith('/chains')) {
        return { ok: true, status: 200, json: async () => [] }
      }
      if (path.endsWith('/serving')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            llm_mode: 'disabled',
            llm_target: null,
            embedding_mode: 'disabled',
            embedding_target: null,
          }),
        }
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

describe('ModelHubPage', () => {
  it('renders the header, tab counts, and serving status', async () => {
    stubFetch()
    render(
      <MemoryRouter>
        <ModelHubPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: /model hub/i })).toBeInTheDocument()
    })
    expect(screen.getByText(/inference layer/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /models\s*1/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /chains\s*0/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /serving status/i })).toBeInTheDocument()
  })
})
