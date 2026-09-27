import { useEffect, useRef, useState } from 'react'

import {
  attachSourceToProject,
  createProject,
  ingestFile,
  ingestGithub,
  ingestSource,
} from '../../services/api'

// Polished lightweight creation flow: name + optional description first,
// then optional source imports (staged locally, ingested on Create).
export default function NewProjectModal({ open, onClose, onCreated, initialName = '' }) {
  const [name, setName] = useState(initialName)
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('')
  const [staged, setStaged] = useState([])
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)
  const nameRef = useRef(null)

  // Draft inputs per import card (kept local so typing never stages).
  const [urlDraft, setUrlDraft] = useState('')
  const [repoDraft, setRepoDraft] = useState('')
  const [ytDraft, setYtDraft] = useState('')
  const [textDraft, setTextDraft] = useState('')

  useEffect(() => {
    if (open) {
      setName(initialName)
      setDescription('')
      setCategory('')
      setStaged([])
      setError(null)
      setCreating(false)
      setUrlDraft('')
      setRepoDraft('')
      setYtDraft('')
      setTextDraft('')
      requestAnimationFrame(() => nameRef.current?.focus())
    }
  }, [open, initialName])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => {
      // Never dismiss mid-creation — ingestion is in flight.
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

  const stage = (entry) => {
    setStaged((prev) => [...prev, { ...entry, key: `${entry.kind}-${Date.now()}-${prev.length}` }])
  }

  const removeStaged = (key) => setStaged((prev) => prev.filter((s) => s.key !== key))

  const handleFiles = (event) => {
    const files = Array.from(event.target.files || [])
    files.forEach((file) => {
      const lower = file.name.toLowerCase()
      let kind = 'file-pdf'
      if (lower.endsWith('.docx')) kind = 'file-docx'
      else if (lower.endsWith('.txt') || lower.endsWith('.md')) kind = 'file-text'
      stage({ kind, label: file.name, file })
    })
    event.target.value = ''
  }

  const valid = name.trim().length > 0 && !creating

  const ingestOne = async (item) => {
    switch (item.kind) {
      case 'web':
        return ingestSource({ source_type: 'web', source: item.payload })
      case 'github':
        return ingestGithub({ repo_url: item.payload })
      case 'youtube':
        return ingestSource({ source_type: 'youtube', source: item.payload })
      case 'text':
        return ingestSource({ source_type: 'text', source: item.payload })
      case 'file-pdf':
        return ingestFile({ source_type: 'pdf', file: item.file })
      case 'file-docx':
        return ingestFile({ source_type: 'docx', file: item.file })
      case 'file-text': {
        const text = await item.file.text()
        return ingestSource({ source_type: 'text', source: text })
      }
      default:
        throw new Error(`Unknown import kind: ${item.kind}`)
    }
  }

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
      })
      // Ingest staged sources one by one, attaching each to the new project.
      // Failures are collected but never block project creation.
      const failures = []
      for (const item of staged) {
        try {
          const result = await ingestOne(item)
          if (result?.source_id) {
            await attachSourceToProject(project.id, result.source_id)
          }
        } catch (err) {
          failures.push(`${item.label}: ${err.message || 'ingest failed'}`)
        }
      }
      onCreated?.(project, { staged: staged.length, failures })
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
            <p>Bring your sources together in one intelligent workspace. You can add more later.</p>
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

        <div style={{ marginTop: 22 }}>
          <span className="pg-eyebrow">Add sources — optional</span>
          <div className="pg-import-grid">
            <div className="pg-import-card">
              <h3>Upload files</h3>
              <p>PDF, DOCX, TXT, Markdown · max 50MB</p>
              <label className="pg-import-add" style={{ textAlign: 'center', cursor: 'pointer' }}>
                Choose files
                <input
                  type="file"
                  hidden
                  multiple
                  accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown"
                  onChange={handleFiles}
                />
              </label>
            </div>

            <div className="pg-import-card">
              <h3>Import from web</h3>
              <p>Paste any public URL</p>
              <input
                value={urlDraft}
                onChange={(e) => setUrlDraft(e.target.value)}
                placeholder="https://example.com/article"
                aria-label="Web URL"
              />
              <button
                className="pg-import-add"
                disabled={!urlDraft.trim() || creating}
                onClick={() => {
                  stage({
                    kind: 'web',
                    label: urlDraft.trim().replace(/^https?:\/\//, ''),
                    payload: urlDraft.trim(),
                  })
                  setUrlDraft('')
                }}
              >
                Stage URL
              </button>
            </div>

            <div className="pg-import-card">
              <h3>Import from GitHub</h3>
              <p>Index a public repository</p>
              <input
                value={repoDraft}
                onChange={(e) => setRepoDraft(e.target.value)}
                placeholder="https://github.com/org/repo"
                aria-label="GitHub repository URL"
              />
              <button
                className="pg-import-add"
                disabled={!repoDraft.trim() || creating}
                onClick={() => {
                  stage({
                    kind: 'github',
                    label: repoDraft.trim().replace('https://github.com/', ''),
                    payload: repoDraft.trim(),
                  })
                  setRepoDraft('')
                }}
              >
                Stage repo
              </button>
            </div>

            <div className="pg-import-card">
              <h3>Import from YouTube</h3>
              <p>Paste a video URL</p>
              <input
                value={ytDraft}
                onChange={(e) => setYtDraft(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=…"
                aria-label="YouTube video URL"
              />
              <button
                className="pg-import-add"
                disabled={!ytDraft.trim() || creating}
                onClick={() => {
                  stage({ kind: 'youtube', label: 'YouTube video', payload: ytDraft.trim() })
                  setYtDraft('')
                }}
              >
                Stage video
              </button>
            </div>

            <div className="pg-import-card" style={{ gridColumn: '1 / -1' }}>
              <h3>Paste text</h3>
              <p>Notes, specs, snippets — stored instantly</p>
              <textarea
                rows={2}
                value={textDraft}
                onChange={(e) => setTextDraft(e.target.value)}
                placeholder="Paste knowledge snippets, meeting notes, or specs…"
                aria-label="Paste text"
              />
              <button
                className="pg-import-add"
                disabled={!textDraft.trim() || creating}
                onClick={() => {
                  stage({
                    kind: 'text',
                    label: `${textDraft.trim().slice(0, 42)}…`,
                    payload: textDraft.trim(),
                  })
                  setTextDraft('')
                }}
              >
                Stage text
              </button>
            </div>
          </div>
        </div>

        {error ? (
          <div role="alert" style={{ marginTop: 16, color: '#f0a3a3', fontSize: '0.85rem' }}>
            {error}
          </div>
        ) : null}

        <div className="pg-modal-foot">
          <div className="pg-staged" aria-live="polite">
            {staged.length === 0 ? (
              <span style={{ background: 'none', border: 'none', padding: 0 }}>
                No sources staged yet — you can also start empty.
              </span>
            ) : (
              staged.map((s) => (
                <span key={s.key} title={s.label}>
                  {s.label.length > 28 ? `${s.label.slice(0, 28)}…` : s.label}
                  <button
                    onClick={() => removeStaged(s.key)}
                    disabled={creating}
                    aria-label={`Remove ${s.label}`}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: 'inherit',
                      cursor: 'pointer',
                      padding: '0 0 0 6px',
                      fontSize: '0.7rem',
                    }}
                  >
                    ✕
                  </button>
                </span>
              ))
            )}
          </div>
          <div className="pg-modal-actions">
            <button className="pg-btn-ghost" onClick={requestClose} disabled={creating}>
              Cancel
            </button>
            <button className="pg-btn-primary" onClick={handleCreate} disabled={!valid}>
              {creating
                ? `Creating${staged.length ? ` · ingesting ${staged.length}…` : '…'}`
                : staged.length
                  ? `Create · ingest ${staged.length}`
                  : 'Create project'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
