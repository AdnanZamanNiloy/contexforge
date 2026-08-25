import { useCallback, useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';

import RepositoryHeader from './components/RepositoryHeader';
import RepositoryTabs from './components/RepositoryTabs';
import RepositoryStats from './components/RepositoryStats';
import RepositoryHealth from './components/RepositoryHealth';
import RepositoryActivity from './components/RepositoryActivity';
import RepositoryAIInput from './components/RepositoryAIInput';
import RepositoryAnswerPanel from './components/RepositoryAnswerPanel';

import ArchitectureView from './views/ArchitectureView';
import DependencyView from './views/DependencyView';
import DataFlowView from './views/DataFlowView';
import GitHistoryView from './views/GitHistoryView';
import OwnershipView from './views/OwnershipView';
import ChangeImpactView from './views/ChangeImpactView';

import { repositoryAsk } from '../../services/api';
import { useRepository } from '../../hooks/useRepository';

const TABS = {
  'architecture': ArchitectureView,
  'dependencies': DependencyView,
  'data-flow': DataFlowView,
  'git-history': GitHistoryView,
  'ownership': OwnershipView,
  'change-impact': ChangeImpactView,
};

const GRAPH_DIMENSIONS = { width: 1240, height: 860 };

export default function RepositoryIntelligencePage() {
  const { repositoryId } = useParams();
  const [searchParams] = useSearchParams();
  const repoUrl = searchParams.get('repoUrl') || undefined;

  const { id, analysis, status, loading, error, reanalyze } = useRepository({
    repositoryId,
    repoUrl,
  });

  const [activeTab, setActiveTab] = useState('architecture');

  // Live AI answer state, lifted here so <RepositoryAnswerPanel/> (rendered
  // between the tabs and the visualization) can reserve space and stream while
  // the repository graph stays in normal flow below it.
  const [aiQuestion, setAiQuestion] = useState('');
  const [aiAnswer, setAiAnswer] = useState('');
  const [aiSources, setAiSources] = useState([]);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState('');

  // Wire AI answers to graph highlighting: navigate to architecture for
  // structural questions and highlight the relevant nodes.
  const handleTabHint = useCallback((text) => {
    if (!text) return;
    const s = text.toLowerCase();
    if (/pipeline|flow|retriev|ingest|query|depend|risk|architect|coupl/.test(s)) {
      setActiveTab('architecture');
    } else if (/change|impact|blast|affected/.test(s)) {
      setActiveTab('change-impact');
    } else {
      setActiveTab('architecture');
    }
  }, []);

  // Cross-view "View Change Impact" navigation.
  useEffect(() => {
    const onChangeImpact = () => setActiveTab('change-impact');
    window.addEventListener('repo-intel:change-impact', onChangeImpact);
    return () => window.removeEventListener('repo-intel:change-impact', onChangeImpact);
  }, []);

  const streamAnswer = useCallback(
    (text, handlers) => {
      if (!id) {
        handlers.onError?.('No analysis available.');
        return Promise.resolve();
      }
      return repositoryAsk(id, text, handlers);
    },
    [id],
  );

  // Kick off a question: reset the answer panel (reserving its space), then
  // stream tokens into it while keeping the repository visualization below.
  const handleAsk = useCallback(
    (text, askFn) => {
      if (!text) return;
      setAiQuestion(text);
      setAiAnswer('');
      setAiSources([]);
      setAiError('');
      setAiLoading(true);
      askFn(text, {
        onToken: (token) => {
          // First token marks the start of the streamed answer, so drop the
          // placeholder and reveal the answer as it arrives.
          setAiLoading(false);
          setAiAnswer((prev) => prev + token);
        },
        onSources: (next) => setAiSources(next || []),
        onError: (msg) => setAiError(msg || 'Something went wrong'),
      })
        .catch((err) => setAiError(err.message || 'Something went wrong'))
        .finally(() => setAiLoading(false));
    },
    [],
  );

  const ActiveView = TABS[activeTab] || ArchitectureView;

  if (loading && !analysis) {
    return (
      <main className="app-shell intel-shell">
        <div className="intel-loading">
          <div className="intel-spinner" />
          <p>{status ? `Analyzing repository… ${status.progress || 0}%` : 'Loading repository analysis…'}</p>
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="app-shell intel-shell">
        <div className="intel-loading">
          <p className="intel-error">{error}</p>
        </div>
      </main>
    );
  }

  const repo = analysis?.repository || {};
  const stats = repo;

  return (
    <main className="app-shell intel-shell">
      <div className="app-layout intel-layout">
        {/* Left sidebar — preserved ContextForge chrome */}
        <aside className="sidebar-shell intel-sidebar">
          <div className="brand">
            <div className="brand-mark" aria-hidden="true">
              <img src="/logos/project_logo.png" alt="ContextForge" />
            </div>
            <div className="brand-text">
              <span className="brand-title">
                Context<span className="brand-title-accent">Forge</span>
              </span>
              <small>Grounded AI Workspace</small>
            </div>
          </div>

          <button className="add-knowledge-btn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
            <span>Add Source</span>
          </button>

          <section className="kb-section">
            <div className="section-title">Repository Intelligence</div>
            <div className="kb-rows">
              <div className="kb-row active">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9V5a2 2 0 0 1 2-2h4M15 3h4a2 2 0 0 1 2 2v4M21 15v4a2 2 0 0 1-2 2h-4M9 21H5a2 2 0 0 1-2-2v-4" /></svg>
                <span>{repo.name || 'repository'}</span>
                <span className="kb-count">{repo.modules || 0}</span>
              </div>
            </div>
          </section>

          <section className="sources-section">
            <div className="section-title"><span>My Sources</span></div>
            <div className="source-list">
              <div className="source-item-compact">
                <div className="source-item-icon is-github">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" /></svg>
                </div>
                <div className="source-item-body">
                  <div className="source-item-title">{repo.name || 'repository'}</div>
                  <div className="source-item-meta">GitHub Repo • {repo.files || 0} files</div>
                </div>
                <div className="source-item-status"><span className="status-dot is-indexed" /></div>
              </div>
            </div>
          </section>

          <div className="sidebar-spacer" />

          <div className="status-card">
            <div className="status-card-header">Repository Status</div>
            <div className="status-card-body">
              <div className="status-card-row"><span className="status-dot is-indexed" /><span>Indexed & analyzed</span></div>
              <div className="status-card-row"><span className="status-dot is-indexed" /><span>All pipelines idle</span></div>
            </div>
          </div>
        </aside>

        {/* Center workspace */}
        <section className="main-shell intel-main">
          <div className="intel-card">
            <RepositoryHeader repo={repo} onSync={reanalyze} />
            <RepositoryTabs active={activeTab} onChange={setActiveTab} />
            <RepositoryAnswerPanel
              question={aiQuestion}
              answer={aiAnswer}
              sources={aiSources}
              loading={aiLoading}
              error={aiError}
            />
            <div className="intel-viewport">
              <ActiveView
                analysisId={id}
                architecture={analysis.architecture}
                dependencyGraph={analysis.dependencies}
                gitHistory={analysis.gitHistory || {}}
                ownership={analysis.ownership || {}}
                changeImpact={analysis.changeImpact || { nodes: [], blastRadius: { nodes: [], edges: [] }, estimated: {} }}
                graphDimensions={GRAPH_DIMENSIONS}
              />
            </div>
            <RepositoryAIInput
              suggestedQuestions={analysis.suggestedQuestions}
              streamAnswer={streamAnswer}
              onTabHint={handleTabHint}
              onAsk={handleAsk}
            />
          </div>
        </section>

        {/* Right sidebar — repository-level information only */}
        <aside className="intel-right">
          <RepositoryStats stats={repo} />
          <RepositoryHealth health={analysis.health || {}} rankedModules={analysis.rankedModules || []} />
          <RepositoryActivity activity={analysis.activity || []} onViewHistory={() => setActiveTab('git-history')} />
        </aside>
      </div>
    </main>
  );
}
