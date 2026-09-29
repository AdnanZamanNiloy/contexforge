const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

// RAG queries run HyDE expansion + retrieval + rerank + LLM generation, which
// routinely takes 8-20s and can exceed 30s under load.  A short timeout aborts a
// legitimate request, which the browser reports as "NetworkError when attempting
// to fetch resource".
const DEFAULT_TIMEOUT_MS = 120000

// Mind map generation gets a longer window than an ordinary request: the server
// caps a single generation at 135s (MAX_GENERATION_SECONDS), and a multi-source
// map feeds chunks from every selected source into one prompt.  This must stay
// above that cap, otherwise the browser would abort first and the user would see
// an opaque network error instead of the server's clear timeout message.
const MIND_MAP_TIMEOUT_MS = 165000

function buildUrl(path) {
  if (!path.startsWith('/')) {
    return `${API_BASE}/${path}`
  }
  return `${API_BASE}${path}`
}

async function request(path, options = {}) {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  }

  try {
    const response = await fetch(buildUrl(path), {
      ...fetchOptions,
      headers,
      signal: controller.signal,
    })

    if (!response.ok) {
      let detail = 'Request failed'
      try {
        const data = await response.json()
        detail = data.detail || data.message || JSON.stringify(data)
      } catch {
        detail = await response.text()
      }
      throw new Error(detail)
    }

    if (response.status === 204) {
      return null
    }

    return response.json()
  } finally {
    clearTimeout(timeoutId)
  }
}

export async function pingApi() {
  return request('/health', { method: 'GET' })
}

export async function ingestSource(payload) {
  return request('/ingest/source', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function ingestGithub(payload) {
  return request('/github/ingest', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function ingestFile({ source_type, file }) {
  const formData = new FormData()
  formData.append('upload', file)

  const response = await fetch(buildUrl(`/ingest/file?source_type=${source_type}`), {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    let detail
    try {
      const data = await response.json()
      detail = data.detail || data.message || JSON.stringify(data)
    } catch {
      detail = await response.text()
    }
    throw new Error(detail)
  }

  return response.json()
}

export async function deleteSource(sourceId) {
  return request(`/ingest/source/${encodeURIComponent(sourceId)}`, {
    method: 'DELETE',
  })
}

// Rename a source.  The backend stores this as a display-title override
// layered over the title derived from the source's chunk metadata.
export async function updateSourceTitle(sourceId, title) {
  return request(`/ingest/source/${encodeURIComponent(sourceId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  })
}

export async function clearKnowledgeBase() {
  return request('/ingest/clear', {
    method: 'DELETE',
  })
}

export async function fetchSources() {
  return request('/ingest/sources', {
    method: 'GET',
  })
}

export async function queryAnswer(payload) {
  return request('/query', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

const STREAM_IDLE_TIMEOUT_MS = 120000

export async function streamQuery(payload, handlers = {}, path = '/query/stream') {
  const controller = new AbortController()
  const externalSignal = handlers.signal
  const onExternalAbort = () => controller.abort()
  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort()
    } else {
      externalSignal.addEventListener('abort', onExternalAbort, { once: true })
    }
  }

  let idleTimer = null
  let timedOut = false
  const resetIdle = () => {
    if (idleTimer) {
      clearTimeout(idleTimer)
    }
    idleTimer = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, STREAM_IDLE_TIMEOUT_MS)
  }

  try {
    const response = await fetch(buildUrl(path), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })

    resetIdle()

    if (!response.ok || !response.body) {
      throw new Error('Streaming request failed to start')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) {
        break
      }

      resetIdle()

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const cleaned = line.replace(/\r$/, '')
        if (!cleaned.startsWith('data:')) {
          continue
        }
        let data = cleaned.slice(5)
        if (data.startsWith(' ')) {
          data = data.slice(1)
        }
        if (!data) {
          continue
        }

        if (data.startsWith('[STATUS]')) {
          // A progress marker sent before any token exists, so the UI can say
          // what it is doing instead of sitting on an empty bubble. Sent twice
          // per request: once when retrieval starts, once when generation does.
          if (handlers.onStatus) {
            handlers.onStatus(data.replace('[STATUS]', '').trim())
          }
          continue
        }

        if (data.startsWith('[SOURCES]')) {
          const json = data.replace('[SOURCES]', '').trim()
          if (handlers.onSources) {
            try {
              handlers.onSources(JSON.parse(json))
            } catch {
              handlers.onSources([])
            }
          }
          continue
        }

        if (data.startsWith('[LATENCY]')) {
          const json = data.replace('[LATENCY]', '').trim()
          if (handlers.onLatency) {
            try {
              handlers.onLatency(JSON.parse(json))
            } catch {
              handlers.onLatency({})
            }
          }
          continue
        }

        if (data.startsWith('[CONFIDENCE]')) {
          const json = data.replace('[CONFIDENCE]', '').trim()
          if (handlers.onConfidence) {
            try {
              handlers.onConfidence(JSON.parse(json))
            } catch {
              handlers.onConfidence(null)
            }
          }
          continue
        }

        if (data.startsWith('[ERROR]')) {
          const message = data.replace('[ERROR]', '').trim()
          if (handlers.onError) {
            handlers.onError(message || 'Streaming error')
          }
          continue
        }

        if (data.startsWith('[DONE]')) {
          if (handlers.onDone) {
            handlers.onDone()
          }
          continue
        }

        if (handlers.onToken) {
          handlers.onToken(data)
        }
      }
    }
  } catch (error) {
    if (timedOut) {
      throw new Error('Backend stopped responding — please try again.', { cause: error })
    }
    throw error
  } finally {
    if (idleTimer) {
      clearTimeout(idleTimer)
    }
    if (externalSignal) {
      externalSignal.removeEventListener('abort', onExternalAbort)
    }
  }
}

// --- Mind Map ---------------------------------------------------------------

// The workspace can build a map from one source or from several at once.  A
// single source posts `source_id` so the backend keeps using the pre-existing
// cache entry for it; multiple sources post `source_ids` and are keyed by a
// sorted composite key server-side.
export async function createMindMap(sourceIds, options = {}) {
  const ids = (Array.isArray(sourceIds) ? sourceIds : [sourceIds]).filter(Boolean)
  const body = ids.length === 1 ? { source_id: ids[0] } : { source_ids: ids }
  if (options.refresh) body.refresh = true
  return request('/mindmap/generate', {
    method: 'POST',
    body: JSON.stringify(body),
    timeoutMs: MIND_MAP_TIMEOUT_MS,
  })
}

export async function getMindMap(sourceIds) {
  const ids = (Array.isArray(sourceIds) ? sourceIds : [sourceIds]).filter(Boolean)
  if (ids.length === 0) return null
  // Mirror the server's key derivation so a GET addresses the same entry the
  // POST created (single source = its own id, several = sorted composite).
  const key = ids.length === 1 ? ids[0] : `multi:${[...new Set(ids)].sort().join(',')}`
  const response = await fetch(buildUrl(`/mindmap/${encodeURIComponent(key)}`), {
    method: 'GET',
  })
  if (response.status === 404) {
    return null
  }
  if (!response.ok) {
    let detail = 'Failed to load mind map'
    try {
      const data = await response.json()
      detail = data.detail || data.message || detail
    } catch {
      detail = await response.text()
    }
    throw new Error(detail)
  }
  return response.json()
}

// --- Model Center -------------------------------------------------------------
//
// API keys travel in the JSON request body only — never in a URL — and the
// backend redacts them from every response.

export async function listModels() {
  return request('/models', { method: 'GET' })
}

export async function createModel(payload) {
  return request('/models', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateModel(modelId, payload) {
  return request(`/models/${encodeURIComponent(modelId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteModel(modelId) {
  return request(`/models/${encodeURIComponent(modelId)}`, { method: 'DELETE' })
}

export async function testModel(modelId) {
  return request(`/models/${encodeURIComponent(modelId)}/test`, { method: 'POST' })
}

export async function listChains() {
  return request('/chains', { method: 'GET' })
}

export async function createChain(payload) {
  return request('/chains', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function updateChain(chainId, payload) {
  return request(`/chains/${encodeURIComponent(chainId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteChain(chainId) {
  return request(`/chains/${encodeURIComponent(chainId)}`, { method: 'DELETE' })
}

export async function testChain(chainId) {
  return request(`/chains/${encodeURIComponent(chainId)}/test`, { method: 'POST' })
}

export async function getServing() {
  return request('/serving', { method: 'GET' })
}

export async function updateServing(payload) {
  return request('/serving', {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

// --- Projects library ------------------------------------------------------
//
// Lightweight metadata + membership.  Sources themselves stay global in
// FAISS/BM25; these endpoints only group source_ids into named projects.

export async function listProjects() {
  return request('/projects', { method: 'GET' })
}

export async function createProject({
  name,
  description = '',
  category = '',
  source_category = 'documents',
}) {
  return request('/projects', {
    method: 'POST',
    body: JSON.stringify({ name, description, category, source_category }),
  })
}

export async function getProject(projectId) {
  return request(`/projects/${encodeURIComponent(projectId)}`, { method: 'GET' })
}

export async function updateProject(projectId, payload) {
  return request(`/projects/${encodeURIComponent(projectId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteProject(projectId) {
  const response = await fetch(buildUrl(`/projects/${encodeURIComponent(projectId)}`), {
    method: 'DELETE',
  })
  if (!response.ok) {
    let detail = 'Failed to delete project'
    try {
      const data = await response.json()
      detail = data.detail || data.message || detail
    } catch {
      detail = await response.text()
    }
    throw new Error(detail)
  }
  return true
}

export async function touchProject(projectId) {
  return request(`/projects/${encodeURIComponent(projectId)}/touch`, {
    method: 'POST',
  })
}

export async function attachSourceToProject(projectId, sourceId) {
  return request(`/projects/${encodeURIComponent(projectId)}/sources`, {
    method: 'POST',
    body: JSON.stringify({ source_id: sourceId }),
  })
}

export async function detachSourceFromProject(projectId, sourceId) {
  return request(
    `/projects/${encodeURIComponent(projectId)}/sources/${encodeURIComponent(sourceId)}`,
    { method: 'DELETE' },
  )
}

// --- Architecture Diagram ---------------------------------------------------

// The server caps a cold generation at 110s (MAX_GENERATION_SECONDS) and serves a
// cached diagram immediately.  This window stays above that cap so the browser
// never aborts first and reports an opaque network error instead of the
// server's readable timeout message.  Both were doubled together: a 55s server
// cap abandoned runs that were still making progress through the provider
// fallback chain, and the client window has to track it or the browser becomes
// the thing that gives up first.
const ARCHITECTURE_TIMEOUT_MS = 180000

// Stream the finished diagram over SSE.  A cold run spends most of its time in a
// single model call, so the stream exists to let the client show progress and to
// carry a readable failure rather than a bare network drop.  Deliberately does
// not share code with `streamQuery`, so the chat transport stays untouched.
export async function streamArchitecture(payload, handlers = {}, path = '/architecture/generate') {
  const controller = new AbortController()
  const externalSignal = handlers.signal
  const onExternalAbort = () => controller.abort()
  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort()
    } else {
      externalSignal.addEventListener('abort', onExternalAbort, { once: true })
    }
  }

  let idleTimer = null
  let timedOut = false
  const resetIdle = () => {
    if (idleTimer) clearTimeout(idleTimer)
    idleTimer = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, ARCHITECTURE_TIMEOUT_MS)
  }

  try {
    const response = await fetch(buildUrl(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })

    resetIdle()

    if (!response.ok || !response.body) {
      let detail = 'Architecture request failed to start'
      try {
        const data = await response.json()
        detail = data.detail || data.message || detail
      } catch {
        /* keep the default message */
      }
      if (handlers.onError) handlers.onError(detail)
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { value, done } = await reader.read()
      if (done) break

      resetIdle()

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const cleaned = line.replace(/\r$/, '')
        if (!cleaned.startsWith('data:')) continue
        let data = cleaned.slice(5)
        if (data.startsWith(' ')) data = data.slice(1)
        if (!data) continue

        if (data.startsWith('[DIAGRAM]')) {
          const json = data.replace('[DIAGRAM]', '').trim()
          if (handlers.onDiagram) {
            try {
              handlers.onDiagram(JSON.parse(json))
            } catch {
              handlers.onError('The diagram could not be read — please try again.')
            }
          }
          continue
        }

        if (data.startsWith('[ERROR]')) {
          let message = 'Architecture generation failed — please retry.'
          try {
            message = JSON.parse(data.replace('[ERROR]', '').trim()).message || message
          } catch {
            message = data.replace('[ERROR]', '').trim() || message
          }
          if (handlers.onError) handlers.onError(message)
          return
        }

        if (data.startsWith('[DONE]')) {
          if (handlers.onDone) handlers.onDone()
          return
        }
      }
    }

    if (handlers.onDone) handlers.onDone()
  } catch (error) {
    if (timedOut) {
      if (handlers.onError) {
        handlers.onError('The backend stopped responding — please try again.')
      }
      return
    }
    if (error && error.name === 'AbortError') return
    if (handlers.onError) handlers.onError('Could not reach the backend — please try again.')
  } finally {
    if (idleTimer) clearTimeout(idleTimer)
    if (externalSignal) externalSignal.removeEventListener('abort', onExternalAbort)
  }
}

export async function regenerateArchitecture(projectId, handlers = {}) {
  return streamArchitecture(
    { project_id: projectId, refresh: true },
    handlers,
    '/architecture/regenerate',
  )
}

export async function getArchitecture(projectId) {
  return request(`/architecture/${encodeURIComponent(projectId)}`)
}

// --- Dependency & Tech Stack ------------------------------------------------

// A scan is local string processing over chunks already in memory, so it lands
// in milliseconds and needs no streaming or special timeout handling.
export async function getTechStack(projectId) {
  return request(`/tech-stack/${encodeURIComponent(projectId)}`)
}

export async function scanTechStack(projectId, { refresh = false } = {}) {
  return request('/tech-stack/scan', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId, refresh }),
  })
}

// --- Security & Quality -----------------------------------------------------

// A security scan reads the indexed source and, when a manifest pins a
// resolvable version, asks OSV.dev about it.  That makes it seconds rather than
// milliseconds -- still a plain request, so still no streaming.
export async function getSecurityScan(projectId) {
  return request(`/security/${encodeURIComponent(projectId)}`)
}

export async function scanSecurity(projectId, { refresh = false } = {}) {
  return request('/security/scan', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId, refresh }),
  })
}

// --- Health Score & Hotspots ------------------------------------------------

// A health scan is AST parsing of chunks already in memory, so it lands in
// milliseconds and needs no streaming or special timeout handling.
export async function getHealthScan(projectId) {
  return request(`/health/${encodeURIComponent(projectId)}`)
}

export async function scanHealth(projectId, { refresh = false } = {}) {
  return request('/health/scan', {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId, refresh }),
  })
}
