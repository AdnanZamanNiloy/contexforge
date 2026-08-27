import { useParams } from 'react-router-dom'
import { useNavigate } from 'react-router-dom'

import AppShell from '../../components/layout/AppShell'
import Sidebar from '../../components/layout/Sidebar'
import RepositoryIntelligenceView from './RepositoryIntelligenceView'
import RepositoryInsights from './RepositoryInsights'
import RepositoryAnalysisLoading from './components/RepositoryAnalysisLoading'

import { useRepository } from '../../hooks/useRepository'
import { useSources } from '../../hooks/useSources'
import { clearKnowledgeBase, deleteSource } from '../../services/api'

// Deep-link entry point for Repository Intelligence.
//
// A GitHub repository is a ContextForge source, and Repository Intelligence is
// its specialised capability.  This page renders that capability inside the
// shared product shell (same sidebar, same chrome) so a /repository/{id} link
// lands in the same workspace instead of a separate application.
export default function RepositoryIntelligencePage() {
  const { repositoryId } = useParams()
  const navigate = useNavigate()
  const { sources, loading, removeSource, replaceAll } = useSources()
  const repository = useRepository({ repositoryId })

  const handleDeleteSource = async (id) => {
    try {
      await deleteSource(id)
    } catch {
      /* best effort */
    }
    removeSource(id)
  }

  const handleSelectSource = (id) => navigate(`/sources/${encodeURIComponent(id)}`)

  const handleClearKB = async () => {
    try {
      await clearKnowledgeBase()
      replaceAll([])
    } catch {
      /* best effort */
    }
    navigate('/')
  }

  let main
  if (repository.loading && !repository.analysis) {
    main = (
      <RepositoryAnalysisLoading
        embedded
        name={repository.status?.name || 'repository'}
        progress={repository.status?.progress || 0}
        status={repository.status?.status || 'queued'}
      />
    )
  } else if (repository.error && !repository.analysis) {
    main = (
      <div className="intel-analyzing-card empty-intel">
        <p className="intel-error">{repository.error}</p>
        <button className="primary" onClick={() => navigate('/')}>
          Back to workspace
        </button>
      </div>
    )
  } else {
    main = (
      <RepositoryIntelligenceView
        analysis={repository.analysis}
        analysisId={repository.id}
        reanalyze={repository.reanalyze}
        loading={repository.loading}
        error={repository.error}
      />
    )
  }

  return (
    <AppShell
      sidebar={
        <Sidebar
          sources={sources}
          loading={loading}
          onAddSource={() => navigate('/?add=1')}
          onSelectSource={handleSelectSource}
          onDeleteSource={handleDeleteSource}
          onClearKB={handleClearKB}
        />
      }
      main={<div className="explore-main">{main}</div>}
      right={
        repository.analysis ? (
          <RepositoryInsights
            analysis={repository.analysis}
            onViewHistory={() => window.dispatchEvent(new Event('repo-intel:git-history'))}
          />
        ) : (
          <section className="panel">
            <div className="panel-head">
              <h3>Loading</h3>
            </div>
            <div className="empty" style={{ padding: '20px 0' }}>
              Analyzing repository…
            </div>
          </section>
        )
      }
      layoutClass="explore-layout"
    />
  )
}
