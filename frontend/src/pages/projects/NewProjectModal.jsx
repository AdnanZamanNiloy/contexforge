import { useEffect, useRef, useState } from 'react'

import { FileMark, GithubMark, YoutubeMark } from '../../lib/sources'
import { SOURCE_CATEGORIES, sourceCategoryLabel } from '../../lib/projects'
import { createProject } from '../../services/api'

function CategoryIcon({ icon }) {
  if (icon === 'github') return <GithubMark size={20} />
  if (icon === 'youtube') return <YoutubeMark size={20} />
  return <FileMark size={20} />
}

// Focused creation flow: name the project, then pick which kind of sources
// it will hold.  Actual ingestion happens in the project workspace, scoped
// to the chosen family.
export default function NewProjectModal({ open, onClose, onCreated, initialName = '' }) {
  const [name, setName] = useState(initialName)
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('')
  const [sourceCategory, setSourceCategory] = useState('documents')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)
  const nameRef = useRef(null)

  useEffect(() => {
    if (open) {
      setName(initialName)
      setDescription('')
      setCategory('')
      setSourceCategory('documents')
      setError(null)
      setCreating(false)
      if (typeof requestAnimationFrame !== 'undefined') {
        requestAnimationFrame(() => nameRef.current?.focus())
      } else {
        nameRef.current?.focus()
      }
    }
  }, [open, initialName])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      // Never dismiss mid-creation.
      if (e.key === 'Escape' && !creating) onClose?.()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose, creating])

  if (!open) return null

  // Backdrop dismiss is disabled while creating for the same reason.
  const requestClose = () => {
    if (!creating) onClose?.()
  }

  const valid = name.trim().length > 0 && !creating

  const handleCreate = async () => {
    if (!name.trim()) {
      setError('Give your project a name to continue.')
      nameRef.current?.focus()
      return
    }
    setCreating(true)
    setError(null)
    try {
      const project = await createProject({
        name: name.trim(),
        description: description.trim(),
        category: category.trim() || 'General',
        source_category: sourceCategory,
      })
      onCreated?.(project)
    } catch (err) {
      setError(err.message || 'Could not create the project.')
      setCreating(false)
    }
  }

  return (
    <div className="pg-modal-backdrop" onClick={requestClose} role="presentation">
      <div
        className="pg-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pg-new-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="pg-modal-head">
          <div>
            <h2 id="pg-new-title">Create a new project</h2>
            <p>Pick a source family — you&apos;ll add the actual sources in its workspace.</p>
          </div>
          <button className="pg-icon-btn" onClick={requestClose} aria-label="Close">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="pg-field">
          <label htmlFor="pg-name">Project name</label>
          <input
            id="pg-name"
            ref={nameRef}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleCreate()
            }}
            placeholder="e.g. AI Research"
            maxLength={120}
          />
        </div>

        <div className="pg-field">
          <label htmlFor="pg-desc">
            Description <span style={{ fontWeight: 400, color: 'var(--mute)' }}>(optional)</span>
          </label>
          <textarea
            id="pg-desc"
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What is this project about?"
            maxLength={2000}
          />
        </div>

        <div className="pg-field">
          <label htmlFor="pg-cat">
            Category <span style={{ fontWeight: 400, color: 'var(--mute)' }}>(optional)</span>
          </label>
          <input
            id="pg-cat"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="Research, Engineering, Study…"
            maxLength={80}
          />
        </div>

        <div className="pg-field">
          <label id="pg-source-family">What will this project hold?</label>
          <div
            className="pg-import-grid pg-family-grid"
            role="radiogroup"
            aria-labelledby="pg-source-family"
          >
            {SOURCE_CATEGORIES.map((item) => {
              const active = sourceCategory === item.id
              return (
                <button
                  key={item.id}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  className={`pg-import-card pg-family-card${active ? ' is-active' : ''}`}
                  onClick={() => setSourceCategory(item.id)}
                >
                  <span className="pg-family-icon" aria-hidden="true">
                    <CategoryIcon icon={item.icon} />
                  </span>
                  <span className="pg-family-text">
                    <h3>{item.label}</h3>
                    <p>{item.hint}</p>
                  </span>
                  <span className="pg-family-check" aria-hidden="true">
                    ✓
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        {error ? (
          <div role="alert" style={{ marginTop: 16, color: '#f0a3a3', fontSize: '0.85rem' }}>
            {error}
          </div>
        ) : null}

        <div className="pg-modal-foot">
          <div className="pg-staged" aria-live="polite">
            <span style={{ background: 'none', border: 'none', padding: 0 }}>
              {sourceCategoryLabel(sourceCategory)} · added in the workspace next
            </span>
          </div>
          <div className="pg-modal-actions">
            <button className="pg-btn-ghost" onClick={requestClose} disabled={creating}>
              Cancel
            </button>
            <button className="pg-btn-primary" onClick={handleCreate} disabled={!valid}>
              {creating ? 'Creating…' : 'Create project'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
