import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';

import AppShell from '../components/layout/AppShell';
import Sidebar from '../components/layout/Sidebar';
import SourceHeader from '../components/SourceHeader';
import ChatBox from '../components/ChatBox';
import SourceViewer from '../components/SourceViewer';
import MindMapCanvas from '../components/MindMapCanvas';
import RepositoryIntelligenceView from './repository/RepositoryIntelligenceView';
import RepositoryInsights from './repository/RepositoryInsights';
import RepositoryAnalysisLoading from './repository/components/RepositoryAnalysisLoading';

import { useSources } from '../hooks/useSources';
import { useChat } from '../hooks/useChat';
import { useRepository } from '../hooks/useRepository';

import { clearKnowledgeBase, deleteSource } from '../services/api';
import { SourceGlyph, formatSourceMeta, formatTypeLabel, sourceRepoUrl } from '../lib/sources';

const VALID_TABS = ['overview', 'chat', 'intelligence', 'mindmap'];
const DEFAULT_TAB = 'overview';

export default function SourceExplorePage() {
  const { sourceId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get('tab') || DEFAULT_TAB;

  const {
    sources,
    loading: sourcesLoading,
    refresh,
    removeSource,
    replaceAll,
  } = useSources();

  const source = sources.find((s) => s.id === sourceId) || null;

  const chat = useChat({ sourceId });

  // Fullscreen for the mind map tab.
  const mindmapRef = useRef(null);
  const [isMindmapFullscreen, setIsMindmapFullscreen] = useState(false);

  const toggleMindmapFullscreen = useCallback(() => {
    const el = mindmapRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      document.exitFullscreen?.();
    } else {
      el.requestFullscreen?.();
    }
  }, []);

  useEffect(() => {
    const onFullscreenChange = () => {
      setIsMindmapFullscreen(!!document.fullscreenElement);
      window.dispatchEvent(new Event('resize'));
    };
    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange);
  }, []);

  // Reset the in-page thread whenever we are exploring a different source.
  useEffect(() => {
    chat.resetChat();
  }, [sourceId]);

  const isGithub = source?.type === 'github';
  const repoUrl = isGithub ? sourceRepoUrl(source) : undefined;
  const repository = useRepository({ repoUrl });

  // Resolve the active tab to a valid one for this source.
  const availableTabs = useMemo(() => {
    const tabs = ['overview', 'chat'];
    if (isGithub) tabs.push('intelligence');
    tabs.push('mindmap');
    return tabs;
  }, [isGithub]);

  const tab = availableTabs.includes(requestedTab) ? requestedTab : DEFAULT_TAB;

  const setTab = (next) => {
    setSearchParams(next === DEFAULT_TAB ? {} : { tab: next }, { replace: true });
  };

  const handleDelete = async (id) => {
    try { await deleteSource(id); } catch { /* best effort */ }
    removeSource(id);
    if (id === sourceId) navigate('/');
  };

  const handleClearKB = async () => {
    try { await clearKnowledgeBase(); replaceAll([]); chat.resetChat(); } catch { /* ignore */ }
  };

  if (sourcesLoading && !source) {
    return (
      <AppShell
        sidebar={<Sidebar sources={sources} loading onAddSource={() => navigate('/?add=1')} />}
        main={<div className="explore-loading">Loading source…</div>}
      />
    );
  }

  if (!source) {
    return (
      <AppShell
        sidebar={<Sidebar sources={sources} onAddSource={() => navigate('/?add=1')} />}
        main={(
          <div className="explore-empty">
            <p>This source could not be found. It may have been deleted.</p>
            <button className="primary" onClick={() => navigate('/')}>Back to workspace</button>
          </div>
        )}
      />
    );
  }

  const rightPanel = tab === 'intelligence' ? (
    repository.analysis ? (
      <RepositoryInsights
        analysis={repository.analysis}
        onViewHistory={() => window.dispatchEvent(new Event('repo-intel:git-history'))}
      />
    ) : (
      <section className="panel">
        <div className="panel-head"><h3>Loading</h3></div>
        <div className="empty" style={{ padding: '20px 0' }}>Analyzing repository…</div>
      </section>
    )
  ) : tab === 'chat' ? (
    <SourceViewer
      sources={chat.sources}
      latency={chat.latency}
      isStreaming={chat.isStreaming}
      confidence={chat.confidence}
    />
  ) : (
    <SourceDetails source={source} />
  );

function SourceDetails({ source }) {
  const repoUrl = sourceRepoUrl(source);
  const urlLabel = repoUrl ? repoUrl.replace(/^https?:\/\/(www\.)?/, '') : '';
  return (
    <section className="panel source-details-panel">
      <div className="panel-head"><h3>Source Details</h3></div>
      <dl className="source-detail-grid">
        <div className="source-detail-tile">
          <dt>Type</dt>
          <dd><span className={`source-type-pill is-${source.type}`}>{formatTypeLabel(source.type)}</span></dd>
        </div>
        <div className="source-detail-tile">
          <dt>Chunks</dt>
          <dd className="source-detail-count">{source.chunks}</dd>
        </div>
        <div className="source-detail-tile source-detail-tile-span">
          <dt>URL</dt>
          <dd className="source-detail-url">
            {repoUrl ? (
              <a className="source-detail-link" href={repoUrl} target="_blank" rel="noreferrer" title={repoUrl}>
                <span className="source-detail-link-text">{urlLabel}</span>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                  <polyline points="15 3 21 3 21 9" />
                  <line x1="10" y1="14" x2="21" y2="3" />
                </svg>
              </a>
            ) : (
              <span>—</span>
            )}
          </dd>
        </div>
      </dl>
    </section>
  );
}

  const mainContent = (() => {
    switch (tab) {
      case 'chat':
        return (
          <div className="main-card explore-chat-card">
            <ChatBox
              messages={chat.messages}
              input={chat.input}
              onInputChange={chat.setInput}
              onSend={chat.sendMessage}
              isStreaming={chat.isStreaming}
              error={chat.error}
              onSuggestion={chat.sendMessage}
              onRetry={chat.retryLast}
              uploadHint={chat.showUploadHint}
              onNewChat={chat.resetChat}
            />
          </div>
        );
      case 'intelligence':
        if (repository.loading && !repository.analysis) {
          return <RepositoryAnalysisLoading embedded name={source.title} progress={repository.status?.progress || 0} status={repository.status?.status || 'queued'} />;
        }
        if (repository.error && !repository.analysis) {
          return (
            <div className="intel-analyzing-card empty-intel">
              <p className="intel-error">{repository.error}</p>
              <button className="primary" onClick={() => navigate('/')}>Back to workspace</button>
            </div>
          );
        }
        return (
          <RepositoryIntelligenceView
            analysis={repository.analysis}
            analysisId={repository.id}
            reanalyze={repository.reanalyze}
            loading={repository.loading}
            error={repository.error}
          />
        );
      case 'mindmap':
        return (
          <div className="mindmap-shell" ref={mindmapRef}>
            <button
              className={`icon-button mindmap-fullscreen-btn${isMindmapFullscreen ? ' is-active' : ''}`}
              onClick={toggleMindmapFullscreen}
              title={isMindmapFullscreen ? 'Exit fullscreen (Esc)' : 'Enter fullscreen'}
            >
              {isMindmapFullscreen ? (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 8h4V4M20 8h-4V4M4 16h4v4M20 16h-4v4" />
                </svg>
              ) : (
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3" />
                </svg>
              )}
            </button>
            <MindMapCanvas sourceId={sourceId} isFullscreen={isMindmapFullscreen} />
          </div>
        );
      case 'overview':
      default:
        return (
          <OverviewTab source={source} onOpenChat={() => setTab('chat')} />
        );
    }
  })();

  return (
    <AppShell
      sidebar={(
        <Sidebar
          sources={sources}
          loading={sourcesLoading}
          activeSourceId={sourceId}
          onAddSource={() => navigate('/?add=1')}
          onSelectSource={(id) => navigate(`/sources/${encodeURIComponent(id)}`)}
          onDeleteSource={handleDelete}
          onClearKB={handleClearKB}
        />
      )}
      main={(
        <div className="explore-main">
          <SourceHeader
            source={source}
            onBack={() => navigate('/')}
            actions={isGithub ? (
              <button className="sync-btn" onClick={() => repository.reanalyze()}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></svg>
                Sync
              </button>
            ) : null}
          />
          <CapabilityTabs tabs={availableTabs} active={tab} onChange={setTab} />
          <div className="explore-content">
            <motion.div
              key={tab}
              className="tab-pane"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.28, ease: 'easeOut' }}
            >
              {mainContent}
            </motion.div>
          </div>
        </div>
      )}
      right={rightPanel}
      layoutClass="explore-layout"
      rightClass={tab === 'chat' ? 'shell-right-evidence' : ''}
    />
  );
}

function CapabilityTabs({ tabs, active, onChange }) {
  const labels = {
    overview: 'Overview',
    chat: 'Chat',
    intelligence: 'Repository Intelligence',
    mindmap: 'Mind Map',
  };
  return (
    <nav className="capability-tabs">
      <div className="capability-tabs-track">
        {tabs.map((id) => (
          <button
            key={id}
            className={`capability-tab${active === id ? ' active' : ''}`}
            onClick={() => onChange(id)}
          >
            {labels[id] || id}
          </button>
        ))}
      </div>
    </nav>
  );
}

function OverviewTab({ source, onOpenChat }) {
  return (
    <div className="overview-grid">
      <section className="panel overview-panel">
        <div className="panel-head">
          <h3>About this source</h3>
        </div>
        <div className="overview-visual">
          <div className={`source-item-icon is-${source.type}`}>
            <SourceGlyph type={source.type} size={20} />
          </div>
          <div>
            <div className="overview-title">{source.title}</div>
            <div className="overview-meta">{formatSourceMeta(source)}</div>
          </div>
        </div>
        <p className="overview-blurb">
          This {source.type} source has been indexed into your ContextForge knowledge
          base. Ask questions about it, or explore it visually with a mind map.
          {source.type === 'github' ? ' Use Repository Intelligence to understand its architecture.' : ''}
        </p>
      </section>
      <section className="panel overview-panel">
        <div className="panel-head"><h3>Explore</h3></div>
        <div className="overview-actions">
          <button className="primary" onClick={onOpenChat}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
            Ask about this source
          </button>
        </div>
      </section>
    </div>
  );
}
