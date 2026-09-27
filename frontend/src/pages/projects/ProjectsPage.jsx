import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import ContextForgeMark from '../../components/ContextForgeMark'
import { useProjects } from '../../hooks/useProjects'
import {
  FEATURED_PROJECTS,
  SORT_OPTIONS,
  filterProjects,
  lastOpenedLabel,
  projectCategories,
  sortProjects,
  timeAgo,
} from '../../lib/projects'
import '../../styles/projects.css'
import CommandPalette from './CommandPalette'
import NewProjectModal from './NewProjectModal'

// Original abstract cover artwork — soft topographic / orbital motifs in
// muted tones.  Deliberately distinct from any third-party product.
function CoverArt({ cover = 'aurora', seed = '' }) {
  const id = `${cover}-${seed}`.replace(/[^a-z0-9-]/gi, '')
  let hash = 0
  for (let i = 0; i < seed.length; i += 1) hash = (hash * 33 + seed.charCodeAt(i)) % 997
  const circles = [0, 1, 2].map((i) => ({
    cx: 200 + ((hash + i * 137) % 320),
    cy: 40 + ((hash + i * 89) % 90),
    r: 70 + ((hash + i * 53) % 90),
  }))
  return (
    <svg viewBox="0 0 640 200" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs>
        <radialGradient id={`g-${id}`} cx="30%" cy="20%" r="90%">
          <stop offset="0%" stopColor="rgba(255,255,255,0.16)" />
          <stop offset="55%" stopColor="rgba(255,255,255,0.04)" />
          <stop offset="100%" stopColor="rgba(255,255,255,0)" />
        </radialGradient>
      </defs>
      <rect width="640" height="200" fill={`url(#g-${id})`} />
      {circles.map((c, i) => (
        <circle
          key={i}
          cx={c.cx}
          cy={c.cy}
          r={c.r}
          fill="none"
          stroke="rgba(255,255,255,0.14)"
          strokeWidth="1.2"
        />
      ))}
      <circle cx={circles[0].cx} cy={circles[0].cy} r="4" fill="rgba(255,255,255,0.5)" />
      <path
        d={`M0 ${120 + (hash % 30)} C 160 ${80 + (hash % 40)}, 420 ${160 - (hash % 30)}, 640 ${100 + (hash % 40)}`}
        fill="none"
        stroke="rgba(255,255,255,0.18)"
        strokeWidth="1.4"
      />
      <path
        d={`M0 ${140 + (hash % 20)} C 180 ${110 + (hash % 30)}, 400 ${170 - (hash % 20)}, 640 ${130}`}
        fill="none"
        stroke="rgba(255,255,255,0.08)"
        strokeWidth="1"
      />
    </svg>
  )
}

function ArrowMark() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  )
}

export default function ProjectsPage() {
  const navigate = useNavigate()
  const { projects, loading, error, refresh, create, rename, remove, touch } = useProjects()

  const [query, setQuery] = useState('')
  const [sortId, setSortId] = useState('recent')
  const [category, setCategory] = useState('all')
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [menuId, setMenuId] = useState(null)
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [renameTarget, setRenameTarget] = useState(null)
  const [renameName, setRenameName] = useState('')
  const [renameDesc, setRenameDesc] = useState('')
  const [notice, setNotice] = useState(null)
  const [recentSearches, setRecentSearches] = useState([])
  // Tracks which template is being materialised so rapid clicks can't create
  // the same project twice.
  const [templateBusy, setTemplateBusy] = useState(null)
  const menuRef = useRef(null)

  useEffect(() => {
    try {
      const raw = localStorage.getItem('cf-recent-searches')
      if (raw) setRecentSearches(JSON.parse(raw))
    } catch {
      /* ignore */
    }
  }, [])

  // ⌘K / Ctrl+K opens the palette from anywhere on this page.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (!menuId) return undefined
    const onDown = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuId(null)
      if (e.key === 'Escape') setMenuId(null)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onDown)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onDown)
    }
  }, [menuId])

  useEffect(() => {
    if (!notice) return undefined
    const id = setTimeout(() => setNotice(null), 4200)
    return () => clearTimeout(id)
  }, [notice])

  // Esc closes the rename dialog.
  useEffect(() => {
    if (!renameTarget) return undefined
    const onKey = (e) => {
      if (e.key === 'Escape') setRenameTarget(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [renameTarget])

  const categories = useMemo(() => projectCategories(projects), [projects])

  const visible = useMemo(() => {
    const filtered = filterProjects(projects, { query, category })
    return sortProjects(filtered, sortId)
  }, [projects, query, category, sortId])

  const persistRecent = useCallback((q) => {
    const trimmed = q.trim()
    if (!trimmed) return
    setRecentSearches((prev) => {
      const next = [trimmed, ...prev.filter((s) => s !== trimmed)].slice(0, 5)
      try {
        localStorage.setItem('cf-recent-searches', JSON.stringify(next))
      } catch {
        /* ignore */
      }
      return next
    })
  }, [])

  const openProject = useCallback(
    async (project) => {
      persistRecent(project.name)
      try {
        await touch(project.id)
      } catch {
        /* best effort */
      }
      navigate(`/projects/${encodeURIComponent(project.id)}`)
    },
    [navigate, touch, persistRecent],
  )

  const createFromTemplate = useCallback(
    async (template) => {
      if (templateBusy) return
      setTemplateBusy(template.id || template.title)
      try {
        const project = await create({
          name: template.title,
          description: template.description,
          category: template.tags?.[0] || 'General',
        })
        setNotice(`Created “${template.title}” — opening its workspace.`)
        navigate(`/projects/${encodeURIComponent(project.id)}`)
      } catch (err) {
        setNotice(err.message || 'Could not create from template.')
      } finally {
        setTemplateBusy(null)
      }
    },
    [create, navigate, templateBusy],
  )

  const handleDelete = useCallback(
    async (project) => {
      try {
        await remove(project.id)
        setConfirmDelete(null)
        setNotice(`Deleted “${project.name}”. Its sources remain in your knowledge base.`)
      } catch (err) {
        setNotice(err.message || 'Could not delete the project.')
      }
    },
    [remove],
  )

  const handleRename = useCallback(async () => {
    if (!renameTarget || !renameName.trim()) return
    try {
      await rename(renameTarget.id, { name: renameName.trim(), description: renameDesc.trim() })
      setRenameTarget(null)
      setNotice('Project renamed.')
    } catch (err) {
      setNotice(err.message || 'Could not rename the project.')
    }
  }, [renameTarget, renameName, renameDesc, rename])

  return (
    <div className="pg-root">
      {/* ---------------- top navigation ---------------- */}
      <header className="pg-nav">
        <div className="pg-nav-inner">
          <button className="pg-brand" onClick={() => navigate('/')} aria-label="ContextForge home">
            <ContextForgeMark size={30} />
            <span>
              Context<span className="pg-brand-accent">Forge</span>
            </span>
          </button>
          <nav className="pg-tabs" aria-label="Primary">
            <button
              className="pg-tab is-active"
              aria-current="page"
              onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
            >
              Projects
            </button>
            <button
              className="pg-tab"
              onClick={() =>
                document.getElementById('pg-library')?.scrollIntoView({ behavior: 'smooth' })
              }
            >
              Collections
            </button>
          </nav>
          <div className="pg-nav-right">
            <button
              className="pg-search-trigger"
              onClick={() => setPaletteOpen(true)}
              aria-label="Search projects"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                aria-hidden="true"
              >
                <circle cx="11" cy="11" r="7" />
                <path d="M21 21l-4.3-4.3" />
              </svg>
              <span>Search projects</span>
              <span className="pg-kbd">⌘K</span>
            </button>
            <button
              className="pg-icon-btn"
              onClick={() => navigate('/models')}
              aria-label="Settings"
            >
              <svg
                width="17"
                height="17"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.01a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </button>
            <button className="pg-avatar" aria-label="Your profile">
              AZ
            </button>
          </div>
        </div>
      </header>

      <main className="pg-body">
        {/* ---------------- featured ---------------- */}
        <section id="pg-featured" aria-labelledby="pg-featured-h">
          <div className="pg-section-head">
            <div>
              <span className="pg-eyebrow">Featured</span>
              <h2 className="pg-h2" id="pg-featured-h">
                Start from a curated collection
              </h2>
              <p className="pg-section-sub">
                Example libraries — using one creates your own private copy.
              </p>
            </div>
          </div>
          <div className="pg-featured-grid">
            {FEATURED_PROJECTS.slice(0, 4).map((f) => (
              <button
                key={f.id}
                className="pg-featured-card"
                onClick={() => createFromTemplate(f)}
                disabled={templateBusy !== null}
                aria-label={`Use template ${f.title}`}
              >
                <span className={`pg-cover is-${f.cover}`}>
                  <CoverArt cover={f.cover} seed={f.id} />
                  <span className="pg-provider-badge">{f.provider}</span>
                </span>
                <span className="pg-featured-body" style={{ display: 'block' }}>
                  <span className="pg-featured-title">
                    <span className="pg-title-text">{f.title}</span>
                    <span className="pg-open-arrow">
                      <ArrowMark />
                    </span>
                  </span>
                  <span className="pg-featured-desc">{f.description}</span>
                  <span className="pg-featured-meta">
                    <span>{f.sourceCount} sources</span>
                    <span className="pg-dot" />
                    <span>{timeAgo(f.updatedAt)}</span>
                  </span>
                </span>
              </button>
            ))}
          </div>
        </section>

        {/* ---------------- library ---------------- */}
        <section id="pg-library" aria-labelledby="pg-library-h">
          <div className="pg-section-head">
            <div>
              <span className="pg-eyebrow">Library</span>
              <h2 className="pg-h2" id="pg-library-h">
                Your Projects
              </h2>
              <p className="pg-section-sub">
                {loading
                  ? 'Loading…'
                  : `${visible.length} of ${projects.length} project${projects.length === 1 ? '' : 's'}`}
              </p>
            </div>
          </div>

          <div className="pg-toolbar" role="search">
            <div className="pg-toolbar-search">
              <svg
                width="15"
                height="15"
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
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') persistRecent(query)
                }}
                placeholder="Search projects…"
                aria-label="Search your projects"
              />
            </div>
            <select
              className="pg-select"
              value={sortId}
              onChange={(e) => setSortId(e.target.value)}
              aria-label="Sort projects"
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
            <select
              className="pg-select"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              aria-label="Filter by category"
            >
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c === 'all' ? 'All categories' : c}
                </option>
              ))}
            </select>
            <button className="pg-new-btn" onClick={() => setModalOpen(true)}>
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                aria-hidden="true"
              >
                <path d="M12 5v14M5 12h14" />
              </svg>
              New Project
            </button>
          </div>

          <div style={{ marginTop: 18 }}>
            {loading ? (
              <div className="pg-skeleton-grid" aria-label="Loading projects">
                {[0, 1, 2, 3].map((i) => (
                  <div key={i} className="pg-skeleton" aria-hidden="true">
                    <i style={{ height: 148 }} />
                    <i style={{ height: 16, width: '60%' }} />
                    <i style={{ height: 12, width: '90%' }} />
                    <i style={{ height: 12, width: '40%' }} />
                  </div>
                ))}
              </div>
            ) : error ? (
              <div className="pg-error" role="alert">
                <p style={{ margin: 0, fontWeight: 600, color: 'var(--ink-strong)' }}>
                  Couldn’t load your projects
                </p>
                <p style={{ margin: '8px 0 18px' }}>{error}</p>
                <button className="pg-btn-primary" onClick={refresh}>
                  Try again
                </button>
              </div>
            ) : projects.length === 0 ? (
              <div className="pg-empty">
                <div className="pg-empty-mark">
                  <ContextForgeMark size={32} />
                </div>
                <h2>Your research starts here.</h2>
                <p>
                  Create a project and bring your sources together in one intelligent workspace.
                </p>
                <div className="pg-empty-actions">
                  <button className="pg-btn-primary" onClick={() => setModalOpen(true)}>
                    Create your first project
                  </button>
                  <button
                    className="pg-btn-ghost"
                    onClick={() =>
                      document.getElementById('pg-featured')?.scrollIntoView({ behavior: 'smooth' })
                    }
                  >
                    Browse templates
                  </button>
                </div>
              </div>
            ) : visible.length === 0 ? (
              <div className="pg-empty" style={{ padding: '48px 24px' }}>
                <h2 style={{ fontSize: '1.2rem' }}>No projects match “{query}”</h2>
                <p>Try a different search, or start something new.</p>
                <div className="pg-empty-actions">
                  <button
                    className="pg-btn-ghost"
                    onClick={() => {
                      setQuery('')
                      setCategory('all')
                    }}
                  >
                    Clear filters
                  </button>
                  <button className="pg-btn-primary" onClick={() => setModalOpen(true)}>
                    New Project
                  </button>
                </div>
              </div>
            ) : (
              <div className="pg-grid">
                {visible.map((p) => (
                  <div
                    key={p.id}
                    className="pg-card"
                    role="button"
                    tabIndex={0}
                    aria-label={`Open project ${p.name}, ${p.source_count || 0} sources`}
                    onClick={() => openProject(p)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        openProject(p)
                      }
                    }}
                  >
                    <span className={`pg-cover is-${p.cover || 'aurora'}`}>
                      <CoverArt cover={p.cover} seed={p.id} />
                      <span className="pg-provider-badge">{p.category || 'General'}</span>
                      <button
                        className="pg-more-btn pg-more-over-cover"
                        aria-label={`More actions for ${p.name}`}
                        aria-expanded={menuId === p.id}
                        aria-haspopup="menu"
                        onClick={(e) => {
                          e.stopPropagation()
                          setMenuId(menuId === p.id ? null : p.id)
                        }}
                        // The card itself opens on Enter/Space — without this,
                        // keyboard use of the menu would also open the project.
                        onKeyDown={(e) => e.stopPropagation()}
                      >
                        <svg
                          width="15"
                          height="15"
                          viewBox="0 0 24 24"
                          fill="currentColor"
                          aria-hidden="true"
                        >
                          <circle cx="12" cy="5" r="1.8" />
                          <circle cx="12" cy="12" r="1.8" />
                          <circle cx="12" cy="19" r="1.8" />
                        </svg>
                      </button>
                    </span>
                    <span className="pg-featured-body" style={{ display: 'block' }}>
                      <span className="pg-featured-title">
                        <span className="pg-title-text">{p.name}</span>
                        <span className="pg-open-arrow">
                          <ArrowMark />
                        </span>
                      </span>
                      <span className="pg-featured-desc">
                        {p.description ||
                          'No description yet — add one to describe this line of research.'}
                      </span>
                      <span className="pg-featured-meta">
                        <span>
                          {p.source_count ?? 0} source{(p.source_count ?? 0) === 1 ? '' : 's'}
                        </span>
                        <span className="pg-dot" />
                        <span>{lastOpenedLabel(p.last_opened_at)}</span>
                      </span>
                    </span>
                    {menuId === p.id ? (
                      <div
                        className="pg-more-menu"
                        role="menu"
                        ref={menuRef}
                        onClick={(e) => e.stopPropagation()}
                        onKeyDown={(e) => e.stopPropagation()}
                      >
                        <button
                          role="menuitem"
                          onClick={() => {
                            setMenuId(null)
                            openProject(p)
                          }}
                        >
                          Open workspace
                        </button>
                        <button
                          role="menuitem"
                          onClick={() => {
                            setMenuId(null)
                            setRenameTarget(p)
                            setRenameName(p.name)
                            setRenameDesc(p.description || '')
                          }}
                        >
                          Rename
                        </button>
                        <button
                          role="menuitem"
                          className="is-danger"
                          onClick={() => {
                            setMenuId(null)
                            setConfirmDelete(p)
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </main>

      <CommandPalette
        open={paletteOpen}
        projects={projects}
        recent={recentSearches}
        onClose={() => setPaletteOpen(false)}
        onSelect={(p) => openProject(p)}
      />

      <NewProjectModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={async (project, info) => {
          setModalOpen(false)
          await refresh()
          if (info?.failures?.length) {
            setNotice(
              `${info.failures.length} source${info.failures.length === 1 ? '' : 's'} failed to ingest — project created anyway.`,
            )
          } else if (info?.staged) {
            setNotice(
              `Created “${project.name}” with ${info.staged} source${info.staged === 1 ? '' : 's'}.`,
            )
          }
          navigate(`/projects/${encodeURIComponent(project.id)}`)
        }}
      />

      {confirmDelete ? (
        <div
          className="pg-modal-backdrop"
          onClick={() => setConfirmDelete(null)}
          role="presentation"
        >
          <div
            className="pg-modal"
            style={{ width: 'min(440px, 92vw)' }}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="pg-del-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="pg-del-title" style={{ margin: 0, fontSize: '1.15rem' }}>
              Delete “{confirmDelete.name}”?
            </h2>
            <p style={{ color: 'var(--mute)', fontSize: '0.88rem', lineHeight: 1.6 }}>
              The project will be removed from your library. Sources in your knowledge base are
              kept.
            </p>
            <div className="pg-modal-actions" style={{ marginTop: 20 }}>
              <button className="pg-btn-ghost" onClick={() => setConfirmDelete(null)}>
                Cancel
              </button>
              <button className="pg-btn-primary" onClick={() => handleDelete(confirmDelete)}>
                Delete project
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {renameTarget ? (
        <div
          className="pg-modal-backdrop"
          onClick={() => setRenameTarget(null)}
          role="presentation"
        >
          <div
            className="pg-modal"
            style={{ width: 'min(480px, 92vw)' }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="pg-rename-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="pg-rename-title" style={{ margin: 0, fontSize: '1.15rem' }}>
              Rename project
            </h2>
            <div className="pg-field">
              <label htmlFor="pg-rename-name">Name</label>
              <input
                id="pg-rename-name"
                autoFocus
                value={renameName}
                onChange={(e) => setRenameName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleRename()
                }}
                maxLength={120}
              />
            </div>
            <div className="pg-field">
              <label htmlFor="pg-rename-desc">Description</label>
              <textarea
                id="pg-rename-desc"
                rows={2}
                value={renameDesc}
                onChange={(e) => setRenameDesc(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleRename()
                }}
                maxLength={2000}
              />
            </div>
            <div className="pg-modal-actions" style={{ marginTop: 20 }}>
              <button className="pg-btn-ghost" onClick={() => setRenameTarget(null)}>
                Cancel
              </button>
              <button
                className="pg-btn-primary"
                onClick={handleRename}
                disabled={!renameName.trim()}
              >
                Save changes
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {notice ? (
        <div className="toast-stack" role="status">
          <div className="toast info">{notice}</div>
        </div>
      ) : null}
    </div>
  )
}
