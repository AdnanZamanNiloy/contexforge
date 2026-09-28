import { useState } from 'react'

import { createModel, testModel } from '../../services/api'
import PasswordField from './PasswordField'
import { DEVICES, LOCAL_BACKENDS, MODEL_TYPES, PROVIDERS, RUNTIMES } from './modelHubMeta'

const EMPTY = {
  name: '',
  model_type: 'llm',
  runtime: 'api',
  provider: 'openai',
  provider_label: '',
  model_id: '',
  base_url: '',
  api_key: '',
  local_backend: 'sentence_transformers',
  device: 'auto',
}

const STEPS = [
  { id: 1, label: 'Model type', hint: 'LLM or embedding' },
  { id: 2, label: 'Runtime', hint: 'API or local' },
  { id: 3, label: 'Details', hint: 'Connect it' },
]

function TypeGlyph({ kind }) {
  if (kind === 'embedding') {
    return (
      <svg
        width="22"
        height="22"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        aria-hidden="true"
      >
        <circle cx="5" cy="5" r="2.2" />
        <circle cx="19" cy="5" r="2.2" />
        <circle cx="12" cy="12" r="2.2" />
        <circle cx="5" cy="19" r="2.2" />
        <circle cx="19" cy="19" r="2.2" />
      </svg>
    )
  }
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
      <path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z" />
    </svg>
  )
}

function RuntimeGlyph({ kind }) {
  if (kind === 'local') {
    return (
      <svg
        width="22"
        height="22"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <rect x="2" y="4" width="20" height="13" rx="2" />
        <path d="M8 21h8M12 17v4" />
      </svg>
    )
  }
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z" />
    </svg>
  )
}

// Add a model as a guided 3-step flow.  API keys are held only in this
// component's transient form state and posted in the request body — never
// written to a URL or persisted in frontend storage.
export default function AddModelTab({ onCreated }) {
  const [form, setForm] = useState(EMPTY)
  const [step, setStep] = useState(1)
  const [visited, setVisited] = useState(1)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [message, setMessage] = useState(null)
  const [testResult, setTestResult] = useState(null)

  const update = (key, value) => setForm((prev) => ({ ...prev, [key]: value }))

  const isEmbedding = form.model_type === 'embedding'
  const isLocal = form.runtime === 'local'
  const providerOptions = PROVIDERS.filter((p) => !(isEmbedding && p.id === 'google'))

  const updateType = (id) => {
    setForm((prev) => ({
      ...prev,
      model_type: id,
      // Google offers no embedding API — fall back instead of keeping a
      // hidden, invalid provider selection.
      provider: id === 'embedding' && prev.provider === 'google' ? 'openai' : prev.provider,
    }))
  }

  const goTo = (id) => {
    if (id <= visited) {
      setStep(id)
      setMessage(null)
    }
  }

  const goNext = () => {
    const next = Math.min(3, step + 1)
    setVisited((prev) => Math.max(prev, next))
    setStep(next)
    setMessage(null)
  }

  const goBack = () => {
    setStep((prev) => Math.max(1, prev - 1))
    setMessage(null)
  }

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
      if (form.provider === 'custom' && form.provider_label.trim()) {
        payload.provider_label = form.provider_label.trim()
      }
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
      setStep(1)
      setVisited(1)
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
      setStep(1)
      setVisited(1)
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

  const stepValue = (id) => {
    if (id === 1) return form.model_type === 'embedding' ? 'Embedding' : 'LLM'
    if (id === 2) return isLocal ? 'Local' : 'API'
    return form.name.trim() || form.model_id.trim() || '—'
  }

  return (
    <form className="mh-form mh-wizard" onSubmit={handleSave}>
      <ol className="mh-steps" aria-label="Add model progress">
        {STEPS.map((item) => {
          const active = item.id === step
          const done = !active && item.id <= visited
          return (
            <li key={item.id}>
              <button
                type="button"
                className={`mh-step${active ? ' is-active' : ''}${done ? ' is-done' : ''}`}
                aria-current={active ? 'step' : undefined}
                onClick={() => goTo(item.id)}
                disabled={item.id > visited}
              >
                <span className="mh-step-index" aria-hidden="true">
                  {done ? '✓' : item.id}
                </span>
                <span className="mh-step-text">
                  <span className="mh-step-label">{item.label}</span>
                  <span className="mh-step-value">
                    {done || active ? stepValue(item.id) : item.hint}
                  </span>
                </span>
              </button>
            </li>
          )
        })}
      </ol>

      {step === 1 ? (
        <div className="mh-step-panel" key="step-1">
          <div className="mh-field">
            <label id="mh-type-label">What kind of model is this?</label>
            <div className="mh-type-grid" role="group" aria-labelledby="mh-type-label">
              {MODEL_TYPES.map((type) => (
                <button
                  type="button"
                  key={type.id}
                  className={`mh-type-card${form.model_type === type.id ? ' is-active' : ''}`}
                  aria-pressed={form.model_type === type.id}
                  onClick={() => updateType(type.id)}
                >
                  <span className={`mh-model-glyph is-${type.id}`}>
                    <TypeGlyph kind={type.id} />
                  </span>
                  <span className="mh-type-card-text">
                    <span className="mh-choice-label">{type.label}</span>
                    <span className="mh-choice-hint">
                      {type.id === 'llm'
                        ? 'Answers questions and generates text for your workspace.'
                        : 'Turns your sources into searchable vectors.'}
                    </span>
                  </span>
                  <span className="mh-type-check" aria-hidden="true">
                    ✓
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      {step === 2 ? (
        <div className="mh-step-panel" key="step-2">
          <div className="mh-field">
            <label id="mh-runtime-label">How does it run?</label>
            <div className="mh-type-grid" role="group" aria-labelledby="mh-runtime-label">
              {RUNTIMES.map((runtime) => (
                <button
                  type="button"
                  key={runtime.id}
                  className={`mh-type-card${form.runtime === runtime.id ? ' is-active' : ''}`}
                  aria-pressed={form.runtime === runtime.id}
                  onClick={() => update('runtime', runtime.id)}
                >
                  <span className="mh-model-glyph is-slate">
                    <RuntimeGlyph kind={runtime.id} />
                  </span>
                  <span className="mh-type-card-text">
                    <span className="mh-choice-label">{runtime.label}</span>
                    <span className="mh-choice-hint">
                      {runtime.id === 'api'
                        ? 'A hosted provider endpoint, billed by usage.'
                        : 'Self-hosted on this machine — private, no usage fees.'}
                    </span>
                  </span>
                  <span className="mh-type-check" aria-hidden="true">
                    ✓
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      {step === 3 ? (
        <div className="mh-step-panel" key="step-3">
          <div className="mh-details-grid">
            <div className="mh-details-main">
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
                        Local LLMs are served by a local OpenAI-compatible server (llama.cpp,
                        Ollama, vLLM) on port 8080 by default.
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
                    <label id="mh-provider-label">Provider</label>
                    <div
                      className="mh-provider-grid"
                      role="radiogroup"
                      aria-labelledby="mh-provider-label"
                    >
                      {providerOptions.map((p) => (
                        <button
                          type="button"
                          key={p.id}
                          role="radio"
                          aria-checked={form.provider === p.id}
                          className={`mh-provider-chip${form.provider === p.id ? ' is-active' : ''}`}
                          onClick={() => update('provider', p.id)}
                        >
                          {p.label}
                        </button>
                      ))}
                    </div>
                    {form.provider === 'custom' ? (
                      <div className="mh-field" style={{ marginTop: '12px' }}>
                        <label htmlFor="mh-custom-provider">Custom provider name</label>
                        <input
                          id="mh-custom-provider"
                          className="mh-input"
                          value={form.provider_label}
                          onChange={(e) => update('provider_label', e.target.value)}
                          placeholder="e.g. My vLLM server"
                          maxLength={60}
                        />
                        <small className="mh-hint">
                          Shown across the Model Center instead of “Custom”. Routing still uses your
                          Base URL.
                        </small>
                      </div>
                    ) : null}
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
                    <PasswordField
                      id="mh-api-key"
                      label="API Key"
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

            <aside className="mh-summary" aria-label="Configuration summary">
              <h3>Summary</h3>
              <dl>
                <div>
                  <dt>Type</dt>
                  <dd>{isEmbedding ? 'Embedding' : 'LLM'}</dd>
                </div>
                <div>
                  <dt>Runtime</dt>
                  <dd>{isLocal ? 'Local' : 'API'}</dd>
                </div>
                <div>
                  <dt>{isLocal ? 'Backend' : 'Provider'}</dt>
                  <dd>
                    {isLocal
                      ? LOCAL_BACKENDS.find((b) => b.id === form.local_backend)?.label ||
                        form.local_backend
                      : form.provider === 'custom' && form.provider_label.trim()
                        ? form.provider_label.trim()
                        : providerOptions.find((p) => p.id === form.provider)?.label ||
                          form.provider}
                  </dd>
                </div>
                <div>
                  <dt>Model</dt>
                  <dd>{form.model_id.trim() || '—'}</dd>
                </div>
                {!isLocal ? (
                  <div>
                    <dt>API key</dt>
                    <dd>{form.api_key ? 'Provided' : 'Missing'}</dd>
                  </div>
                ) : null}
              </dl>
              <p className="mh-hint">Add &amp; Test verifies the connection before you serve it.</p>
            </aside>
          </div>
        </div>
      ) : null}

      {message ? <div className={`mh-message is-${message.type}`}>{message.text}</div> : null}
      {testResult && !testResult.ok ? (
        <div className="mh-message is-error">{testResult.detail}</div>
      ) : null}

      <div className="mh-form-actions mh-wizard-nav">
        {step > 1 ? (
          <button type="button" className="mh-btn" onClick={goBack} disabled={saving}>
            Back
          </button>
        ) : null}
        {step < 3 ? (
          <button type="button" className="mh-btn primary" onClick={goNext}>
            Continue
          </button>
        ) : (
          <>
            <button className="mh-btn primary" type="submit" disabled={saving}>
              {saving && !testing ? 'Saving…' : 'Add Model'}
            </button>
            <button className="mh-btn" type="button" onClick={handleSaveAndTest} disabled={saving}>
              {testing ? 'Testing…' : 'Add & Test'}
            </button>
          </>
        )}
      </div>
    </form>
  )
}
