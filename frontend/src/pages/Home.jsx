import { useCallback, useState, useRef, useEffect, useMemo } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import AppShell from '../components/layout/AppShell'
import Sidebar from '../components/layout/Sidebar'
import ChatBox from '../components/ChatBox'
import SourceViewer from '../components/SourceViewer'
import MindMapPanel from '../components/MindMapPanel'
import RepoStudio, { STUDIO_TOOLS, StudioView } from '../components/RepoStudio'
import {
  ingestFile,
  ingestGithub,
  ingestSource,
  deleteSource,
  clearKnowledgeBase,
  getProject,
  touchProject,
  attachSourceToProject,
} from '../services/api'
import { ingestScopeFor, sidebarTypesFor, sourceCategoryLabel } from '../lib/projects'
import { useChat } from '../hooks/useChat'
import { useSourceSelection } from '../hooks/useSourceSelection'
import { useSources } from '../hooks/useSources'

export default function Home() {
  const { projectId } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const { sources, loading, addSource, updateSource, renameSource, removeSource, replaceAll } =
    useSources()
  const [activeProject, setActiveProject] = useState(null)
  const [projectMissing, setProjectMissing] = useState(false)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [isAddingRepo, setIsAddingRepo] = useState(false)
  const [isAddingUrl, setIsAddingUrl] = useState(false)
  const [isAddingText, setIsAddingText] = useState(false)
  const [isAddingYoutube, setIsAddingYoutube] = useState(false)
  const [notifications, setNotifications] = useState([])
  const [confirmState, setConfirmState] = useState({ open: false, message: '', onConfirm: null })
  const [renameTarget, setRenameTarget] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const [renameSaving, setRenameSaving] = useState(false)
  const confirmResolveRef = useRef(null)

  // Project scope: /projects/:projectId renders this same workspace filtered
  // to the project's membership.  /workspace keeps the legacy global view.
  useEffect(() => {
    let cancelled = false
    if (!projectId) {
      setActiveProject(null)
      setProjectMissing(false)
      return undefined
    }
    setProjectMissing(false)
    getProject(projectId)
      .then((project) => {
        if (cancelled) return
        setActiveProject(project)
        touchProject(projectId).catch(() => {})
      })
      .catch(() => {
        if (!cancelled) setProjectMissing(true)
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  const visibleSources = useMemo(() => {
    if (!projectId) return sources
    // While the project membership is still loading, show nothing rather
    // than flashing the full global knowledge base inside a project view.
    if (!activeProject) return projectMissing ? sources : []
    const allowed = new Set(activeProject.source_ids || [])
    return sources.filter((s) => allowed.has(s.id))
  }, [sources, projectId, activeProject, projectMissing])

  // The project's chosen source family scopes which ingest options this
  // workspace offers.  Legacy projects ("all") keep every option.
  const ingestScope = useMemo(() => ingestScopeFor(activeProject?.source_category), [activeProject])
  const allowsIngest = useCallback((kind) => ingestScope.includes(kind), [ingestScope])

  // Same family drives the sidebar's Knowledge Base rows.  While the project
  // is still loading, no rows render rather than flashing the full list.
  const sidebarScope = useMemo(() => {
    if (!projectId) return null
    if (!activeProject) return projectMissing ? null : []
    return sidebarTypesFor(activeProject.source_category)
  }, [projectId, activeProject, projectMissing])

  // Repository Studio replaces the evidence rail inside a project workspace
  // that holds GitHub sources — or was created for them (Code Repositories
  // family), so the options are visible even before the first repo lands.
  // Document, web and global workspaces keep the standard evidence rail.
  const repoStudioSource = useMemo(() => {
    if (!projectId) return null
    return visibleSources.find((s) => s.type === 'github') || null
  }, [projectId, visibleSources])
  const showRepoStudio = useMemo(() => {
    if (!projectId) return false
    if (repoStudioSource) return true
    return activeProject?.source_category === 'github'
  }, [projectId, repoStudioSource, activeProject])

  // Studio tool outputs render in the main window; the rail only holds the
  // five tool buttons.  Cleared when leaving the project or returning to chat.
  // Repo Chat is the main composer itself — not a separate view.
  const [studioView, setStudioView] = useState(null)
  const [chatFocusRequest, setChatFocusRequest] = useState(0)
  useEffect(() => {
    setStudioView(null)
  }, [projectId])
  const effectiveStudio = showRepoStudio ? studioView : null
  const handleStudioSelect = useCallback((id) => {
    if (id === 'chat') {
      setStudioView(null)
      setActiveView('chat')
      setChatFocusRequest((n) => n + 1)
      return
    }
    setStudioView(id)
    setActiveView('chat')
  }, [])
  const studioLabel = STUDIO_TOOLS.find((t) => t.id === effectiveStudio)?.label || ''

  // The sidebar owns source selection.  That one selection drives chat, the mind
  // map and every other AI capability in this workspace.
  const selection = useSourceSelection(visibleSources)
  const {
    selectedIds: selectedSourceIds,
    select: selectSource,
    selectOnly: selectOnlySource,
    toggle: toggleSource,
    selectAll: selectAllSources,
    clear: clearSourceSelection,
  } = selection

  // The Mind Map tab's in-tab picker edits the same selection the sidebar owns.
  const setSelection = useCallback(
    (ids) => {
      selection.replaceAll(ids)
    },
    [selection],
  )

  // Chat and Mind Map share the selection, so both stay on the same scope.
  // The Mind Map is reached from a button in the evidence rail, not a tab.
  const [activeView, setActiveView] = useState('chat')
  const handleOpenMindMap = useCallback(() => {
    setStudioView(null)
    setActiveView((view) => (view === 'mindmap' ? 'chat' : 'mindmap'))
  }, [])

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
  } = useChat({ sourceIds: selectedSourceIds })

  const pushNotification = useCallback((type, text) => {
    const id = `${type}-${Date.now()}`
    setNotifications((prev) => [...prev, { id, type, text }])
    setTimeout(() => {
      setNotifications((prev) => prev.filter((item) => item.id !== id))
    }, 4000)
  }, [])

  // Attach a freshly ingested source to the open project (if any) and refresh
  // the project's membership so its card count updates immediately.
  const attachToProject = useCallback(
    async (sourceId) => {
      if (!projectId || !sourceId) return
      try {
        const updated = await attachSourceToProject(projectId, sourceId)
        setActiveProject(updated)
      } catch {
        /* best effort — source is still ingested globally */
      }
    },
    [projectId],
  )

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
        await attachToProject(response.source_id)
      } catch (uploadError) {
        updateSource(tempId, { status: 'failed' })
        pushNotification('error', uploadError.message || 'Upload failed')
      } finally {
        setIsUploading(false)
      }
    },
    [addSource, pushNotification, updateSource, attachToProject],
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
        await attachToProject(response.source_id)
      } catch (ingestError) {
        updateSource(tempId, { status: 'failed' })
        pushNotification('error', ingestError.message || 'Ingest failed')
      } finally {
        setIsAddingUrl(false)
      }
    },
    [addSource, pushNotification, updateSource, attachToProject],
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
        await attachToProject(response.source_id)
        setIsModalOpen(false)
        // There is no per-source page any more: select the new source so the
        // workspace is scoped to it, and let the user reach Repository
        // Intelligence from the source details panel.
        selectOnlySource(response.source_id)
      } catch (repoError) {
        updateSource(tempId, { status: 'failed' })
        pushNotification('error', repoError.message || 'GitHub ingest failed')
      } finally {
        setIsAddingRepo(false)
      }
    },
    [addSource, pushNotification, updateSource, selectOnlySource, attachToProject],
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
        await attachToProject(response.source_id)
      } catch (textError) {
        updateSource(tempId, { status: 'failed' })
        pushNotification('error', textError.message || 'Text ingest failed')
      } finally {
        setIsAddingText(false)
      }
    },
    [addSource, pushNotification, updateSource, attachToProject],
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
        await attachToProject(response.source_id)
      } catch (ingestError) {
        updateSource(tempId, { status: 'failed' })
        pushNotification('error', ingestError.message || 'YouTube ingest failed')
      } finally {
        setIsAddingYoutube(false)
      }
    },
    [addSource, pushNotification, updateSource, attachToProject],
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

  // The ⋮ menu's Remove action asks first — deleting a source drops its chunks
  // from the knowledge base and cannot be undone.
  const handleRequestRemoveSource = useCallback(
    async (source) => {
      const confirmed = await showConfirm(
        `Remove "${source.title}"? Its chunks are deleted from the knowledge base and this cannot be undone.`,
      )
      if (!confirmed) return
      await handleDeleteSource(source.id)
      pushNotification('success', `Removed "${source.title}".`)
    },
    [showConfirm, handleDeleteSource, pushNotification],
  )

  const handleRequestRenameSource = useCallback((source) => {
    setRenameTarget(source)
    setRenameValue(source.title || '')
  }, [])

  const handleCommitRename = useCallback(async () => {
    const clean = renameValue.trim()
    if (!renameTarget || !clean || renameSaving) return
    setRenameSaving(true)
    try {
      await renameSource(renameTarget.id, clean)
      setRenameTarget(null)
      pushNotification('success', `Renamed to "${clean}".`)
    } catch (err) {
      pushNotification('error', err.message || 'Failed to rename source.')
    } finally {
      setRenameSaving(false)
    }
  }, [renameTarget, renameValue, renameSaving, renameSource, pushNotification])

  // Escape closes the rename dialog.
  useEffect(() => {
    if (!renameTarget) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape' && !renameSaving) setRenameTarget(null)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [renameTarget, renameSaving])

  // How many sources chat is currently allowed to draw on, for its counter.
  const chatScopeCount =
    selectedSourceIds.length > 0 ? selectedSourceIds.length : visibleSources.length

  const main = (
    <div className="main-card is-bare">
      {projectId ? (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '0 24px 14px 0',
            fontSize: '0.82rem',
            color: 'var(--mute)',
          }}
        >
          {projectMissing ? (
            <span>This project could not be found.</span>
          ) : (
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              <strong style={{ color: 'var(--ink-strong)' }}>
                {activeProject?.name || 'Loading project…'}
              </strong>
              {activeProject
                ? ` · ${visibleSources.length} of ${sources.length} sources in view`
                : ''}
            </span>
          )}
        </div>
      ) : null}

      {effectiveStudio ? (
        <div className="rs-main">
          <div className="rs-main-head">
            <div>
              <span className="ev-eyebrow">Studio</span>
              <h2>{studioLabel}</h2>
            </div>
            <button className="mh-back" onClick={() => setStudioView(null)}>
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <polyline points="15 18 9 12 15 6" />
              </svg>
              <span>Back to chat</span>
            </button>
          </div>
          <div className="rs-main-body">
            <StudioView
              tool={effectiveStudio}
              projectId={projectId}
              hasGithubSource={Boolean(repoStudioSource)}
            />
          </div>
        </div>
      ) : activeView === 'chat' ? (
        <ChatBox
          messages={messages}
          input={input}
          onInputChange={setInput}
          onSend={sendMessage}
          isStreaming={isStreaming}
          error={error}
          onRetry={retryLast}
          uploadHint={showUploadHint}
          onNewChat={resetChat}
          sourceCount={chatScopeCount}
          focusRequest={chatFocusRequest}
          studioPreviews={
            showRepoStudio ? { tools: STUDIO_TOOLS, onSelect: handleStudioSelect } : null
          }
        />
      ) : (
        <MindMapPanel
          sources={visibleSources}
          selectedIds={selectedSourceIds}
          onSelectionChange={setSelection}
        />
      )}
    </div>
  )

  const right = showRepoStudio ? (
    <RepoStudio
      repoName={repoStudioSource?.title || activeProject?.name}
      active={effectiveStudio}
      onSelect={handleStudioSelect}
    />
  ) : (
    <SourceViewer
      sources={querySources}
      latency={latency}
      isStreaming={isStreaming}
      confidence={confidence}
      onOpenMindMap={handleOpenMindMap}
      mindMapActive={activeView === 'mindmap'}
    />
  )

  return (
    <>
      <AppShell
        sidebar={
          <Sidebar
            sources={visibleSources}
            loading={loading}
            onAddSource={() => setIsModalOpen(true)}
            onSelectSource={selectSource}
            onToggleSource={toggleSource}
            onSelectAllSources={selectAllSources}
            onClearSourceSelection={clearSourceSelection}
            selectedSourceIds={selectedSourceIds}
            onRenameSource={handleRequestRenameSource}
            onDeleteSource={handleRequestRemoveSource}
            onClearKB={handleClearKB}
            scopeTypes={sidebarScope}
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
                {projectId && activeProject ? (
                  <span className="eyebrow">Project · {activeProject.name}</span>
                ) : null}
                <h2>
                  {projectId && activeProject && activeProject.source_category !== 'all'
                    ? `Add ${sourceCategoryLabel(activeProject.source_category)}`
                    : 'Expand your knowledge base'}
                </h2>
                <p>
                  {projectId && activeProject && activeProject.source_category !== 'all'
                    ? `This project holds ${sourceCategoryLabel(activeProject.source_category).toLowerCase()} — add them to “${activeProject.name}” below.`
                    : 'Ingest sources in multiple formats and keep your RAG workspace grounded.'}
                </p>
              </div>
              <button className="icon-button" onClick={() => setIsModalOpen(false)}>
                x
              </button>
            </div>

            <div className={`modal-grid${ingestScope.length === 1 ? ' is-single' : ''}`}>
              {allowsIngest('files') ? (
                <div
                  className="option-card"
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={handleFileDrop}
                >
                  <div className="option-head">
                    <div className="option-icon is-files">
                      <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                        <rect x="2" y="2" width="20" height="20" rx="4" fill="#3d3a39" />
                        <rect x="2" y="2" width="13" height="7" rx="4" fill="#8b949e" />
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
              ) : null}

              {allowsIngest('web') ? (
                <div className="option-card">
                  <div className="option-head">
                    <div className="option-icon is-web">
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
              ) : null}

              {allowsIngest('youtube') ? (
                <div className="option-card">
                  <div className="option-head">
                    <div className="option-icon is-youtube">
                      <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                        <rect x="2" y="4" width="20" height="16" rx="4" fill="#3d3a39" />
                        <path d="M10 9l6 3-6 3z" fill="#f2f2f2" />
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
              ) : null}

              {allowsIngest('github') ? (
                <div className="option-card">
                  <div className="option-head">
                    <div className="option-icon is-github">
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
              ) : null}

              {allowsIngest('text') ? (
                <div className="option-card">
                  <div className="option-head">
                    <div className="option-icon is-text">
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
              ) : null}
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

      {renameTarget ? (
        <div
          className="confirm-backdrop"
          onClick={() => {
            if (!renameSaving) setRenameTarget(null)
          }}
        >
          <div className="confirm-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Rename source</h3>
            <p>Give this source a name you will recognise in the sidebar.</p>
            <input
              className="confirm-input"
              value={renameValue}
              autoFocus
              maxLength={200}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  handleCommitRename()
                }
              }}
              aria-label="New source name"
            />
            <div className="confirm-actions">
              <button
                className="confirm-cancel"
                onClick={() => setRenameTarget(null)}
                disabled={renameSaving}
              >
                Cancel
              </button>
              <button
                className="confirm-danger"
                onClick={handleCommitRename}
                disabled={renameSaving || !renameValue.trim()}
              >
                {renameSaving ? 'Saving…' : 'Save name'}
              </button>
            </div>
          </div>
        </div>
      ) : null}

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
