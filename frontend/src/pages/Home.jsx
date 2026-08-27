import { useCallback, useState, useRef, useEffect, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import AppShell from '../components/layout/AppShell'
import Sidebar from '../components/layout/Sidebar'
import ChatBox from '../components/ChatBox'
import SourceViewer from '../components/SourceViewer'
import {
  ingestFile,
  ingestGithub,
  ingestSource,
  deleteSource,
  clearKnowledgeBase,
} from '../services/api'
import { sourceRepoUrl } from '../lib/sources'
import { useChat } from '../hooks/useChat'
import { useSources } from '../hooks/useSources'

export default function Home() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { sources, loading, addSource, updateSource, removeSource, replaceAll } = useSources()
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [isAddingRepo, setIsAddingRepo] = useState(false)
  const [isAddingUrl, setIsAddingUrl] = useState(false)
  const [isAddingText, setIsAddingText] = useState(false)
  const [isAddingYoutube, setIsAddingYoutube] = useState(false)
  const [notifications, setNotifications] = useState([])
  const [confirmState, setConfirmState] = useState({ open: false, message: '', onConfirm: null })
  const confirmResolveRef = useRef(null)

  // Allow the shared sidebar's "Add Source" button on any page to open the
  // ingest modal by returning to the workspace with ?add=1.
  useEffect(() => {
    if (searchParams.get('add')) {
      setIsModalOpen(true)
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, setSearchParams])

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
    retryLast,
    showUploadHint,
    resetChat,
  } = useChat()

  // The dominant source of the current query determines whether Repository
  // Intelligence can be launched from the main chat interface.
  const { dominantSourceId, dominantRepoUrl } = useMemo(() => {
    const counts = {}
    for (const item of querySources) {
      if (item.source_id) counts[item.source_id] = (counts[item.source_id] || 0) + 1
    }
    let best = null
    let bestCount = 0
    for (const [id, count] of Object.entries(counts)) {
      if (count > bestCount) {
        best = id
        bestCount = count
      }
    }
    const dominant = sources.find((s) => s.id === best) || null
    return {
      dominantSourceId: best,
      dominantRepoUrl: dominant?.type === 'github' ? sourceRepoUrl(dominant) : undefined,
    }
  }, [querySources, sources])

  const pushNotification = useCallback((type, text) => {
    const id = `${type}-${Date.now()}`
    setNotifications((prev) => [...prev, { id, type, text }])
    setTimeout(() => {
      setNotifications((prev) => prev.filter((item) => item.id !== id))
    }, 4000)
  }, [])

  const showConfirm = useCallback((message) => {
    return new Promise((resolve) => {
      confirmResolveRef.current = resolve
      setConfirmState({ open: true, message, onConfirm: resolve })
    })
  }, [])

  const handleConfirm = useCallback((result) => {
    setConfirmState({ open: false, message: '', onConfirm: null })
    if (confirmResolveRef.current) {
      confirmResolveRef.current(result)
      confirmResolveRef.current = null
    }
  }, [])

  const handleFileUpload = useCallback(
    async (file) => {
      const sourceType = file.name.toLowerCase().endsWith('.pdf') ? 'pdf' : 'docx'
      const tempId = `local-${Date.now()}`
      addSource({
        id: tempId,
        type: sourceType,
        title: file.name,
        status: 'processing',
        chunks: 0,
        size: file.size,
      })
      setIsUploading(true)
      try {
        const response = await ingestFile({ source_type: sourceType, file })
        updateSource(tempId, {
          id: response.source_id,
          status: 'indexed',
          chunks: response.chunks_indexed,
          meta: response.message,
        })
        pushNotification('success', response.message)
      } catch (uploadError) {
        updateSource(tempId, { status: 'failed' })
        pushNotification('error', uploadError.message || 'Upload failed')
      } finally {
        setIsUploading(false)
      }
    },
    [addSource, pushNotification, updateSource],
  )

  const handleUrlIngest = useCallback(
    async (url) => {
      const tempId = `web-${Date.now()}`
      addSource({
        id: tempId,
        type: 'web',
        title: url.replace(/^https?:\/\//, ''),
        status: 'processing',
        chunks: 0,
        date: new Date().toISOString(),
      })
      setIsAddingUrl(true)
      try {
        const response = await ingestSource({ source_type: 'web', source: url })
        updateSource(tempId, {
          id: response.source_id,
          status: 'indexed',
          chunks: response.chunks_indexed,
          meta: response.message,
        })
        pushNotification('success', response.message)
      } catch (ingestError) {
        updateSource(tempId, { status: 'failed' })
        pushNotification('error', ingestError.message || 'Ingest failed')
      } finally {
        setIsAddingUrl(false)
      }
    },
    [addSource, pushNotification, updateSource],
  )

  const handleRepoIngest = useCallback(
    async (url) => {
      const tempId = `repo-${Date.now()}`
      addSource({
        id: tempId,
        type: 'github',
        title: url.replace('https://github.com/', ''),
        status: 'processing',
        chunks: 0,
      })
      setIsAddingRepo(true)
      try {
        const response = await ingestGithub({ repo_url: url })
        updateSource(tempId, {
          id: response.source_id,
          status: 'indexed',
          chunks: response.chunks_indexed,
          meta: response.message,
        })
        pushNotification('success', response.message)
        setIsModalOpen(false)
        navigate(`/sources/${encodeURIComponent(response.source_id)}?tab=intelligence`)
      } catch (repoError) {
        updateSource(tempId, { status: 'failed' })
        pushNotification('error', repoError.message || 'GitHub ingest failed')
      } finally {
        setIsAddingRepo(false)
      }
    },
    [addSource, pushNotification, updateSource, navigate],
  )

  const handleTextIngest = useCallback(
    async (text) => {
      const trimmed = text.trim()
      if (!trimmed) return
      const tempId = `text-${Date.now()}`
      addSource({
        id: tempId,
        type: 'text',
        title: 'Notes',
        status: 'processing',
        chunks: 0,
      })
      setIsAddingText(true)
      try {
        const response = await ingestSource({ source_type: 'text', source: trimmed })
        updateSource(tempId, {
          id: response.source_id,
          status: 'indexed',
          chunks: response.chunks_indexed,
          meta: response.message,
        })
        pushNotification('success', response.message)
      } catch (textError) {
        updateSource(tempId, { status: 'failed' })
        pushNotification('error', textError.message || 'Text ingest failed')
      } finally {
        setIsAddingText(false)
      }
    },
    [addSource, pushNotification, updateSource],
  )

  const handleYoutubeIngest = useCallback(
    async (url) => {
      const tempId = `youtube-${Date.now()}`
      addSource({
        id: tempId,
        type: 'youtube',
        title: url.replace(/^https?:\/\//, ''),
        status: 'processing',
        chunks: 0,
      })
      setIsAddingYoutube(true)
      try {
        const response = await ingestSource({ source_type: 'youtube', source: url })
        updateSource(tempId, {
          id: response.source_id,
          status: 'indexed',
          chunks: response.chunks_indexed,
          meta: response.message,
        })
        pushNotification('success', response.message)
      } catch (ingestError) {
        updateSource(tempId, { status: 'failed' })
        pushNotification('error', ingestError.message || 'YouTube ingest failed')
      } finally {
        setIsAddingYoutube(false)
      }
    },
    [addSource, pushNotification, updateSource],
  )

  const handleFileDrop = useCallback(
    (event) => {
      event.preventDefault()
      const [file] = event.dataTransfer.files
      if (file) handleFileUpload(file)
    },
    [handleFileUpload],
  )

  const handleFilePicker = useCallback(
    (event) => {
      const [file] = event.target.files
      if (file) handleFileUpload(file)
      event.target.value = ''
    },
    [handleFileUpload],
  )

  const isProcessing = isUploading || isAddingRepo || isAddingUrl || isAddingText || isAddingYoutube

  const handleClearKB = useCallback(async () => {
    const confirmed = await showConfirm(
      'Are you sure you want to clear the entire knowledge base? This cannot be undone.',
    )
    if (!confirmed) return
    try {
      await clearKnowledgeBase()
      replaceAll([])
      resetChat()
      pushNotification('success', 'Knowledge base cleared successfully.')
    } catch (err) {
      pushNotification('error', err.message || 'Failed to clear knowledge base.')
    }
  }, [showConfirm, pushNotification, resetChat, replaceAll])

  const handleDeleteSource = useCallback(
    async (id) => {
      try {
        await deleteSource(id)
      } catch {
        // Best effort — still remove from UI
      }
      removeSource(id)
    },
    [removeSource],
  )

  const handleSelectSource = useCallback(
    (id) => {
      navigate(`/sources/${encodeURIComponent(id)}`)
    },
    [navigate],
  )

  const main = (
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
        onNewChat={resetChat}
      />
    </div>
  )

  const right = (
    <SourceViewer
      sources={querySources}
      latency={latency}
      isStreaming={isStreaming}
      confidence={confidence}
      showQuickActions
      repoUrl={dominantRepoUrl}
      onOpenIntel={() => {
        if (dominantSourceId) {
          navigate(`/sources/${encodeURIComponent(dominantSourceId)}?tab=intelligence`)
        }
      }}
    />
  )

  return (
    <>
      <AppShell
        sidebar={
          <Sidebar
            sources={sources}
            loading={loading}
            onAddSource={() => setIsModalOpen(true)}
            onSelectSource={handleSelectSource}
            onDeleteSource={handleDeleteSource}
            onClearKB={handleClearKB}
          />
        }
        main={main}
        right={right}
        rightClass="shell-right-evidence"
      />

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
              <div
                className="option-card"
                onDragOver={(event) => event.preventDefault()}
                onDrop={handleFileDrop}
              >
                <div className="option-head">
                  <div className="option-icon">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                      <rect x="2" y="2" width="20" height="20" rx="4" fill="#EF4444" />
                      <rect x="2" y="2" width="13" height="7" rx="4" fill="#DC2626" />
                      <text
                        x="12"
                        y="16"
                        textAnchor="middle"
                        fill="white"
                        fontSize="7"
                        fontWeight="bold"
                        fontFamily="Arial,sans-serif"
                      >
                        PDF
                      </text>
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
                    <svg
                      width="22"
                      height="22"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
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
                    event.preventDefault()
                    const url = event.currentTarget.elements.url?.value || ''
                    if (url.trim()) {
                      handleUrlIngest(url.trim())
                      event.currentTarget.reset()
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
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                      <rect x="2" y="4" width="20" height="16" rx="4" fill="#FF0000" />
                      <path d="M10 9l6 3-6 3z" fill="#FFFFFF" />
                    </svg>
                  </div>
                  <div>
                    <h3>YouTube Video</h3>
                    <p>Paste a YouTube video URL to index it.</p>
                  </div>
                </div>
                <form
                  className="inline-form"
                  onSubmit={(event) => {
                    event.preventDefault()
                    const url = event.currentTarget.elements.url?.value || ''
                    if (url.trim()) {
                      handleYoutubeIngest(url.trim())
                      event.currentTarget.reset()
                    }
                  }}
                >
                  <input
                    name="url"
                    placeholder="https://www.youtube.com/watch?v=..."
                    className="text-input"
                  />
                  <button className="primary" type="submit" disabled={isAddingYoutube}>
                    {isAddingYoutube ? 'Ingesting...' : 'Ingest Video'}
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
                    event.preventDefault()
                    const url = event.currentTarget.elements.repo?.value || ''
                    if (url.trim()) {
                      handleRepoIngest(url.trim())
                      event.currentTarget.reset()
                    }
                  }}
                >
                  <input
                    name="repo"
                    placeholder="https://github.com/org/repo"
                    className="text-input"
                  />
                  <button className="primary" type="submit" disabled={isAddingRepo}>
                    {isAddingRepo ? 'Indexing...' : 'Index Repository'}
                  </button>
                </form>
              </div>

              <div className="option-card">
                <div className="option-head">
                  <div className="option-icon">
                    <svg
                      width="22"
                      height="22"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
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
                    event.preventDefault()
                    const text = event.currentTarget.elements.notes?.value || ''
                    handleTextIngest(text)
                    event.currentTarget.reset()
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
              <div className="processing-banner">
                Ingestion running — new chunks will appear in the source list.
              </div>
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

      {confirmState.open && (
        <div className="confirm-backdrop" onClick={() => handleConfirm(false)}>
          <div className="confirm-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Confirm</h3>
            <p>{confirmState.message}</p>
            <div className="confirm-actions">
              <button className="confirm-cancel" onClick={() => handleConfirm(false)}>
                Cancel
              </button>
              <button className="confirm-danger" onClick={() => handleConfirm(true)}>
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
