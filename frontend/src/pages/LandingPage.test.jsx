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

  it('runs hero, stats, features, pipeline, capabilities, quickstart', () => {
    const { container } = renderPage()
    // The page carries no About section and no closing CTA band: the visitor
    // goes from the hero straight into the numbers, and the last thing on the
    // page is the setup path.
    // Sectioned elements carry an id. The hero and the stats strip do not, so
    // they are matched on class — and the stats strip's aria-label is checked
    // separately, since it wins the fallback chain above.
    // A section with no id reads back as an empty string from getAttribute, not
    // as null.
    const sections = Array.from(container.querySelectorAll('main > *')).map((el) => el.id)
    expect(sections).toEqual([
      '',
      '',
      'features',
      'how-it-works',
      'capabilities',
      'quickstart',
    ])
    const [hero, stats] = container.querySelector('main').children
    expect(hero.className).toContain('lp-hero')
    expect(stats.className).toContain('lp-stats')
    expect(stats).toHaveAttribute('aria-label', 'Product by the numbers')
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
    // Visitor-facing labels, in the order the sections appear. The nav used to
    // read Pipeline / Workspace / Capabilities / Stack — internal nouns, one of
    // which pointed at a section that has since been removed.
    expect(targets).toEqual(['#features', '#how-it-works', '#quickstart'])
  })

  it('gives every nav link a target that exists on the page', () => {
    const { container } = renderPage()
    const nav = screen.getByRole('navigation', { name: /sections/i })
    Array.from(nav.querySelectorAll('a')).forEach((a) => {
      const id = a.getAttribute('href').slice(1)
      expect(container.querySelector(`#${id}`)).not.toBeNull()
    })
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

  it('ships setup commands that are real Makefile targets', () => {
    renderPage()
    const commands = Array.from(document.querySelectorAll('.lp-quickstart-cmd')).map((n) =>
      n.textContent.trim(),
    )
    expect(commands).toEqual(
      expect.arrayContaining(['make install', 'make dev-backend', 'make dev-frontend']),
    )
    // There is no bare `make dev` target, and an earlier draft of the quickstart
    // told visitors to run one.
    expect(commands).not.toContain('make dev')
    commands
      .filter((c) => c.startsWith('make '))
      .forEach((c) => expect(c.split(' ').length).toBe(2))
  })

  it('does not tell operators to put a provider key in .env', () => {
    renderPage()
    // backend/.env.example states that keys are not set there: they are added
    // in the Model Hub and stored encrypted.
    expect(document.querySelector('.lp-quickstart').textContent).not.toMatch(
      /VOYAGE_API_KEY|API_KEY/,
    )
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
