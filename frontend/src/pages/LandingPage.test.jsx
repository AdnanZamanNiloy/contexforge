import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import LandingPage from './LandingPage'

function renderPage() {
  return render(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>,
  )
}

describe('LandingPage', () => {
  it('states the product promise in the first heading', () => {
    renderPage()
    expect(
      screen.getByRole('heading', { level: 1, name: /sources you control/i }),
    ).toBeInTheDocument()
  })

  it('exposes a primary call to action into the projects library', () => {
    renderPage()
    const ctas = screen.getAllByRole('link', { name: /open projects|browse projects/i })
    expect(ctas.length).toBeGreaterThan(0)
    ctas.forEach((cta) => expect(cta).toHaveAttribute('href', '/projects'))
  })

  it('renders the retrieval pipeline as the five stages the backend times', () => {
    renderPage()
    const rails = screen.getByRole('list', { name: /retrieval pipeline stages/i })
    // Five, not six. Hybrid search and RRF fusion are a single `retrieve_ms`
    // bucket and prompt assembly has no timing key at all, so a six-stage rail
    // was describing something the backend does not report.
    expect(rails.querySelectorAll('li')).toHaveLength(5)
  })

  it('documents every supported source format', () => {
    renderPage()
    const strip = screen.getByRole('list', { name: /supported source formats/i })
    const names = Array.from(strip.querySelectorAll('.lp-source-name')).map((n) => n.textContent)
    expect(names).toEqual(['PDF', 'Word', 'Web', 'YouTube', 'GitHub', 'Text'])
  })

  it('gives capability cards real technical facts, not marketing filler', () => {
    renderPage()
    // "FAISS IndexFlatIP" is deliberately repeated in both the retrieval
    // capability and the stack table — both are claims the reader can verify.
    expect(screen.getAllByText(/FAISS IndexFlatIP/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/ms-marco-MiniLM-L-6-v2/i).length).toBeGreaterThan(0)
  })

  it('provides landmark navigation to the main sections', () => {
    renderPage()
    const nav = screen.getByRole('navigation', { name: /sections/i })
    const targets = Array.from(nav.querySelectorAll('a')).map((a) => a.getAttribute('href'))
    expect(targets).toEqual(['#pipeline', '#workspace', '#capabilities', '#stack'])
  })

  it('shows the workspace tools, not just the retrieval pipeline', () => {
    renderPage()
    // The page used to describe a RAG pipeline and said nothing about the
    // application built on top of it.
    expect(
      screen.getByRole('heading', { name: /turn a selection into a note/i }),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /the same selection, drawn/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /four repository analyzers/i })).toBeInTheDocument()
  })

  it('ships runnable setup commands', () => {
    renderPage()
    const code = document.querySelector('.lp-code').textContent
    expect(code).toMatch(/make install/)
    expect(code).toMatch(/make dev-backend/)
    // `backend.app.main:app` raises ModuleNotFoundError: every module inside
    // backend/app imports `from app.…`, so `app` must be the package and
    // backend/ the working directory.
    expect(code).not.toMatch(/backend\.app\.main/)
  })

  it('makes no claim about a built-in provider order', () => {
    renderPage()
    // There is no default chain. `get_llm()` returns NullLLM until the Model
    // Hub is configured, and serving defaults to `disabled`.
    expect(screen.queryByText(/Gemini leads/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/set two API keys/i)).not.toBeInTheDocument()
  })

  it('does not promise the documents never leave the machine', () => {
    renderPage()
    // The README has always said "except for embedding and LLM API calls";
    // the hero used to claim the stronger, untrue version.
    expect(screen.queryByText(/no data leaves your machine/i)).not.toBeInTheDocument()
  })
})
