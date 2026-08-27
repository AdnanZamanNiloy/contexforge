import { useNavigate } from 'react-router-dom'

import { SourceGlyph, formatTypeLabel } from '../lib/sources'

// Shared source representation for the explore header.  A GitHub repository,
// a PDF, a web page or a YouTube video all present the same identity row so the
// source reads as one ContextForge knowledge unit.
export default function SourceHeader({ source = {}, onBack, actions }) {
  const navigate = useNavigate()
  const type = source.type || 'unknown'

  return (
    <header className="source-header">
      <div className="source-header-left">
        {onBack ? (
          <button className="icon-button source-back" onClick={onBack} title="Back to workspace">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="15 18 9 12 15 6" />
            </svg>
            <span>Workspace</span>
          </button>
        ) : (
          <button
            className="icon-button source-back"
            onClick={() => navigate('/')}
            title="Back to workspace"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="15 18 9 12 15 6" />
            </svg>
            <span>Workspace</span>
          </button>
        )}
        <div className="source-icon">
          <SourceGlyph type={type} size={24} />
        </div>
        <div className="source-identity">
          <div className="source-line">
            <span className="source-name">{source.title || 'Untitled source'}</span>
            <span className={`source-type-pill is-${type}`}>{formatTypeLabel(type)}</span>
          </div>
          <div className="source-sub">{formatSourceMetaExtended(source)}</div>
        </div>
      </div>
      {actions ? <div className="source-header-right">{actions}</div> : null}
    </header>
  )
}

function formatSourceMetaExtended(source) {
  if (source.url) {
    try {
      return new URL(source.url).hostname.replace(/^www\./, '')
    } catch {
      return source.url
    }
  }
  return `${source.chunks || 0} chunks indexed`
}
