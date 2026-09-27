import { useCallback, useEffect, useRef, useState } from 'react'

import {
  attachSourceToProject,
  createProject,
  deleteProject,
  detachSourceFromProject,
  getProject,
  listProjects,
  touchProject,
  updateProject,
} from '../services/api'

// Shared project-library store.  The backend is the source of truth
// (SQLite, survives restarts); this hook adds loading / error / optimistic
// states and keeps the list sorted by recency for instant UI feedback.
export function useProjects() {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listProjects()
      if (!mountedRef.current) return
      setProjects(data?.projects || [])
    } catch (err) {
      if (!mountedRef.current) return
      setError(err.message || 'Could not load projects.')
      setProjects([])
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const create = useCallback(
    async ({ name, description = '', category = '', source_category = 'documents' }) => {
      const project = await createProject({ name, description, category, source_category })
      setProjects((prev) => [project, ...prev])
      return project
    },
    [],
  )

  const rename = useCallback(async (id, fields) => {
    const updated = await updateProject(id, fields)
    setProjects((prev) => prev.map((p) => (p.id === id ? updated : p)))
    return updated
  }, [])

  const remove = useCallback(async (id) => {
    await deleteProject(id)
    setProjects((prev) => prev.filter((p) => p.id !== id))
  }, [])

  const touch = useCallback(async (id) => {
    try {
      const updated = await touchProject(id)
      setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, ...updated } : p)))
      return updated
    } catch {
      return null
    }
  }, [])

  const fetchOne = useCallback(async (id) => {
    const project = await getProject(id)
    setProjects((prev) => {
      if (prev.some((p) => p.id === id)) return prev.map((p) => (p.id === id ? project : p))
      return [project, ...prev]
    })
    return project
  }, [])

  const attachSource = useCallback(async (projectId, sourceId) => {
    const updated = await attachSourceToProject(projectId, sourceId)
    setProjects((prev) => prev.map((p) => (p.id === projectId ? updated : p)))
    return updated
  }, [])

  const detachSource = useCallback(async (projectId, sourceId) => {
    const updated = await detachSourceFromProject(projectId, sourceId)
    setProjects((prev) => prev.map((p) => (p.id === projectId ? updated : p)))
    return updated
  }, [])

  return {
    projects,
    loading,
    error,
    refresh,
    create,
    rename,
    remove,
    touch,
    fetchOne,
    attachSource,
    detachSource,
  }
}
