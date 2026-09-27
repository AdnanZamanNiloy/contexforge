import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import AppShell from '../../components/layout/AppShell'
import Sidebar from '../../components/layout/Sidebar'
import { useSources } from '../../hooks/useSources'
import {
  clearKnowledgeBase,
  deleteSource,
  getServing,
  listChains,
  listModels,
} from '../../services/api'
import AddModelTab from './AddModelTab'
import ChainsTab from './ChainsTab'
import ModelsTab from './ModelsTab'
import ServingTab from './ServingTab'

const TABS = [
  { id: 'add', label: 'Add Model' },
  { id: 'models', label: 'Models' },
  { id: 'chains', label: 'Chains' },
  { id: 'serving', label: 'Serving' },
]

const EMPTY_SERVING = {
  llm_mode: 'disabled',
  llm_target: null,
  embedding_mode: 'disabled',
  embedding_target: null,
}

export default function ModelHubPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { sources, loading: sourcesLoading, removeSource, replaceAll } = useSources()

  const requestedTab = searchParams.get('tab') || 'add'
  const tab = TABS.some((t) => t.id === requestedTab) ? requestedTab : 'add'

  const [models, setModels] = useState([])
  const [chains, setChains] = useState([])
  const [serving, setServing] = useState(EMPTY_SERVING)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [modelsData, chainsData, servingData] = await Promise.all([
        listModels(),
        listChains(),
        getServing(),
      ])
      setModels(modelsData)
      setChains(chainsData)
      setServing(servingData)
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const setTab = (next) => {
    setSearchParams({ tab: next }, { replace: true })
  }

  const handleSelectSource = (id) => navigate(`/sources/${encodeURIComponent(id)}`)

  const handleAddSource = () => navigate('/?add=1')

  const handleDeleteSource = async (id) => {
    try {
      await deleteSource(id)
    } catch {
      /* best effort */
    }
    removeSource(id)
  }

  const handleClearKB = async () => {
    try {
      await clearKnowledgeBase()
      replaceAll([])
    } catch {
      /* best effort */
    }
  }

  const counts = useMemo(
    () => ({
      models: models.length,
      chains: chains.length,
    }),
    [models, chains],
  )

  const tabNav = (
    <nav className="mh-tabs" aria-label="Model Hub sections">
      {TABS.map((item) => {
        const count =
          item.id === 'models' ? models.length : item.id === 'chains' ? chains.length : null
        const active = tab === item.id
        return (
          <button
            key={item.id}
            className={active ? 'mh-tab active' : 'mh-tab'}
            aria-current={active ? 'page' : undefined}
            onClick={() => setTab(item.id)}
          >
            {item.label}
            {count !== null ? <span className="mh-tab-count">{count}</span> : null}
          </button>
        )
      })}
    </nav>
  )

  let content
  if (loading) {
    content = <div className="mh-empty">Loading Model Hub…</div>
  } else if (error) {
    content = (
      <div className="mh-empty">
        <p className="mh-error">{error}</p>
        <button className="mh-btn primary" onClick={refresh}>
          Retry
        </button>
      </div>
    )
  } else if (tab === 'add') {
    content = (
      <AddModelTab
        onCreated={(model) => {
          setModels((prev) => [...prev, model])
          setTab('models')
        }}
      />
    )
  } else if (tab === 'models') {
    content = (
      <ModelsTab
        models={models}
        onChanged={refresh}
        onDeleted={(id) => setModels((prev) => prev.filter((m) => m.id !== id))}
      />
    )
  } else if (tab === 'chains') {
    content = <ChainsTab models={models} chains={chains} onChanged={refresh} />
  } else {
    content = <ServingTab models={models} chains={chains} serving={serving} onChanged={refresh} />
  }

  const rightPanel = (
    <section className="panel mh-side-panel">
      <div className="panel-head">
        <h3>Serving status</h3>
        <span className="mh-live-dot" aria-hidden="true" />
      </div>
      <dl className="mh-side-stats">
        <div>
          <dt>
            <span
              className={`mh-dot ${serving.llm_mode === 'disabled' ? 'is-idle' : 'is-live'}`}
              aria-hidden="true"
            />
            LLM
          </dt>
          <dd>{serving.llm_mode === 'disabled' ? 'Env default' : serving.llm_mode}</dd>
        </div>
        <div>
          <dt>
            <span
              className={`mh-dot ${serving.embedding_mode === 'disabled' ? 'is-idle' : 'is-live'}`}
              aria-hidden="true"
            />
            Embedding
          </dt>
          <dd>{serving.embedding_mode === 'disabled' ? 'Env default' : serving.embedding_mode}</dd>
        </div>
        <div>
          <dt>Models</dt>
          <dd>{counts.models}</dd>
        </div>
        <div>
          <dt>Chains</dt>
          <dd>{counts.chains}</dd>
        </div>
      </dl>
      <p className="mh-side-note">Serving changes apply live to the running pipeline.</p>
    </section>
  )

  const main = (
    <div className="mh-page">
      <header className="mh-header">
        <div className="mh-header-text">
          <span className="mh-eyebrow">Inference layer</span>
          <h1>Model Hub</h1>
          <p className="mh-subtitle">
            Connect, test, chain, and serve your LLM and embedding models.
          </p>
        </div>
        <button className="mh-back" onClick={() => navigate('/workspace')}>
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="15 18 9 12 15 6" />
          </svg>
          <span>Back to Chat</span>
        </button>
      </header>
      {tabNav}
      <div className="mh-content">{content}</div>
    </div>
  )

  return (
    <AppShell
      sidebar={
        <Sidebar
          sources={sources}
          loading={sourcesLoading}
          onAddSource={handleAddSource}
          onSelectSource={handleSelectSource}
          onDeleteSource={handleDeleteSource}
          onClearKB={handleClearKB}
          onOpenModelHub={() => setSearchParams({ tab: 'add' }, { replace: true })}
        />
      }
      main={main}
      right={rightPanel}
      layoutClass="explore-layout"
    />
  )
}
