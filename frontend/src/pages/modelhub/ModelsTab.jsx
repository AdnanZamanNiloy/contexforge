import { useCallback, useRef, useState } from 'react'

import { deleteModel, testModel, updateModel } from '../../services/api'
import PasswordField from './PasswordField'
import {
  DEVICES,
  LOCAL_BACKENDS,
  providerDisplayName,
  providerLabel,
  runtimeLabel,
  STATUS_LABEL,
  statusClass,
  typeLabel,
} from './modelHubMeta'

function ModelCard({ model, onChanged, onDeleted, notify }) {
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({
    name: model.name,
    model_id: model.model_id,
    base_url: model.base_url || '',
    api_key: '',
    provider_label: model.provider_label || '',
    device: model.device || 'auto',
    local_backend: model.local_backend || 'sentence_transformers',
  })
  const [modalError, setModalError] = useState('')

  const handleTest = async () => {
    setBusy(true)
    try {
      const data = await testModel(model.id)
      if (data.ok) {
        const detail =
          model.model_type === 'embedding' && data.dimension
            ? `${data.dimension} dims`
            : `${Math.round(data.latency_ms)} ms`
        notify?.('success', 'Connected', `${model.name} · ${detail}`)
      } else {
        notify?.('error', 'Test failed', data.detail || `Could not reach ${model.name}.`)
      }
      onChanged?.()
    } catch (err) {
      notify?.('error', 'Test failed', err.message || `Could not reach ${model.name}.`)
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async () => {
    if (!window.confirm(`Delete “${model.name}”? This cannot be undone.`)) return
    setBusy(true)
    try {
      await deleteModel(model.id)
      onDeleted?.(model.id)
    } catch (err) {
      notify?.('error', 'Delete failed', err.message)
      setBusy(false)
    }
  }

  const handleSave = async (event) => {
    event?.preventDefault?.()
    setBusy(true)
    setModalError('')
    try {
      const payload = {
        name: draft.name,
        model_id: draft.model_id,
      }
      if (model.runtime === 'local') {
        payload.device = draft.device
        payload.local_backend = draft.local_backend
      } else {
        if (draft.base_url.trim()) payload.base_url = draft.base_url.trim()
        else payload.base_url = ''
        if (draft.api_key) payload.api_key = draft.api_key
        if (model.provider === 'custom') payload.provider_label = draft.provider_label
      }
      await updateModel(model.id, payload)
      setEditing(false)
      setDraft((prev) => ({ ...prev, api_key: '' }))
      notify?.('success', 'Saved', `“${draft.name}” updated.`)
      onChanged?.()
    } catch (err) {
      setModalError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const closeEditor = () => {
    if (!busy) {
      setEditing(false)
      setModalError('')
    }
  }

  return (
    <>
      <article className="mh-card">
        <header className="mh-card-head">
          <span className={`mh-model-glyph is-${model.model_type}`} aria-hidden="true">
            {model.model_type === 'embedding' ? (
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              >
                <circle cx="5" cy="5" r="2.2" />
                <circle cx="19" cy="5" r="2.2" />
                <circle cx="12" cy="12" r="2.2" />
                <circle cx="5" cy="19" r="2.2" />
                <circle cx="19" cy="19" r="2.2" />
              </svg>
            ) : (
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
                <path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z" />
              </svg>
            )}
          </span>
          <div>
            <h3 title={model.name}>{model.name}</h3>
            <div className="mh-card-tags">
              <span className={`mh-tag is-${model.model_type}`}>{typeLabel(model)}</span>
              <span className="mh-tag">{runtimeLabel(model)}</span>
            </div>
          </div>
          <span className={`mh-status ${statusClass(model.status)}`}>
            {STATUS_LABEL[model.status] || model.status}
          </span>
        </header>
        <div
          className="mh-card-provider"
          title={providerDisplayName(model) || providerLabel(model.provider)}
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z" />
            <path d="M12 12l8-4.5M12 12v9M12 12L4 7.5" />
          </svg>
          <span>{providerDisplayName(model)}</span>
        </div>

        <dl className="mh-card-meta">
          <div>
            <dt>Model ID</dt>
            <dd title={model.model_id}>{model.model_id}</dd>
          </div>
          {model.base_url ? (
            <div>
              <dt>Base URL</dt>
              <dd title={model.base_url}>{model.base_url}</dd>
            </div>
          ) : null}
          {model.model_type === 'embedding' ? (
            <div>
              <dt>Dimension</dt>
              <dd>{model.dimension ? `${model.dimension} dims` : 'Detected on test'}</dd>
            </div>
          ) : null}
          <div>
            <dt>API Key</dt>
            <dd>{model.has_api_key ? 'Stored securely' : '—'}</dd>
          </div>
        </dl>

        <div className="mh-card-actions">
          <button className="mh-btn" onClick={handleTest} disabled={busy}>
            {busy ? 'Testing…' : 'Test'}
          </button>
          <button className="mh-btn" onClick={() => setEditing(true)} disabled={busy}>
            Edit
          </button>
          <button className="mh-btn danger" onClick={handleDelete} disabled={busy}>
            Delete
          </button>
        </div>
      </article>

      {editing ? (
        <div className="mh-modal-backdrop" onClick={closeEditor} role="presentation">
          <div
            className="mh-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby={`mh-edit-title-${model.id}`}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === 'Escape') closeEditor()
            }}
          >
            <div className="mh-modal-head">
              <div>
                <h2 id={`mh-edit-title-${model.id}`}>Edit model</h2>
                <p>{model.name}</p>
              </div>
              <button className="mh-modal-close" onClick={closeEditor} aria-label="Close editor">
                <svg
                  width="15"
                  height="15"
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
            <form className="mh-edit" onSubmit={handleSave}>
              <label>
                Name
                <input
                  autoFocus
                  className="mh-input"
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                />
              </label>
              <label>
                Model ID
                <input
                  className="mh-input"
                  value={draft.model_id}
                  onChange={(e) => setDraft({ ...draft, model_id: e.target.value })}
                />
              </label>
              {model.runtime === 'local' ? (
                <>
                  <label>
                    Local Backend
                    <select
                      className="mh-input"
                      value={draft.local_backend}
                      onChange={(e) => setDraft({ ...draft, local_backend: e.target.value })}
                    >
                      {LOCAL_BACKENDS.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Device
                    <select
                      className="mh-input"
                      value={draft.device}
                      onChange={(e) => setDraft({ ...draft, device: e.target.value })}
                    >
                      {DEVICES.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </>
              ) : (
                <>
                  <label>
                    Base URL
                    <input
                      className="mh-input"
                      value={draft.base_url}
                      onChange={(e) => setDraft({ ...draft, base_url: e.target.value })}
                    />
                  </label>
                  {model.provider === 'custom' ? (
                    <label>
                      Custom provider name
                      <input
                        className="mh-input"
                        value={draft.provider_label}
                        onChange={(e) => setDraft({ ...draft, provider_label: e.target.value })}
                        placeholder="e.g. My vLLM server"
                        maxLength={60}
                      />
                    </label>
                  ) : null}
                  <PasswordField
                    id={`mh-edit-key-${model.id}`}
                    label="API Key"
                    value={draft.api_key}
                    onChange={(e) => setDraft({ ...draft, api_key: e.target.value })}
                    placeholder={
                      model.has_api_key ? 'Leave blank to keep current key' : 'Add a key'
                    }
                  />
                </>
              )}
              {modalError ? <div className="mh-message is-error">{modalError}</div> : null}
              <div className="mh-form-actions">
                <button className="mh-btn primary" type="submit" disabled={busy}>
                  Save
                </button>
                <button className="mh-btn" type="button" onClick={closeEditor} disabled={busy}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </>
  )
}

export default function ModelsTab({ models, onChanged, onDeleted }) {
  const [filter, setFilter] = useState('all')
  const [toasts, setToasts] = useState([])
  const toastId = useRef(0)

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  // Card feedback never lives inside the fixed-size cards — test results
  // surface here, top-right, and dismiss themselves.
  const notify = useCallback(
    (kind, title, detail) => {
      const id = (toastId.current += 1)
      setToasts((prev) => [...prev.slice(-3), { id, kind, title, detail }])
      setTimeout(() => dismissToast(id), 6000)
    },
    [dismissToast],
  )

  const visible = models.filter((m) => filter === 'all' || m.model_type === filter)

  if (!models.length) {
    return (
      <div className="mh-empty">
        <p>No models configured yet.</p>
        <p className="mh-hint">
          Use the “Add Model” tab to connect your first LLM or embedding model.
        </p>
      </div>
    )
  }

  return (
    <div className="mh-models">
      <div className="mh-toast-stack" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <button
            key={toast.id}
            type="button"
            className={`mh-toast is-${toast.kind}`}
            onClick={() => dismissToast(toast.id)}
            aria-label={`Dismiss: ${toast.title}`}
          >
            <span className={`mh-toast-icon is-${toast.kind}`} aria-hidden="true">
              {toast.kind === 'success' ? (
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M20 6L9 17l-5-5" />
                </svg>
              ) : (
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 9v4M12 17h.01" />
                  <path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
                </svg>
              )}
            </span>
            <span className="mh-toast-body">
              <span className="mh-toast-title">{toast.title}</span>
              {toast.detail ? <span className="mh-toast-detail">{toast.detail}</span> : null}
            </span>
          </button>
        ))}
      </div>
      <div className="mh-filter-row">
        {[
          { id: 'all', label: 'All' },
          { id: 'llm', label: 'LLM' },
          { id: 'embedding', label: 'Embedding' },
        ].map((option) => (
          <button
            key={option.id}
            className={`mh-filter${filter === option.id ? ' is-active' : ''}`}
            onClick={() => setFilter(option.id)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <div className="mh-empty">
          <p>No {filter} models configured.</p>
        </div>
      ) : (
        <div className="mh-grid">
          {visible.map((model) => (
            <ModelCard
              key={model.id}
              model={model}
              onChanged={onChanged}
              onDeleted={onDeleted}
              notify={notify}
            />
          ))}
        </div>
      )}
    </div>
  )
}
