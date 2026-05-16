import { useCallback, useState } from 'react';

import ChatBox from '../components/ChatBox';
import SourceViewer from '../components/SourceViewer';
import { ingestFile, ingestGithub, ingestSource } from '../services/api';
import { useChat } from '../hooks/useChat';

function SourceIcon({ type }) {
  const icon = (() => {
    switch (type) {
      case 'pdf':
      case 'docx':
        return (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <rect x="2" y="2" width="20" height="20" rx="4" fill="#EF4444" />
            <rect x="2" y="2" width="14" height="7" rx="4" fill="#DC2626" />
            <text x="12" y="16" textAnchor="middle" fill="white" fontSize="7.5" fontWeight="bold" fontFamily="Arial,sans-serif">PDF</text>
          </svg>
        );
      case 'web':
        return (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="2" y1="12" x2="22" y2="12" />
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
          </svg>
        );
      case 'github':
        return (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
          </svg>
        );
      default:
        return (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
        );
    }
  })();

  const className = (() => {
    switch (type) {
      case 'pdf': return 'source-item-icon is-pdf';
      case 'web': return 'source-item-icon is-web';
      case 'github': return 'source-item-icon is-github';
      default: return 'source-item-icon';
    }
  })();

  return <div className={className}>{icon}</div>;
}

function formatFileSize(bytes) {
  if (!bytes) return '0 KB';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function formatSourceMeta(source) {
  switch (source.type) {
    case 'pdf':
    case 'docx':
      return `PDF • ${formatFileSize(source.size)}`;
    case 'web':
      return `Web • ${source.date ? new Date(source.date).toLocaleDateString('en-GB') : ''}`;
    case 'github':
      return `GitHub Repo • ${source.chunks || 0} files`;
    default:
      return `${source.type.toUpperCase()} • ${source.chunks || 0} items`;
  }
}

const STATUS_META = {
  indexed: { label: 'Indexed', dot: 'status-dot is-indexed' },
  processing: { label: 'Processing', dot: 'status-dot is-processing' },
  failed: { label: 'Failed', dot: 'status-dot is-failed' },
};

const TYPE_LABEL = {
  pdf: 'PDF',
  docx: 'DOCX',
  web: 'WEB',
  github: 'GIT',
  text: 'TXT',
};

export default function Home() {
  const [sources, setSources] = useState([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isAddingRepo, setIsAddingRepo] = useState(false);
  const [isAddingUrl, setIsAddingUrl] = useState(false);
  const [isAddingText, setIsAddingText] = useState(false);
  const [notifications, setNotifications] = useState([]);

  const {
    input,
    setInput,
    messages,
    sendMessage,
    isStreaming,
    error,
    sources: querySources,
    latency,
    confidence,
    suggestions,
    retryLast,
    showUploadHint,
  } = useChat();

  const pushNotification = useCallback((type, text) => {
    const id = `${type}-${Date.now()}`;
    setNotifications((prev) => [...prev, { id, type, text }]);
    setTimeout(() => {
      setNotifications((prev) => prev.filter((item) => item.id !== id));
    }, 4000);
  }, []);

  const addSource = useCallback((payload) => {
    setSources((prev) => [payload, ...prev]);
  }, []);

  const updateSource = useCallback((id, patch) => {
    setSources((prev) => prev.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }, []);

  const removeSource = useCallback((id) => {
    setSources((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const handleFileUpload = useCallback(
    async (file) => {
      const sourceType = file.name.toLowerCase().endsWith('.pdf') ? 'pdf' : 'docx';
      const tempId = `local-${Date.now()}`;
      addSource({
        id: tempId,
        type: sourceType,
        title: file.name,
        status: 'processing',
        chunks: 0,
        size: file.size,
      });
      setIsUploading(true);
      try {
        const response = await ingestFile({ source_type: sourceType, file });
        updateSource(tempId, {
          id: response.source_id,
          status: 'indexed',
          chunks: response.chunks_indexed,
          meta: response.message,
        });
        pushNotification('success', response.message);
      } catch (uploadError) {
        updateSource(tempId, { status: 'failed' });
        pushNotification('error', uploadError.message || 'Upload failed');
      } finally {
        setIsUploading(false);
      }
    },
    [addSource, pushNotification, updateSource],
  );

  const handleUrlIngest = useCallback(
    async (url) => {
      const tempId = `web-${Date.now()}`;
      addSource({
        id: tempId,
        type: 'web',
        title: url.replace(/^https?:\/\//, ''),
        status: 'processing',
        chunks: 0,
        date: new Date().toISOString(),
      });
      setIsAddingUrl(true);
      try {
        const response = await ingestSource({ source_type: 'web', source: url });
        updateSource(tempId, {
          id: response.source_id,
          status: 'indexed',
          chunks: response.chunks_indexed,
          meta: response.message,
        });
        pushNotification('success', response.message);
      } catch (ingestError) {
        updateSource(tempId, { status: 'failed' });
        pushNotification('error', ingestError.message || 'Ingest failed');
      } finally {
        setIsAddingUrl(false);
      }
    },
    [addSource, pushNotification, updateSource],
  );

  const handleRepoIngest = useCallback(
    async (url) => {
      const tempId = `repo-${Date.now()}`;
      addSource({
        id: tempId,
        type: 'github',
        title: url.replace('https://github.com/', ''),
        status: 'processing',
        chunks: 0,
      });
      setIsAddingRepo(true);
      try {
        const response = await ingestGithub({ repo_url: url });
        updateSource(tempId, {
          id: response.source_id,
          status: 'indexed',
          chunks: response.chunks_indexed,
          meta: response.message,
        });
        pushNotification('success', response.message);
      } catch (repoError) {
        updateSource(tempId, { status: 'failed' });
        pushNotification('error', repoError.message || 'GitHub ingest failed');
      } finally {
        setIsAddingRepo(false);
      }
    },
    [addSource, pushNotification, updateSource],
  );

  const handleTextIngest = useCallback(
    async (text) => {
      const trimmed = text.trim();
      if (!trimmed) {
        return;
      }
      const tempId = `text-${Date.now()}`;
      addSource({
        id: tempId,
        type: 'text',
        title: 'Notes',
        status: 'processing',
        chunks: 0,
      });
      setIsAddingText(true);
      try {
        const response = await ingestSource({ source_type: 'text', source: trimmed });
        updateSource(tempId, {
          id: response.source_id,
          status: 'indexed',
          chunks: response.chunks_indexed,
          meta: response.message,
        });
        pushNotification('success', response.message);
      } catch (textError) {
        updateSource(tempId, { status: 'failed' });
        pushNotification('error', textError.message || 'Text ingest failed');
      } finally {
        setIsAddingText(false);
      }
    },
    [addSource, pushNotification, updateSource],
  );

  const handleFileDrop = useCallback(
    (event) => {
      event.preventDefault();
      const [file] = event.dataTransfer.files;
      if (file) {
        handleFileUpload(file);
      }
    },
    [handleFileUpload],
  );

  const handleFilePicker = useCallback(
    (event) => {
      const [file] = event.target.files;
      if (file) {
        handleFileUpload(file);
      }
      event.target.value = '';
    },
    [handleFileUpload],
  );

  const isProcessing = isUploading || isAddingRepo || isAddingUrl || isAddingText;

  const indexedCount = sources.filter((s) => s.status === 'indexed').length;
  const processingCount = sources.filter((s) => s.status === 'processing').length;
  const pdfCount = sources.filter((s) => s.type === 'pdf').length;
  const webCount = sources.filter((s) => s.type === 'web').length;
  const githubCount = sources.filter((s) => s.type === 'github').length;

  return (
    <main className="app-shell">
      <div className="app-layout">
        <aside className="sidebar-shell">
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

          <button className="add-knowledge-btn" onClick={() => setIsModalOpen(true)}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
            <span>Add Source</span>
          </button>

          <section className="kb-section">
            <div className="section-title">Knowledge Base</div>
            <div className="kb-rows">
              <div className="kb-row active">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="4" rx="1" /><rect x="5" y="10" width="14" height="4" rx="1" /><rect x="7" y="17" width="10" height="4" rx="1" /></svg>
                <span>All Documents</span>
                <span className="kb-count">{sources.length}</span>
              </div>
              <div className="kb-row">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /></svg>
                <span>PDFs</span>
                <span className="kb-count">{pdfCount}</span>
              </div>
              <div className="kb-row">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><line x1="2" y1="12" x2="22" y2="12" /><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" /></svg>
                <span>Web Pages</span>
                <span className="kb-count">{webCount}</span>
              </div>
              <div className="kb-row">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" /></svg>
                <span>GitHub Repos</span>
                <span className="kb-count">{githubCount}</span>
              </div>
            </div>
          </section>

          <section className="sources-section">
            <div className="section-title">
              <span>My Sources</span>
            </div>
            <div className="source-list">
              {sources.length === 0 ? (
                <div className="empty-source">No sources added yet.</div>
              ) : (
                    sources.map((source) => {
                  const status = STATUS_META[source.status] || STATUS_META.processing;
                  return (
                    <div className="source-item-compact" key={source.id}>
                      <SourceIcon type={source.type} />
                      <div className="source-item-body">
                        <div className="source-item-title">{source.title}</div>
                        <div className="source-item-meta">{formatSourceMeta(source)}</div>
                      </div>
                      <div className="source-item-status">
                        <span className={status.dot} title={status.label} />
                      </div>
                      <button
                        className="source-item-delete"
                        title="Delete"
                        onClick={() => removeSource(source.id)}
                      >
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                          <path d="M18 6L6 18M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </section>

          <div className="sidebar-spacer" />

          <div className="status-card">
            <div className="status-card-header">Processing Status</div>
            <div className="status-card-body">
              <div className="status-card-row">
                <span className="status-dot is-indexed" />
                <span>{indexedCount} sources indexed</span>
              </div>
              <div className="status-card-row">
                <span className={`status-dot ${processingCount > 0 ? 'is-processing' : 'is-indexed'}`} />
                <span>{processingCount > 0 ? `${processingCount} processing` : 'All idle'}</span>
              </div>
            </div>
          </div>
        </aside>

        <section className="main-shell">
          <div className="main-card">
            <ChatBox
              messages={messages}
              input={input}
              onInputChange={setInput}
              onSend={sendMessage}
              isStreaming={isStreaming}
              error={error}
              onSuggestion={sendMessage}
              onRetry={retryLast}
              uploadHint={showUploadHint}
            />
          </div>
        </section>

        <aside className="evidence-shell">
          <SourceViewer sources={querySources} latency={latency} isStreaming={isStreaming} confidence={confidence} />
        </aside>
      </div>

      {isModalOpen ? (
        <div className="modal-backdrop" onClick={() => setIsModalOpen(false)}>
          <div className="modal-card" onClick={(event) => event.stopPropagation()}>
            <div className="modal-head">
              <div>
                <h2>Expand your knowledge base</h2>
                <p>Ingest sources in multiple formats and keep your RAG workspace grounded.</p>
              </div>
              <button className="icon-button" onClick={() => setIsModalOpen(false)}>
                x
              </button>
            </div>

            <div className="modal-grid">
              <div className="option-card" onDragOver={(event) => event.preventDefault()} onDrop={handleFileDrop}>
                  <div className="option-head">
                    <div className="option-icon">
                      <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                        <rect x="2" y="2" width="20" height="20" rx="4" fill="#EF4444" />
                        <rect x="2" y="2" width="13" height="7" rx="4" fill="#DC2626" />
                        <text x="12" y="16" textAnchor="middle" fill="white" fontSize="7" fontWeight="bold" fontFamily="Arial,sans-serif">PDF</text>
                      </svg>
                    </div>
                  <div>
                    <h3>Upload PDF/DOCX</h3>
                    <p>Drag & drop or browse files.</p>
                  </div>
                  {isUploading ? <span className="option-status">Uploading...</span> : null}
                </div>
                <label className="drop-zone">
                  <input
                    type="file"
                    accept="application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    onChange={handleFilePicker}
                    hidden
                  />
                  <span>Drop PDF or DOCX here</span>
                  <small>Max 50MB</small>
                </label>
                {isUploading ? (
                  <div className="progress-bar">
                    <div className="progress-fill" />
                  </div>
                ) : null}
              </div>

              <div className="option-card">
                  <div className="option-head">
                    <div className="option-icon">
                      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="10" />
                        <line x1="2" y1="12" x2="22" y2="12" />
                        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                      </svg>
                    </div>
                  <div>
                    <h3>Paste Website URL</h3>
                    <p>Ingest a public webpage.</p>
                  </div>
                </div>
                <form
                  className="inline-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const url = event.currentTarget.elements.url?.value || '';
                    if (url.trim()) {
                      handleUrlIngest(url.trim());
                      event.currentTarget.reset();
                    }
                  }}
                >
                  <input name="url" placeholder="https://example.com" className="text-input" />
                  <button className="primary" type="submit" disabled={isAddingUrl}>
                    {isAddingUrl ? 'Ingesting...' : 'Ingest Website'}
                  </button>
                </form>
              </div>

              <div className="option-card">
                  <div className="option-head">
                    <div className="option-icon">
                      <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
                      </svg>
                    </div>
                  <div>
                    <h3>GitHub Repository</h3>
                    <p>Index a public repo.</p>
                  </div>
                </div>
                <form
                  className="inline-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const url = event.currentTarget.elements.repo?.value || '';
                    if (url.trim()) {
                      handleRepoIngest(url.trim());
                      event.currentTarget.reset();
                    }
                  }}
                >
                  <input name="repo" placeholder="https://github.com/org/repo" className="text-input" />
                  <button className="primary" type="submit" disabled={isAddingRepo}>
                    {isAddingRepo ? 'Indexing...' : 'Index Repository'}
                  </button>
                </form>
              </div>

              <div className="option-card">
                  <div className="option-head">
                    <div className="option-icon">
                      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <polyline points="14 2 14 8 20 8" />
                        <line x1="16" y1="13" x2="8" y2="13" />
                        <line x1="16" y1="17" x2="8" y2="17" />
                        <line x1="10" y1="9" x2="8" y2="9" />
                      </svg>
                    </div>
                  <div>
                    <h3>Plain Text / Notes</h3>
                    <p>Store raw notes quickly.</p>
                  </div>
                </div>
                <form
                  className="stack-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const text = event.currentTarget.elements.notes?.value || '';
                    handleTextIngest(text);
                    event.currentTarget.reset();
                  }}
                >
                  <textarea
                    name="notes"
                    rows={3}
                    placeholder="Paste knowledge snippets, meeting notes, or specs..."
                    className="text-input"
                  />
                  <button className="primary" type="submit" disabled={isAddingText}>
                    {isAddingText ? 'Saving...' : 'Save to Knowledge Base'}
                  </button>
                </form>
              </div>
            </div>

            {isProcessing ? (
              <div className="processing-banner">Ingestion running — new chunks will appear in the source list.</div>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="toast-stack">
        {notifications.map((item) => (
          <div key={item.id} className={`toast ${item.type}`}>
            {item.text}
          </div>
        ))}
      </div>
    </main>
  );
}
