import { useState } from 'react'

import { deleteModel, testModel, updateModel } from '../../services/api'
import {
  DEVICES,
  LOCAL_BACKENDS,
  providerLabel,
  runtimeLabel,
  STATUS_LABEL,
  statusClass,
  typeLabel,
} from './modelHubMeta'

function ModelCard({ model, onChanged, onDeleted }) {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({
    name: model.name,
    model_id: model.model_id,
    base_url: model.base_url || '',
    api_key: '',
    device: model.device || 'auto',
    local_backend: model.local_backend || 'sentence_transformers',
  })
  const [error, setError] = useState('')

  const handleTest = async () => {
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const data = await testModel(model.id)
      setResult(data)
      onChanged?.()
    } catch (err) {
      setError(err.message)
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
      setError(err.message)
      setBusy(false)
    }
  }

  const handleSave = async () => {
    setBusy(true)
    setError('')
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
      }
      await updateModel(model.id, payload)
      setEditing(false)
      setDraft((prev) => ({ ...prev, api_key: '' }))
      onChanged?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <article className="mh-card">
      <header className="mh-card-head">
        <div>
          <h3>{model.name}</h3>
          <div className="mh-card-tags">
            <span className={`mh-tag is-${model.model_type}`}>{typeLabel(model)}</span>
            <span className="mh-tag">{runtimeLabel(model)}</span>
            <span className="mh-tag">{providerLabel(model.provider)}</span>
          </div>
        </div>
        <span className={`mh-status ${statusClass(model.status)}`}>
          {STATUS_LABEL[model.status] || model.status}
        </span>
      </header>

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

      {model.status_detail ? <p className="mh-card-detail">{model.status_detail}</p> : null}

      {result ? (
        <div className={`mh-test-result${result.ok ? ' is-ok' : ' is-fail'}`}>
          {result.ok ? (
            <>
              <span>✓ Connected</span>
              <span>{Math.round(result.latency_ms)} ms</span>
              {result.dimension ? <span>{result.dimension} dims</span> : null}
              {result.response ? <span className="mh-test-response">{result.response}</span> : null}
            </>
          ) : (
            <span>{result.detail || 'Test failed'}</span>
          )}
        </div>
      ) : null}

      {error ? <div className="mh-message is-error">{error}</div> : null}

      {editing ? (
        <div className="mh-edit">
          <label>
            Name
            <input
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
              <label>
                API Key
                <input
                  className="mh-input"
                  type="password"
                  autoComplete="off"
                  placeholder={model.has_api_key ? 'Leave blank to keep current key' : 'Add a key'}
                  value={draft.api_key}
                  onChange={(e) => setDraft({ ...draft, api_key: e.target.value })}
                />
              </label>
            </>
          )}
          <div className="mh-form-actions">
            <button className="mh-btn primary" onClick={handleSave} disabled={busy}>
              Save
            </button>
            <button className="mh-btn" onClick={() => setEditing(false)} disabled={busy}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
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
      )}
    </article>
  )
}

export default function ModelsTab({ models, onChanged, onDeleted }) {
  const [filter, setFilter] = useState('all')

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
            <ModelCard key={model.id} model={model} onChanged={onChanged} onDeleted={onDeleted} />
          ))}
        </div>
      )}
    </div>
  )
}
