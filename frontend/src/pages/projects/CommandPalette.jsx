import { useEffect, useMemo, useRef, useState } from 'react'

// Global-feeling command palette for the Projects library: fuzzy-ish name /
// description search, keyboard navigable, recent-search memory.  The palette
// keeps its own query state — it never writes back to the parent during
// render (that caused render-phase updates of the library grid).
export default function CommandPalette({ open, projects = [], recent = [], onClose, onSelect }) {
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const inputRef = useRef(null)

  useEffect(() => {
    if (open) {
      setQuery('')
      setActive(0)
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (event) => {
      if (event.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return projects.slice(0, 6)
    return projects
      .filter(
        (p) =>
          (p.name || '').toLowerCase().includes(q) ||
          (p.description || '').toLowerCase().includes(q) ||
          (p.category || '').toLowerCase().includes(q),
      )
      .slice(0, 8)
  }, [query, projects])

  useEffect(() => {
    setActive(0)
  }, [query])

  if (!open) return null

  const choose = (project) => {
    onSelect?.(project)
    onClose?.()
  }

  return (
    <div className="pg-palette-backdrop" onClick={onClose} role="presentation">
      <div
        className="pg-palette"
        role="dialog"
        aria-modal="true"
        aria-label="Search projects"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="pg-palette-input">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="M21 21l-4.3-4.3" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') {
                e.preventDefault()
                setActive((a) => Math.min(a + 1, results.length - 1))
              } else if (e.key === 'ArrowUp') {
                e.preventDefault()
                setActive((a) => Math.max(a - 1, 0))
              } else if (e.key === 'Enter' && results[active]) {
                choose(results[active])
              }
            }}
            placeholder="Search projects by name, description, or category…"
            aria-label="Search projects"
          />
          <span className="pg-kbd">esc</span>
        </div>
        <div className="pg-palette-list" role="listbox" aria-label="Matching projects">
          {results.length === 0 ? (
            <div style={{ padding: '18px', color: 'var(--mute)', fontSize: '0.86rem' }}>
              No projects match “{query}”.
            </div>
          ) : (
            results.map((p, index) => (
              <button
                key={p.id}
                role="option"
                aria-selected={index === active}
                className={`pg-palette-item${index === active ? ' is-active' : ''}`}
                onMouseEnter={() => setActive(index)}
                onClick={() => choose(p)}
              >
                <span
                  className={`pg-card-glyph is-${p.cover || 'aurora'}`}
                  style={{ width: 32, height: 32 }}
                >
                  <svg
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="rgba(255,255,255,0.85)"
                    strokeWidth="1.8"
                    aria-hidden="true"
                  >
                    <path d="M4 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" />
                  </svg>
                </span>
                <span style={{ minWidth: 0 }}>
                  <span
                    style={{
                      display: 'block',
                      fontWeight: 600,
                      fontSize: '0.88rem',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {p.name}
                  </span>
                  <span
                    style={{
                      display: 'block',
                      color: 'var(--mute)',
                      fontSize: '0.76rem',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {(p.description || '').slice(0, 72) || p.category || 'No description'}
                  </span>
                </span>
                <small>{p.source_count ?? 0} sources</small>
              </button>
            ))
          )}
          {query.trim() === '' && recent.length > 0 ? (
            <div style={{ padding: '8px 12px 12px', fontSize: '0.72rem', color: 'var(--mute)' }}>
              Recent: {recent.slice(0, 3).join(' · ')}
            </div>
          ) : null}
        </div>
        <div className="pg-palette-hint">
          <span>↑↓ navigate</span>
          <span>↵ open project</span>
          <span>esc close</span>
        </div>
      </div>
    </div>
  )
}
