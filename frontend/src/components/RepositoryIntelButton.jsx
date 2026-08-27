import { useEffect, useRef, useState } from 'react'

import { useRepository } from '../hooks/useRepository'

const NOT_INGESTED_MESSAGE =
  'Select a repo to get started, then explore it with Repository Intelligence.'

// Launches Repository Intelligence from an evidence rail. It only becomes
// actionable once the repository has an analysis (i.e. it has been ingested);
// otherwise clicking it surfaces guidance instead of navigating anywhere.
export default function RepositoryIntelButton({ repoUrl, onOpen }) {
  const [showPrompt, setShowPrompt] = useState(false)
  const promptTimerRef = useRef(null)

  const repository = useRepository({ repoUrl })

  const hasRepo = Boolean(repoUrl)
  const ingested = !!repository?.analysis
  const checking = Boolean(repository?.loading) && !ingested && hasRepo
  const promptText = hasRepo
    ? repository?.error || NOT_INGESTED_MESSAGE
    : 'Select a repo to get started.'

  const showMessage = () => {
    setShowPrompt(true)
    if (promptTimerRef.current) clearTimeout(promptTimerRef.current)
    promptTimerRef.current = setTimeout(() => setShowPrompt(false), 4500)
  }

  useEffect(
    () => () => {
      if (promptTimerRef.current) clearTimeout(promptTimerRef.current)
    },
    [],
  )

  const handleClick = () => {
    if (checking) return
    if (ingested) {
      onOpen?.()
    } else {
      showMessage()
    }
  }

  let label = 'Repository Intelligence'
  if (checking) label = 'Checking…'

  return (
    <>
      <button
        className={`repo-intel-cta${checking ? ' is-checking' : ''}${ingested ? ' is-ready' : ''}`}
        onClick={handleClick}
        disabled={checking}
      >
        <svg
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="5" cy="6" r="2.2" />
          <circle cx="19" cy="6" r="2.2" />
          <circle cx="12" cy="18" r="2.2" />
          <path d="M7 7.2l3.4 8M17 7.2l-3.4 8" />
        </svg>
        <span>{label}</span>
      </button>
      {showPrompt && !ingested ? (
        <div className="repo-intel-prompt" role="status">
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>{promptText}</span>
        </div>
      ) : null}
    </>
  )
}
