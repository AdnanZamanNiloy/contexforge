import { useEffect, useState } from 'react'

import RepositoryTabs from './components/RepositoryTabs'

import ArchitectureView from './views/ArchitectureView'
import DependencyView from './views/DependencyView'
import DataFlowView from './views/DataFlowView'
import GitHistoryView from './views/GitHistoryView'
import OwnershipView from './views/OwnershipView'
import ChangeImpactView from './views/ChangeImpactView'

const TABS = {
  architecture: ArchitectureView,
  dependencies: DependencyView,
  'data-flow': DataFlowView,
  'git-history': GitHistoryView,
  ownership: OwnershipView,
  'change-impact': ChangeImpactView,
}

const GRAPH_DIMENSIONS = { width: 1240, height: 860 }

// Repository Intelligence as a first-class ContextForge capability. Pure content
// view: it renders inside the shared product shell and owns only the capability
// tabs and the active sub-view.
export default function RepositoryIntelligenceView({ analysis, analysisId, reanalyze, error }) {
  const [activeTab, setActiveTab] = useState('architecture')

  // Cross-view navigation emitted by views / the insight rail.
  useEffect(() => {
    const goChangeImpact = () => setActiveTab('change-impact')
    const goGitHistory = () => setActiveTab('git-history')
    window.addEventListener('repo-intel:change-impact', goChangeImpact)
    window.addEventListener('repo-intel:git-history', goGitHistory)
    return () => {
      window.removeEventListener('repo-intel:change-impact', goChangeImpact)
      window.removeEventListener('repo-intel:git-history', goGitHistory)
    }
  }, [])

  const ActiveView = TABS[activeTab] || ArchitectureView

  if (error) {
    return (
      <div className="intel-card intel-enter">
        <div className="rv-viewport">
          <div className="rv-state rv-state-error rv-state-full">
            <p className="rv-state-title">Repository analysis failed</p>
            <p className="rv-state-hint">{error}</p>
            <button type="button" className="rv-btn rv-btn-primary" onClick={reanalyze}>
              Retry analysis
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="intel-card intel-enter">
      <RepositoryTabs active={activeTab} onChange={setActiveTab} />
      <div className="rv-viewport" role="tabpanel">
        <ActiveView
          analysisId={analysisId}
          architecture={analysis?.architecture}
          dependencyGraph={analysis?.dependencies}
          gitHistory={analysis?.gitHistory || {}}
          ownership={analysis?.ownership || {}}
          changeImpact={
            analysis?.changeImpact || {
              nodes: [],
              blastRadius: { nodes: [], edges: [] },
              estimated: {},
            }
          }
          graphDimensions={GRAPH_DIMENSIONS}
        />
      </div>
    </div>
  )
}
