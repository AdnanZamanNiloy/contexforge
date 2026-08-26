import { useEffect, useState } from 'react';

import RepositoryHeader from './components/RepositoryHeader';
import RepositoryTabs from './components/RepositoryTabs';

import ArchitectureView from './views/ArchitectureView';
import DependencyView from './views/DependencyView';
import DataFlowView from './views/DataFlowView';
import GitHistoryView from './views/GitHistoryView';
import OwnershipView from './views/OwnershipView';
import ChangeImpactView from './views/ChangeImpactView';

const TABS = {
  'architecture': ArchitectureView,
  'dependencies': DependencyView,
  'data-flow': DataFlowView,
  'git-history': GitHistoryView,
  'ownership': OwnershipView,
  'change-impact': ChangeImpactView,
};

const GRAPH_DIMENSIONS = { width: 1240, height: 860 };

// Repository Intelligence as a first-class ContextForge capability.  This is
// the pure content view — it renders inside the shared product shell and owns
// only its sub-view tabs, exactly like every other source capability.
export default function RepositoryIntelligenceView({ analysis, analysisId, reanalyze, loading, error }) {
  const [activeTab, setActiveTab] = useState('architecture');

  const repo = analysis?.repository || {};

  // Cross-view navigation from the insight rail / views.
  useEffect(() => {
    const onChangeImpact = () => setActiveTab('change-impact');
    const onGitHistory = () => setActiveTab('git-history');
    window.addEventListener('repo-intel:change-impact', onChangeImpact);
    window.addEventListener('repo-intel:git-history', onGitHistory);
    return () => {
      window.removeEventListener('repo-intel:change-impact', onChangeImpact);
      window.removeEventListener('repo-intel:git-history', onGitHistory);
    };
  }, []);

  const ActiveView = TABS[activeTab] || ArchitectureView;

  if (error) {
    return (
      <div className="intel-analyzing-card empty-intel">
        <p className="intel-error">{error}</p>
      </div>
    );
  }

  return (
    <div className="intel-card intel-enter">
      <RepositoryHeader repo={repo} onSync={reanalyze} />
      <RepositoryTabs active={activeTab} onChange={setActiveTab} />
      <div className="intel-viewport">
        <ActiveView
          analysisId={analysisId}
          architecture={analysis?.architecture}
          dependencyGraph={analysis?.dependencies}
          gitHistory={analysis?.gitHistory || {}}
          ownership={analysis?.ownership || {}}
          changeImpact={analysis?.changeImpact || { nodes: [], blastRadius: { nodes: [], edges: [] }, estimated: {} }}
          graphDimensions={GRAPH_DIMENSIONS}
        />
      </div>
    </div>
  );
}
