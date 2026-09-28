import { useCallback, useEffect, useRef, useState } from 'react'

import { getArchitecture, regenerateArchitecture, streamArchitecture } from '../services/api'

// The Architecture Diagram view.
//
// Renders a Mermaid map generated from the project's ingested GitHub source.
// Three rules shape everything here:
//
// 1. Mermaid is loaded on demand.  It is a large dependency and this view is one
//    of five Studio tools, so importing it eagerly would tax every workspace
//    load for a panel most visits never open.
// 2. The rendered SVG is rendered with `securityLevel: 'antiscript'` and
//    `htmlLabels: false`, and the source is additionally rejected if it contains
//    a script-ish directive.  The Mermaid text comes from a language model, so it
//    is treated as untrusted output, not as something we authored.
// 3. The cached diagram is shown immediately on open when one exists, so a
//    repeat visit never pays for a model call.  Generating is always explicit.
const MIN_ZOOM = 0.3
const MAX_ZOOM = 3

let mermaidPromise = null

function loadMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then(({ default: mermaid }) => {
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'antiscript',
        htmlLabels: false,
        theme: 'base',
        themeVariables: {
          background: '#0b0b0c',
          primaryColor: '#16233d',
          primaryTextColor: '#e6e8ec',
          primaryBorderColor: '#4d7cfe',
          lineColor: '#5b6472',
          secondaryColor: '#141416',
          tertiaryColor: '#141416',
          // Mermaid's own defaults for these are light/olive, which reads as a
          // bright slab against the dark canvas — a subgraph is the largest
          // filled area on screen, so it has to be themed explicitly.
          clusterBkg: '#101014',
          clusterBorder: 'rgba(255,255,255,0.12)',
          edgeLabelBackground: '#0b0b0c',
          titleColor: '#e6e8ec',
          fontFamily: 'var(--font-sans, system-ui, sans-serif)',
          fontSize: '14px',
        },
        flowchart: { htmlLabels: false, curve: 'basis', padding: 18, useMaxWidth: false },
      })
      return mermaid
    })
  }
  return mermaidPromise
}

// A Mermaid `click` directive or a raw <script> in the source would let model
// output reach the DOM.  The server already escapes label text, so this is the
// second of the three layers that keeps a diagram safe to render.
function isSafeSource(source) {
  return !/<\s*script|javascript:|onload\s*=|onerror\s*=|\bclick\s+\w+\s+"(?!https:\/\/github\.com\/)/i.test(
    source,
  )
}

function CopyIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="9" y="9" width="12" height="12" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}

function RefreshIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 12a9 9 0 1 1-3-6.7" />
      <path d="M21 3v6h-6" />
    </svg>
  )
}

function ZoomIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.5-3.5M11 8v6M8 11h6" />
    </svg>
  )
}

function DiagramIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="2" y="9" width="6" height="6" rx="1.5" />
      <rect x="16" y="3" width="6" height="6" rx="1.5" />
      <rect x="16" y="15" width="6" height="6" rx="1.5" />
      <path d="M8 12h4M12 6h4M12 18h4" />
    </svg>
  )
}

function ZoomControls({ zoom, onZoom, onFit }) {
  return (
    <div className="ad-zoom" role="group" aria-label="Diagram zoom">
      <button
        type="button"
        onClick={() => onZoom(-1)}
        aria-label="Zoom out"
        disabled={zoom <= MIN_ZOOM}
      >
        −
      </button>
      <span className="ad-zoom-level">{Math.round(zoom * 100)}%</span>
      <button
        type="button"
        onClick={() => onZoom(1)}
        aria-label="Zoom in"
        disabled={zoom >= MAX_ZOOM}
      >
        +
      </button>
      <button type="button" onClick={onFit} aria-label="Fit diagram to view">
        <ZoomIcon />
      </button>
    </div>
  )
}

export default function ArchitectureDiagram({ projectId, hasGithubSource = true }) {
  const [diagram, setDiagram] = useState(null)
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState('')
  const [zoom, setZoom] = useState(1)
  const [copied, setCopied] = useState(false)

  const surfaceRef = useRef(null)
  const svgHostRef = useRef(null)
  const dragRef = useRef(null)

  const run = useCallback(
    (regenerate) => {
      if (!projectId) return
      setStatus('loading')
      setError('')

      const handlers = {
        onDiagram: (payload) => {
          setDiagram(payload)
          setStatus('ready')
          setZoom(1)
        },
        onError: (message) => {
          setError(message)
          setStatus('error')
        },
        onDone: () => setStatus((s) => (s === 'loading' ? 'ready' : s)),
      }

      const payload = { project_id: projectId, refresh: false }
      if (regenerate) {
        regenerateArchitecture(projectId, handlers)
      } else {
        streamArchitecture(payload, handlers)
      }
    },
    [projectId],
  )

  // A stored diagram is shown on open; only fall back to a generation when the
  // project has none yet.  Runs once per project.
  useEffect(() => {
    let cancelled = false
    if (!projectId || !hasGithubSource) return undefined

    getArchitecture(projectId)
      .then((stored) => {
        if (cancelled || !stored) {
          run(false)
          return
        }
        setDiagram(stored)
        setStatus('ready')
        setZoom(1)
      })
      .catch(() => {
        // 404 simply means nothing cached yet.
        if (!cancelled) run(false)
      })

    return () => {
      cancelled = true
    }
  }, [projectId, hasGithubSource, run])

  // Compile the Mermaid source whenever it changes.  Mermaid renders into the
  // element it is handed, so the host div is emptied first to avoid stacking
  // graphs on re-render.
  useEffect(() => {
    const host = svgHostRef.current
    const source = diagram?.mermaid
    if (!host || !source || !isSafeSource(source)) return undefined

    let cancelled = false
    const id = `ad-${Math.random().toString(36).slice(2, 9)}`

    loadMermaid()
      .then((mermaid) => mermaid.render(id, source))
      .then(({ svg }) => {
        if (cancelled || !host) return
        host.innerHTML = svg
      })
      .catch((err) => {
        if (cancelled) return
        console.error('ArchitectureDiagram: mermaid render failed', err)
        setError('The diagram could not be rendered. Try regenerating it.')
      })

    return () => {
      cancelled = true
      // Remove any svg Mermaid left in the document body for this id.
      document.getElementById(id)?.remove()
    }
  }, [diagram?.mermaid])

  // ---- Pan & zoom -------------------------------------------------------- //
  // Pointer events rather than wheel-only, so a trackpad drag pans and a pinch
  // zooms without a scroll listener fighting the page.
  const clamp = (value) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value))

  const onPointerDown = (event) => {
    if (event.button !== 0) return
    const surface = surfaceRef.current
    dragRef.current = {
      x: event.clientX,
      y: event.clientY,
      left: surface.scrollLeft,
      top: surface.scrollTop,
    }
    surface.setPointerCapture?.(event.pointerId)
    surface.classList.add('is-panning')
  }

  const onPointerMove = (event) => {
    const drag = dragRef.current
    const surface = surfaceRef.current
    if (!drag || !surface) return
    surface.scrollLeft = drag.left - (event.clientX - drag.x)
    surface.scrollTop = drag.top - (event.clientY - drag.y)
  }

  const endDrag = (event) => {
    dragRef.current = null
    surfaceRef.current?.classList.remove('is-panning')
    if (event?.pointerId != null) {
      surfaceRef.current?.releasePointerCapture?.(event.pointerId)
    }
  }

  // Ctrl+wheel (or a pinch, which browsers report as ctrlKey) zooms; a plain
  // wheel keeps scrolling the surface as the user expects.
  useEffect(() => {
    const surface = surfaceRef.current
    if (!surface) return undefined
    const onWheel = (event) => {
      if (!event.ctrlKey && !event.metaKey) return
      event.preventDefault()
      setZoom((z) => clamp(z * (event.deltaY < 0 ? 1.1 : 0.9)))
    }
    surface.addEventListener('wheel', onWheel, { passive: false })
    return () => surface.removeEventListener('wheel', onWheel)
  }, [])

  const mermaidSource = diagram?.mermaid
  // Derived at render time rather than stored, so a payload that fails the
  // safety check is never handed to Mermaid in the first place.
  const unsafeSource = Boolean(mermaidSource) && !isSafeSource(mermaidSource)

  const onCopy = useCallback(async () => {
    if (!mermaidSource) return
    try {
      await navigator.clipboard.writeText(mermaidSource)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      setError('Could not copy to the clipboard.')
    }
  }, [mermaidSource])

  // ---- Empty / error / loading ------------------------------------------ //

  if (!projectId) {
    return (
      <div className="rs-view">
        <div className="rs-view-head">
          <h3>Architecture Diagram</h3>
        </div>
        <EmptyState
          title="Open a project to map a repository"
          body="The architecture map is built from a GitHub repository attached to a project."
        />
      </div>
    )
  }

  if (!hasGithubSource) {
    return (
      <div className="rs-view">
        <div className="rs-view-head">
          <h3>Architecture Diagram</h3>
        </div>
        <EmptyState
          title="No GitHub source in this project"
          body="Attach a GitHub repository to the project and it will be indexed. The map is then built from those files."
        />
      </div>
    )
  }

  return (
    <div className="rs-view ad-root">
      <div className="rs-view-head ad-head">
        <div>
          <h3>Architecture Diagram</h3>
          {diagram?.repository ? (
            <p className="ad-meta">
              {diagram.repository}
              {diagram.cached ? ' · cached' : ''}
              {diagram.node_count
                ? ` · ${diagram.node_count} component${diagram.node_count === 1 ? '' : 's'}`
                : ''}
              {diagram.edge_count
                ? ` · ${diagram.edge_count} connection${diagram.edge_count === 1 ? '' : 's'}`
                : ''}
            </p>
          ) : null}
        </div>
        <div className="ad-actions">
          <button
            type="button"
            className="ad-btn"
            onClick={onCopy}
            disabled={!diagram?.mermaid}
            title="Copy the Mermaid source"
          >
            <CopyIcon />
            <span>{copied ? 'Copied' : 'Copy Mermaid'}</span>
          </button>
          <button
            type="button"
            className="ad-btn"
            onClick={() => run(true)}
            disabled={status === 'loading'}
            title="Regenerate from the current source"
          >
            <RefreshIcon />
            <span>Regenerate</span>
          </button>
        </div>
      </div>

      {status === 'loading' && !diagram ? (
        <div className="ad-stage" aria-live="polite">
          <div className="ad-spinner" aria-hidden="true" />
          <p className="ad-stage-title">Mapping the repository…</p>
          <p className="ad-stage-note">
            Reading the file tree, README and a sample of source, then asking the model for a graph.
            Usually under a minute.
          </p>
        </div>
      ) : null}

      {diagram && !unsafeSource ? (
        <>
          {diagram.explanation ? <p className="ad-explanation">{diagram.explanation}</p> : null}
          <div
            className="ad-surface"
            ref={surfaceRef}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
            onPointerLeave={endDrag}
            role="region"
            aria-label="Architecture diagram, drag to pan"
          >
            <div className="ad-canvas" ref={svgHostRef} style={{ transform: `scale(${zoom})` }} />
          </div>
          <div className="ad-foot">
            <ZoomControls
              zoom={zoom}
              onZoom={(delta) => setZoom((z) => clamp(z * (delta > 0 ? 1.2 : 0.83)))}
              onFit={() => setZoom(1)}
            />
            <span className="ad-foot-hint">
              Drag to pan · Ctrl+scroll to zoom
              {diagram.truncated_paths ? ' · some paths were unverified' : ''}
            </span>
          </div>
        </>
      ) : null}

      {unsafeSource ? (
        <p className="ad-error" role="alert">
          The generated diagram could not be rendered safely. Regenerate it to try again.
        </p>
      ) : null}

      {status === 'loading' && diagram ? (
        <p className="ad-rebuilding" aria-live="polite">
          Regenerating…
        </p>
      ) : null}

      {error ? (
        <p className="ad-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  )
}

function EmptyState({ title, body }) {
  return (
    <div className="ad-stage">
      <span className="ad-empty-icon" aria-hidden="true">
        <DiagramIcon />
      </span>
      <p className="ad-stage-title">{title}</p>
      <p className="ad-stage-note">{body}</p>
    </div>
  )
}
