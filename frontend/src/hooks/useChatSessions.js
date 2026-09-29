import { useCallback, useEffect, useRef, useState } from 'react'

import { createChatSession, deleteChatSession, listChatSessions } from '../services/api'

// Manages the persisted chat sessions that belong to one project.
//
// Sessions are owned by the backend (SQLite, survive restarts); this hook keeps
// the list, exposes the active session id, and lazily creates a session the
// first time a project is opened so a fresh project always has somewhere to
// write.  Switching between sessions never touches message history — each
// session's messages live under its own id.
export function useChatSessions(projectId = null) {
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [loading, setLoading] = useState(false)
  const mountedRef = useRef(true)
  const creatingRef = useRef(null)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const refresh = useCallback(async () => {
    if (!projectId) {
      setSessions([])
      setActiveSessionId(null)
      return []
    }
    setLoading(true)
    try {
      const data = await listChatSessions(projectId)
      if (!mountedRef.current) return []
      const list = data?.sessions || []
      setSessions(list)
      setActiveSessionId((current) => {
        if (current && list.some((s) => s.id === current)) return current
        return list[0]?.id || null
      })
      return list
    } catch {
      if (mountedRef.current) setSessions([])
      return []
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    // Reset immediately when the project changes so the previous project's
    // sessions are never shown against the new project.
    setSessions([])
    setActiveSessionId(null)
    if (projectId) refresh()
  }, [projectId, refresh])

  const createSession = useCallback(
    async (title = '') => {
      if (!projectId) return null
      const session = await createChatSession(projectId, { title })
      if (mountedRef.current) {
        setSessions((prev) => [session, ...prev])
        setActiveSessionId(session.id)
      }
      return session
    },
    [projectId],
  )

  // Ensure an active session exists, creating one on demand.  Concurrent calls
  // share the same in-flight creation so a double send cannot open two sessions.
  const ensureSession = useCallback(async () => {
    if (!projectId) return null
    if (activeSessionId) return activeSessionId
    if (creatingRef.current) return creatingRef.current
    const promise = createSession('')
      .then((session) => session?.id || null)
      .finally(() => {
        creatingRef.current = null
      })
    creatingRef.current = promise
    return promise
  }, [projectId, activeSessionId, createSession])

  const removeSession = useCallback(async (sessionId) => {
    await deleteChatSession(sessionId)
    if (!mountedRef.current) return
    setSessions((prev) => {
      const next = prev.filter((s) => s.id !== sessionId)
      setActiveSessionId((current) => (current === sessionId ? next[0]?.id || null : current))
      return next
    })
  }, [])

  const activeSession = sessions.find((s) => s.id === activeSessionId) || null

  return {
    sessions,
    activeSession,
    activeSessionId,
    setActiveSessionId,
    loading,
    refresh,
    createSession,
    ensureSession,
    removeSession,
  }
}
