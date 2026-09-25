import { useMemo, useState } from 'react'

import { createChain, deleteChain, testChain, updateChain } from '../../services/api'

function ChainEditor({ models, chainType, onSave, onCancel, saving, initial }) {
  const candidates = useMemo(
    () => models.filter((m) => m.model_type === chainType),
    [models, chainType],
  )
  const [name, setName] = useState(initial?.name || '')
  const [enabled, setEnabled] = useState(initial?.enabled ?? true)
  const [memberIds, setMemberIds] = useState(initial?.model_ids || [])
  const [toAdd, setToAdd] = useState('')

  const available = candidates.filter((m) => !memberIds.includes(m.id))

  const addMember = () => {
    if (toAdd && !memberIds.includes(toAdd)) {
      setMemberIds([...memberIds, toAdd])
      setToAdd('')
    }
  }

  const move = (index, delta) => {
    const next = [...memberIds]
    const target = index + delta
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    setMemberIds(next)
  }

  const removeMember = (id) => setMemberIds(memberIds.filter((m) => m !== id))

  const memberName = (id) => models.find((m) => m.id === id)?.name || id

  return (
    <div className="mh-chain-editor">
      <div className="mh-field">
        <label>Chain Name</label>
        <input
          className="mh-input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={
            chainType === 'llm' ? 'e.g. Primary LLM fallback' : 'e.g. Embedding fallback'
          }
        />
      </div>

      <div className="mh-chain-type-note">
        {chainType === 'llm' ? 'LLM chain' : 'Embedding chain'} — ordered fallback, tried top to
        bottom.
      </div>

      <ol className="mh-chain-members">
        {memberIds.length === 0 ? (
          <li className="mh-chain-empty">No models added yet.</li>
        ) : (
          memberIds.map((id, index) => (
            <li key={id} className="mh-chain-member">
              <span className="mh-chain-index">{index + 1}</span>
              <span className="mh-chain-name">{memberName(id)}</span>
              <div className="mh-chain-member-actions">
                <button type="button" onClick={() => move(index, -1)} title="Move up">
                  ↑
                </button>
                <button type="button" onClick={() => move(index, 1)} title="Move down">
                  ↓
                </button>
                <button type="button" onClick={() => removeMember(id)} title="Remove">
                  ×
                </button>
              </div>
            </li>
          ))
        )}
      </ol>

      <div className="mh-chain-add">
        <select className="mh-input" value={toAdd} onChange={(e) => setToAdd(e.target.value)}>
          <option value="">Add a {chainType} model…</option>
          {available.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name} ({m.model_id})
            </option>
          ))}
        </select>
        <button type="button" className="mh-btn" onClick={addMember} disabled={!toAdd}>
          Add
        </button>
      </div>

      <label className="mh-checkbox">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        Enabled
      </label>

      <div className="mh-form-actions">
        <button
          className="mh-btn primary"
          onClick={() => onSave({ name, model_ids: memberIds, enabled })}
          disabled={saving || !name.trim() || memberIds.length === 0}
        >
          {saving ? 'Saving…' : initial ? 'Save Chain' : 'Create Chain'}
        </button>
        <button className="mh-btn" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </div>
  )
}

export default function ChainsTab({ models, chains, onChanged }) {
  const [creatingType, setCreatingType] = useState(null)
  const [editing, setEditing] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [testResult, setTestResult] = useState(null)

  const modelName = (id) => models.find((m) => m.id === id)?.name || id

  const handleCreate = async (chainType, payload) => {
    setBusy(true)
    setError('')
    try {
      await createChain({ ...payload, chain_type: chainType })
      setCreatingType(null)
      onChanged?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const handleUpdate = async (chainId, payload) => {
    setBusy(true)
    setError('')
    try {
      await updateChain(chainId, payload)
      setEditing(null)
      onChanged?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const handleToggle = async (chain) => {
    setBusy(true)
    setError('')
    try {
      await updateChain(chain.id, { enabled: !chain.enabled })
      onChanged?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async (chain) => {
    if (!window.confirm(`Delete chain “${chain.name}”?`)) return
    setBusy(true)
    try {
      await deleteChain(chain.id)
      onChanged?.()
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  const handleTest = async (chain) => {
    setBusy(true)
    setError('')
    setTestResult(null)
    try {
      const result = await testChain(chain.id)
      setTestResult({ chainId: chain.id, ...result })
      onChanged?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mh-chains">
      <div className="mh-section-head">
        <div>
          <h2>Fallback Chains</h2>
          <p className="mh-hint">If the first model fails, the next one is tried automatically.</p>
        </div>
        {!creatingType && !editing ? (
          <div className="mh-form-actions">
            <button className="mh-btn primary" onClick={() => setCreatingType('llm')}>
              New LLM Chain
            </button>
            <button className="mh-btn" onClick={() => setCreatingType('embedding')}>
              New Embedding Chain
            </button>
          </div>
        ) : null}
      </div>

      {error ? <div className="mh-message is-error">{error}</div> : null}

      {creatingType ? (
        <ChainEditor
          models={models}
          chainType={creatingType}
          saving={busy}
          onSave={(payload) => handleCreate(creatingType, payload)}
          onCancel={() => setCreatingType(null)}
        />
      ) : null}

      {chains.length === 0 && !creatingType ? (
        <div className="mh-empty">
          <p>No chains configured yet.</p>
          <p className="mh-hint">Create a chain to add automatic failover between models.</p>
        </div>
      ) : null}

      <div className="mh-chain-list">
        {chains.map((chain) =>
          editing === chain.id ? (
            <div className="mh-chain-editor" key={chain.id}>
              <ChainEditor
                models={models}
                chainType={chain.chain_type}
                saving={busy}
                initial={chain}
                onSave={(payload) => handleUpdate(chain.id, payload)}
                onCancel={() => setEditing(null)}
              />
            </div>
          ) : (
            <article className="mh-chain-card" key={chain.id}>
              <header className="mh-chain-card-head">
                <div>
                  <h3>{chain.name}</h3>
                  <span className={`mh-tag is-${chain.chain_type}`}>
                    {chain.chain_type === 'embedding' ? 'Embedding' : 'LLM'}
                  </span>
                  <span className={`mh-status ${chain.enabled ? 'is-ready' : 'is-untested'}`}>
                    {chain.enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </div>
              </header>

              <ol className="mh-chain-flow">
                {chain.model_ids.map((id, index) => (
                  <li key={`${id}-${index}`}>
                    <span className="mh-chain-node">{modelName(id)}</span>
                    {index < chain.model_ids.length - 1 ? (
                      <span className="mh-chain-arrow">↓</span>
                    ) : null}
                  </li>
                ))}
                {chain.model_ids.length === 0 ? (
                  <li className="mh-chain-empty">No models in this chain.</li>
                ) : null}
              </ol>

              {testResult && testResult.chainId === chain.id ? (
                <div className={`mh-test-result${testResult.ok ? ' is-ok' : ' is-fail'}`}>
                  {testResult.ok ? (
                    <span>
                      ✓ Chain connected — first working model: {modelName(testResult.used_model_id)}
                    </span>
                  ) : (
                    <span>Chain could not reach any model.</span>
                  )}
                </div>
              ) : null}

              <div className="mh-card-actions">
                <button className="mh-btn" onClick={() => handleTest(chain)} disabled={busy}>
                  Test
                </button>
                <button className="mh-btn" onClick={() => setEditing(chain.id)} disabled={busy}>
                  Edit
                </button>
                <button className="mh-btn" onClick={() => handleToggle(chain)} disabled={busy}>
                  {chain.enabled ? 'Disable' : 'Enable'}
                </button>
                <button
                  className="mh-btn danger"
                  onClick={() => handleDelete(chain)}
                  disabled={busy}
                >
                  Delete
                </button>
              </div>
            </article>
          ),
        )}
      </div>
    </div>
  )
}
