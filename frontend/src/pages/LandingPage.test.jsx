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

  it('exposes a primary call to action into the workspace', () => {
    renderPage()
    const ctas = screen.getAllByRole('link', { name: /open the workspace/i })
    expect(ctas.length).toBeGreaterThan(0)
    ctas.forEach((cta) => expect(cta).toHaveAttribute('href', '/workspace'))
  })

  it('renders the retrieval pipeline as a list of six stages', () => {
    renderPage()
    const rails = screen.getByRole('list', { name: /retrieval pipeline stages/i })
    expect(rails.querySelectorAll('li')).toHaveLength(6)
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
    expect(targets).toEqual(['#pipeline', '#capabilities', '#intelligence', '#stack'])
  })
})
