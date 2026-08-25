import { useCallback, useEffect, useState } from 'react';

import RepositoryHeader from './components/RepositoryHeader';
import RepositoryTabs from './components/RepositoryTabs';
import RepositoryInspector from './components/RepositoryInspector';
import RepositoryStats from './components/RepositoryStats';
import RepositoryHealth from './components/RepositoryHealth';
import RepositoryActivity from './components/RepositoryActivity';
import RepositoryAIInput from './components/RepositoryAIInput';

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

export default function RepositoryIntelligencePage() {
  const [activeTab, setActiveTab] = useState('architecture');
  const [selectedNode, setSelectedNode] = useState(null);

  // Cmd/Ctrl+K focuses the repo-level ask input in the header.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        document.querySelector('.repo-ask-input input')?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const handleAsk = useCallback((text) => {
    if (!text) return;
    const s = text.toLowerCase();
    // Wire AI answers to graph highlighting: navigate to architecture for
    // structural questions and highlight the relevant nodes.
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

  const ActiveView = TABS[activeTab] || ArchitectureView;

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
                <span>contextforge</span>
                <span className="kb-count">42</span>
              </div>
              <div className="kb-row">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="4" rx="1" /><rect x="5" y="10" width="14" height="4" rx="1" /><rect x="7" y="17" width="10" height="4" rx="1" /></svg>
                <span>All Documents</span>
                <span className="kb-count">12</span>
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
                  <div className="source-item-title">contextforge</div>
                  <div className="source-item-meta">GitHub Repo • 1284 files</div>
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
            <RepositoryHeader onSync={() => {}} />
            <RepositoryTabs active={activeTab} onChange={setActiveTab} />
            <div className="intel-viewport">
              <ActiveView onSelectChange={setSelectedNode} />
            </div>
            <RepositoryAIInput onAsk={handleAsk} />
          </div>
        </section>

        {/* Right inspector sidebar */}
        <aside className="intel-right">
          <RepositoryInspector node={selectedNode} activeTab={activeTab} />
          <RepositoryStats />
          <RepositoryHealth />
          <RepositoryActivity onViewHistory={() => setActiveTab('git-history')} />
        </aside>
      </div>
    </main>
  );
}
