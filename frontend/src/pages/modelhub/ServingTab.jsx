import { useState } from 'react'

import { updateServing } from '../../services/api'

function TierConfig({ tier, label, models, chains, serving, onSaved }) {
  const [mode, setMode] = useState(serving[`${tier}_mode`] || 'disabled')
  const [target, setTarget] = useState(serving[`${tier}_target`] || '')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)

  const type = tier
  const eligibleModels = models.filter((m) => m.model_type === type)
  const eligibleChains = chains.filter((c) => c.chain_type === type)

  const activeName = (() => {
    if (mode === 'disabled') return null
    if (mode === 'single') return eligibleModels.find((m) => m.id === target)?.name
    return eligibleChains.find((c) => c.id === target)?.name
  })()

  const save = async (nextMode, nextTarget) => {
    setBusy(true)
    setMessage(null)
    try {
      await updateServing({ tier, mode: nextMode, target: nextTarget || null })
      setMessage({ type: 'success', text: `${label} serving updated.` })
      onSaved?.()
    } catch (err) {
      setMessage({ type: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const handleApply = () => {
    if (mode !== 'disabled' && !target) {
      setMessage({ type: 'error', text: 'Select a model or chain first.' })
      return
    }
    save(mode, target)
  }

  const handleDisable = () => {
    setMode('disabled')
    setTarget('')
    save('disabled', null)
  }

  const options = mode === 'chain' ? eligibleChains : eligibleModels

  return (
    <section className="mh-serving-tier">
      <header className="mh-serving-head">
        <h2>{label}</h2>
        <span className={`mh-status ${mode === 'disabled' ? 'is-untested' : 'is-ready'}`}>
          {mode === 'disabled' ? 'Using environment default' : `Serving: ${activeName || target}`}
        </span>
      </header>

      <div className="mh-choice-row">
        {[
          { id: 'single', label: 'Single Model' },
          { id: 'chain', label: 'Chain' },
        ].map((option) => (
          <button
            key={option.id}
            type="button"
            className={`mh-choice${mode === option.id ? ' is-active' : ''}`}
            onClick={() => {
              setMode(option.id)
              setTarget('')
            }}
          >
            <span className="mh-choice-label">{option.label}</span>
          </button>
        ))}
      </div>

      {mode !== 'disabled' ? (
        <div className="mh-field">
          <label>{mode === 'chain' ? 'Chain' : 'Model'}</label>
          <select className="mh-input" value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">Select…</option>
            {options.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
          {options.length === 0 ? (
            <small className="mh-hint">
              No {mode === 'chain' ? 'chains' : `${type} models`} available. Create one first.
            </small>
          ) : null}
        </div>
      ) : null}

      {message ? <div className={`mh-message is-${message.type}`}>{message.text}</div> : null}

      <div className="mh-form-actions">
        <button
          className="mh-btn primary"
          onClick={handleApply}
          disabled={busy || mode === 'disabled'}
        >
          {busy ? 'Applying…' : `Apply ${mode === 'chain' ? 'Chain' : 'Model'}`}
        </button>
        <button className="mh-btn" onClick={handleDisable} disabled={busy}>
          Disable / Use Default
        </button>
      </div>
    </section>
  )
}

export default function ServingTab({ models, chains, serving, onChanged }) {
  return (
    <div className="mh-serving">
      <div className="mh-section-head">
        <div>
          <h2>Serving Configuration</h2>
          <p className="mh-hint">
            Choose which model or chain ContextForge actually uses. Changes take effect immediately
            in the running pipeline.
          </p>
        </div>
      </div>

      <TierConfig
        key={`llm-${serving.llm_mode}-${serving.llm_target}`}
        tier="llm"
        label="LLM"
        models={models}
        chains={chains}
        serving={serving}
        onSaved={onChanged}
      />
      <TierConfig
        key={`embedding-${serving.embedding_mode}-${serving.embedding_target}`}
        tier="embedding"
        label="Embedding"
        models={models}
        chains={chains}
        serving={serving}
        onSaved={onChanged}
      />
    </div>
  )
}
