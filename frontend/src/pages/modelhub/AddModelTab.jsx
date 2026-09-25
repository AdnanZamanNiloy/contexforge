import { useState } from 'react'

import { createModel, testModel } from '../../services/api'
import { DEVICES, LOCAL_BACKENDS, MODEL_TYPES, PROVIDERS, RUNTIMES } from './modelHubMeta'

const EMPTY = {
  name: '',
  model_type: 'llm',
  runtime: 'api',
  provider: 'openai',
  model_id: '',
  base_url: '',
  api_key: '',
  local_backend: 'sentence_transformers',
  device: 'auto',
}

// Add a model.  API keys are held only in this component's transient form
// state and posted in the request body — never written to a URL or persisted in
// frontend storage.
export default function AddModelTab({ onCreated }) {
  const [form, setForm] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [message, setMessage] = useState(null)
  const [testResult, setTestResult] = useState(null)

  const update = (key, value) => setForm((prev) => ({ ...prev, [key]: value }))

  const isEmbedding = form.model_type === 'embedding'
  const isLocal = form.runtime === 'local'

  const buildPayload = () => {
    const payload = {
      name: form.name.trim(),
      model_type: form.model_type,
      runtime: form.runtime,
      provider: isLocal ? 'custom' : form.provider,
      model_id: form.model_id.trim(),
    }
    if (isLocal) {
      payload.local_backend = form.local_backend
      payload.device = form.device
    } else {
      if (form.base_url.trim()) payload.base_url = form.base_url.trim()
      if (form.api_key) payload.api_key = form.api_key
    }
    return payload
  }

  const validate = () => {
    if (!form.name.trim()) return 'Model name is required.'
    if (!form.model_id.trim()) {
      return isLocal ? 'Model ID / path is required.' : 'Model ID is required.'
    }
    return null
  }

  const handleSave = async (event) => {
    event.preventDefault()
    const error = validate()
    if (error) {
      setMessage({ type: 'error', text: error })
      return
    }
    setSaving(true)
    setMessage(null)
    try {
      const created = await createModel(buildPayload())
      setMessage({ type: 'success', text: `Added “${created.name}”.` })
      setForm(EMPTY)
      setTestResult(null)
      onCreated?.(created)
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    } finally {
      setSaving(false)
    }
  }

  // Save, then immediately test the freshly-created model so the user gets
  // real connection feedback (and embedding dimension) in one step.
  const handleSaveAndTest = async () => {
    const error = validate()
    if (error) {
      setMessage({ type: 'error', text: error })
      return
    }
    setSaving(true)
    setTesting(true)
    setMessage(null)
    setTestResult(null)
    try {
      const created = await createModel(buildPayload())
      setForm(EMPTY)
      const result = await testModel(created.id)
      setTestResult(result)
      onCreated?.(created)
      if (result.ok) {
        setMessage({
          type: 'success',
          text: isEmbedding
            ? `Connected — detected ${result.dimension ?? '?'} dimensions.`
            : `Connected in ${Math.round(result.latency_ms)} ms.`,
        })
      } else {
        setMessage({ type: 'error', text: result.detail || 'Test failed.' })
      }
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    } finally {
      setSaving(false)
      setTesting(false)
    }
  }

  return (
    <form className="mh-form" onSubmit={handleSave}>
      <div className="mh-form-section">
        <div className="mh-field">
          <label>Model Type</label>
          <div className="mh-choice-row">
            {MODEL_TYPES.map((type) => (
              <button
                type="button"
                key={type.id}
                className={`mh-choice${form.model_type === type.id ? ' is-active' : ''}`}
                onClick={() => update('model_type', type.id)}
              >
                <span className="mh-choice-label">{type.label}</span>
                <span className="mh-choice-hint">{type.hint}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="mh-field">
          <label>Runtime</label>
          <div className="mh-choice-row">
            {RUNTIMES.map((runtime) => (
              <button
                type="button"
                key={runtime.id}
                className={`mh-choice${form.runtime === runtime.id ? ' is-active' : ''}`}
                onClick={() => update('runtime', runtime.id)}
              >
                <span className="mh-choice-label">{runtime.label}</span>
                <span className="mh-choice-hint">{runtime.hint}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="mh-field">
          <label htmlFor="mh-name">Model Name</label>
          <input
            id="mh-name"
            className="mh-input"
            value={form.name}
            onChange={(e) => update('name', e.target.value)}
            placeholder={isEmbedding ? 'e.g. OpenAI Small Embeddings' : 'e.g. GPT-4o mini'}
          />
        </div>

        {isLocal ? (
          <>
            <div className="mh-field">
              <label htmlFor="mh-model-path">Model ID / Model Path</label>
              <input
                id="mh-model-path"
                className="mh-input"
                value={form.model_id}
                onChange={(e) => update('model_id', e.target.value)}
                placeholder={
                  isEmbedding
                    ? 'e.g. BAAI/bge-small-en-v1.5'
                    : 'e.g. http://127.0.0.1:8080 model name'
                }
              />
              {!isEmbedding ? (
                <small className="mh-hint">
                  Local LLMs are served by a local OpenAI-compatible server (llama.cpp, Ollama,
                  vLLM) on port 8080 by default.
                </small>
              ) : null}
            </div>
            {isEmbedding ? (
              <div className="mh-field">
                <label htmlFor="mh-backend">Local Backend</label>
                <select
                  id="mh-backend"
                  className="mh-input"
                  value={form.local_backend}
                  onChange={(e) => update('local_backend', e.target.value)}
                >
                  {LOCAL_BACKENDS.map((backend) => (
                    <option key={backend.id} value={backend.id}>
                      {backend.label}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
            <div className="mh-field">
              <label htmlFor="mh-device">Device</label>
              <select
                id="mh-device"
                className="mh-input"
                value={form.device}
                onChange={(e) => update('device', e.target.value)}
              >
                {DEVICES.map((device) => (
                  <option key={device.id} value={device.id}>
                    {device.label}
                  </option>
                ))}
              </select>
            </div>
          </>
        ) : (
          <>
            <div className="mh-field">
              <label htmlFor="mh-provider">Provider</label>
              <select
                id="mh-provider"
                className="mh-input"
                value={form.provider}
                onChange={(e) => update('provider', e.target.value)}
              >
                {PROVIDERS.filter((p) => !(isEmbedding && p.id === 'google')).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="mh-field">
              <label htmlFor="mh-model-id">Model ID</label>
              <input
                id="mh-model-id"
                className="mh-input"
                value={form.model_id}
                onChange={(e) => update('model_id', e.target.value)}
                placeholder={isEmbedding ? 'e.g. text-embedding-3-small' : 'e.g. gpt-4o-mini'}
              />
            </div>
            <div className="mh-field">
              <label htmlFor="mh-base-url">Base URL</label>
              <input
                id="mh-base-url"
                className="mh-input"
                value={form.base_url}
                onChange={(e) => update('base_url', e.target.value)}
                placeholder="Optional for known providers — https://api.example.com/v1"
              />
            </div>
            <div className="mh-field">
              <label htmlFor="mh-api-key">API Key</label>
              <input
                id="mh-api-key"
                className="mh-input"
                type="password"
                autoComplete="off"
                value={form.api_key}
                onChange={(e) => update('api_key', e.target.value)}
                placeholder="Stored securely, never returned"
              />
              <small className="mh-hint">
                {isEmbedding
                  ? 'Dimensions are detected automatically when you test the model.'
                  : 'The key is stored server-side and never sent back to the browser.'}
              </small>
            </div>
          </>
        )}
      </div>

      {message ? <div className={`mh-message is-${message.type}`}>{message.text}</div> : null}
      {testResult && !testResult.ok ? (
        <div className="mh-message is-error">{testResult.detail}</div>
      ) : null}

      <div className="mh-form-actions">
        <button className="mh-btn primary" type="submit" disabled={saving}>
          {saving && !testing ? 'Saving…' : 'Add Model'}
        </button>
        <button className="mh-btn" type="button" onClick={handleSaveAndTest} disabled={saving}>
          {testing ? 'Testing…' : 'Add & Test'}
        </button>
      </div>
    </form>
  )
}
