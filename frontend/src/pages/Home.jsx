import { useCallback, useMemo, useState } from 'react';

import ChatBox from '../components/ChatBox';
import SourceViewer from '../components/SourceViewer';
import { ingestFile, ingestGithub, ingestSource } from '../services/api';
import { useChat } from '../hooks/useChat';

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
    suggestions,
    retryLast,
    showUploadHint,
  } = useChat();

  const recentChats = useMemo(
    () => ['Transformer Basics', 'Reranking Strategy', 'Vector DB Tuning', 'Eval Checklist'],
    [],
  );
  const collections = useMemo(() => ['LLM Benchmarks', 'Docs Sync', 'Team Notes'], []);

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

  return (
    <main className="app-shell">
      <div className="app-layout">
        <aside className="sidebar-shell">
          <div className="brand">
            <div className="brand-mark">C</div>
            <div className="brand-text">
              <span>ContextForge</span>
              <small>Grounded AI Workspace</small>
            </div>
          </div>

          <button className="add-knowledge-btn" onClick={() => setIsModalOpen(true)}>
            <span>+ Add Knowledge</span>
            <span className="chevron">&gt;</span>
          </button>

          <section className="data-sources">
            <div className="section-title">
              <span>Data Sources</span>
              <span className="count">{sources.length}</span>
            </div>
            <div className="source-cards">
              {sources.length === 0 ? (
                <div className="empty-card">No knowledge sources added yet.</div>
              ) : (
                sources.map((source) => {
                  const status = STATUS_META[source.status] || STATUS_META.processing;
                  return (
                    <article className="source-card" key={source.id}>
                      <div className="source-card-head">
                        <div className="source-icon">{TYPE_LABEL[source.type] || 'DOC'}</div>
                        <div>
                          <div className="source-title">{source.title}</div>
                          <div className="source-meta">
                            {source.type.toUpperCase()} • {source.chunks || 0} chunks
                          </div>
                        </div>
                        <div className="source-actions">
                          <button className="icon-button" title="Expand">
                            &gt;
                          </button>
                          <button
                            className="icon-button danger"
                            title="Delete"
                            onClick={() => removeSource(source.id)}
                          >
                            x
                          </button>
                        </div>
                      </div>
                      <div className="source-card-foot">
                        <div className="status-line">
                          <span className={status.dot} />
                          <span>{status.label}</span>
                        </div>
                        <div className="source-detail">{source.meta || 'Ready for retrieval'}</div>
                      </div>
                    </article>
                  );
                })
              )}
            </div>
          </section>

          <section className="sidebar-group">
            <div className="section-title">Recent Chats</div>
            <div className="link-list">
              {recentChats.map((chat) => (
                <button className="link-item" key={chat}>
                  <span>{chat}</span>
                  <span className="chevron">&gt;</span>
                </button>
              ))}
            </div>
          </section>

          <section className="sidebar-group">
            <div className="section-title">Saved Collections</div>
            <div className="link-list">
              {collections.map((item) => (
                <div className="link-item static" key={item}>
                  {item}
                </div>
              ))}
            </div>
          </section>

          <section className="sidebar-group">
            <div className="section-title">Settings</div>
            <button className="link-item">
              <span>Workspace preferences</span>
              <span className="chevron">&gt;</span>
            </button>
          </section>
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
          <SourceViewer sources={querySources} latency={latency} />
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
                  <div className="option-icon">PDF</div>
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
                  <div className="option-icon">URL</div>
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
                  <div className="option-icon">GIT</div>
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
                  <div className="option-icon">TXT</div>
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
