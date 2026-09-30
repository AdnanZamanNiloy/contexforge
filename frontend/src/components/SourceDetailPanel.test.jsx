import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'

import SourceDetailPanel from './SourceDetailPanel'
import { fetchSourceDetail, fetchSourceContent } from '../services/api'

// Source inspection.  A source that extracted badly is indistinguishable from a
// healthy one in the sidebar — it still appears, still gets cited, still answers
// questions — so this panel exists to surface what was actually indexed.
//
// The behaviour these tests pin is the honesty of that report: an empty
// extraction must say so in words, the missing original file must be stated
// rather than implied, and one source's payload must never render under another.

vi.mock('../services/api', () => ({
  fetchSourceDetail: vi.fn(),
  fetchSourceContent: vi.fn(),
}))

const HEALTHY = {
  source_id: 's1',
  title: 'A university',
  derived_title: 'A university',
  renamed: false,
  source_type: 'web',
  url: 'https://example.org/uni',
  chunk_count: 3,
  char_count: 9000,
  language: 'en',
  file_paths: [],
  page_count: null,
  non_empty_pages: null,
  is_scanned: null,
  keywords: ['university', 'students'],
  named_entities: [{ text: 'Other', label: 'REGEX' }],
  file_available: false,
}

function chunk(index, text) {
  return { chunk_id: `s1:${index}`, chunk_index: index, path: null, text }
}

beforeEach(() => {
  vi.mocked(fetchSourceDetail).mockReset()
  vi.mocked(fetchSourceContent).mockReset()
  vi.mocked(fetchSourceDetail).mockResolvedValue(HEALTHY)
  vi.mocked(fetchSourceContent).mockResolvedValue({
    source_id: 's1',
    chunks: [chunk(0, 'First chunk text'), chunk(1, 'Second chunk text')],
    chunk_count: 2,
    total_chunks: 2,
    truncated: false,
  })
})

function renderPanel(props = {}) {
  return render(<SourceDetailPanel sourceId="s1" onClose={() => {}} {...props} />)
}

describe('SourceDetailPanel provenance', () => {
  it('reports what was indexed', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByText(/3 chunks/i)).toBeInTheDocument())
    expect(screen.getByText(/9,000 characters/i)).toBeInTheDocument()
  })

  it('labels the source type in plain language', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByText('Web page')).toBeInTheDocument())
  })

  it('states that the original file is not retained', async () => {
    renderPanel()
    // Said in words, not implied by an absent download button.
    await waitFor(() => expect(screen.getByText(/Not retained/i)).toBeInTheDocument())
  })

  it('shows the rename when the title was overridden', async () => {
    vi.mocked(fetchSourceDetail).mockResolvedValue({
      ...HEALTHY,
      title: 'My uni notes',
      derived_title: 'A university',
      renamed: true,
    })
    renderPanel()
    await waitFor(() => expect(screen.getByText(/Renamed from/i)).toBeInTheDocument())
  })

  it('shows the file list for a repository source', async () => {
    vi.mocked(fetchSourceDetail).mockResolvedValue({
      ...HEALTHY,
      source_type: 'github',
      file_paths: ['LICENSE', 'README.md', 'backend/app.py'],
    })
    renderPanel()
    await waitFor(() => expect(screen.getByText('Indexed files (3)')).toBeInTheDocument())
    expect(screen.getByText('backend/app.py')).toBeInTheDocument()
  })
})

describe('SourceDetailPanel extraction warnings', () => {
  it('warns when nothing was extracted', async () => {
    vi.mocked(fetchSourceDetail).mockResolvedValue({
      ...HEALTHY,
      chunk_count: 1,
      char_count: 0,
      is_scanned: true,
      page_count: 4,
      non_empty_pages: 0,
    })
    renderPanel()
    await waitFor(() => expect(screen.getByText(/No text was extracted/i)).toBeInTheDocument())
  })

  it('warns when some pages had no text layer', async () => {
    vi.mocked(fetchSourceDetail).mockResolvedValue({
      ...HEALTHY,
      source_type: 'pdf',
      is_scanned: true,
      page_count: 10,
      non_empty_pages: 6,
      char_count: 8000,
    })
    renderPanel()
    await waitFor(() => expect(screen.getByText(/4 of 10 pages had no text/i)).toBeInTheDocument())
  })

  it('warns when a document yielded very little text', async () => {
    vi.mocked(fetchSourceDetail).mockResolvedValue({ ...HEALTHY, char_count: 120 })
    renderPanel()
    await waitFor(() => expect(screen.getByText(/Very little text/i)).toBeInTheDocument())
  })

  it('shows no warning for a healthy extraction', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByText(/3 chunks/i)).toBeInTheDocument())
    expect(screen.queryByText(/No text was extracted/i)).toBeNull()
    expect(screen.queryByText(/Very little text/i)).toBeNull()
  })
})

describe('SourceDetailPanel indexed text', () => {
  it('shows the chunk text retrieval would quote', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByText('First chunk text')).toBeInTheDocument())
  })

  it('says when the response was capped', async () => {
    vi.mocked(fetchSourceContent).mockResolvedValue({
      source_id: 's1',
      chunks: [chunk(0, 'First chunk text')],
      chunk_count: 1,
      total_chunks: 200,
      truncated: true,
    })
    renderPanel()
    await waitFor(() => expect(screen.getByText(/first 1 of 200 chunks/i)).toBeInTheDocument())
  })

  it('reveals every chunk on request', async () => {
    vi.mocked(fetchSourceContent).mockResolvedValue({
      source_id: 's1',
      chunks: [chunk(0, 'Alpha'), chunk(1, 'Bravo'), chunk(2, 'Charlie'), chunk(3, 'Delta')],
      chunk_count: 4,
      total_chunks: 4,
      truncated: false,
    })
    renderPanel()
    await waitFor(() => expect(screen.getByText(/Show all 4 chunks/i)).toBeInTheDocument())
    expect(screen.queryByText('Delta')).toBeNull()

    fireEvent.click(screen.getByText(/Show all 4 chunks/i))
    await waitFor(() => expect(screen.getByText('Delta')).toBeInTheDocument())
  })
})

describe('SourceDetailPanel failures', () => {
  it('keeps the provenance when only the content request fails', async () => {
    vi.mocked(fetchSourceContent).mockRejectedValue(new Error('content boom'))
    renderPanel()
    // The panel is still useful without the text, so it must not blank out.
    await waitFor(() => expect(screen.getByText(/content boom/i)).toBeInTheDocument())
    expect(screen.getByText(/3 chunks/i)).toBeInTheDocument()
  })

  it('reports a total failure', async () => {
    vi.mocked(fetchSourceDetail).mockRejectedValue(new Error('detail boom'))
    renderPanel()
    await waitFor(() => expect(screen.getByText('detail boom')).toBeInTheDocument())
  })
})

describe('SourceDetailPanel lifecycle', () => {
  it('renders nothing without a source', () => {
    const { container } = renderPanel({ sourceId: '' })
    expect(container.firstChild).toBeNull()
    expect(fetchSourceDetail).not.toHaveBeenCalled()
  })

  it('closes from the button and from the backdrop', async () => {
    const onClose = vi.fn()
    renderPanel({ onClose })
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /close source details/i }))
    expect(onClose).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('dialog'))
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('closes on Escape', async () => {
    const onClose = vi.fn()
    renderPanel({ onClose })
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
  it('never renders one source’s payload under another', async () => {
    // Switching sources while the first request is still in flight must not show
    // the first source's chunks.  s1's detail resolves *after* the switch, which
    // is exactly the race that would paint stale provenance.
    let resolveFirst
    vi.mocked(fetchSourceDetail).mockImplementation(
      (id) =>
        new Promise((resolve) => {
          if (id === 's1') resolveFirst = () => resolve({ ...HEALTHY, title: 'First source' })
          else resolve({ ...HEALTHY, source_id: 's2', title: 'Second source' })
        }),
    )
    vi.mocked(fetchSourceContent).mockImplementation((id) =>
      Promise.resolve({
        source_id: id,
        chunks: [chunk(0, `${id} chunk`)],
        chunk_count: 1,
        total_chunks: 1,
        truncated: false,
      }),
    )

    const { rerender } = render(<SourceDetailPanel sourceId="s1" onClose={() => {}} />)
    rerender(<SourceDetailPanel sourceId="s2" onClose={() => {}} />)
    resolveFirst()

    await waitFor(() => expect(screen.getByText('Second source')).toBeInTheDocument())
    expect(screen.queryByText('First source')).toBeNull()
    expect(screen.queryByText('s1 chunk')).toBeNull()
  })
})
