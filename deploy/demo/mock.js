// ---------------------------------------------------------------------------
// Demo backend.
//
// Cloudflare Pages hosts static files only — there is no FastAPI process, no
// SQLite, and no model provider behind the deployed bundle.  This module stands
// in for the whole backend so the workspace, the chat thread, the confidence
// meter and the stage-latency readout all behave as they do against the real
// server.
//
// It is only active when `VITE_DEMO_MODE === 'true'`; `services/api.js` checks
// that flag and delegates here.  The live code path is untouched and every
// value that plays back comes from `demo/seed.js`, which was captured from a
// real running instance.
//
// State is held in module scope, so it lives for the tab, not across reloads.
// That is deliberate: a visitor can create a session, ask a question and watch
// it stream, then reload to a clean, known-good state.  Nothing pretends to
// persist.
// ---------------------------------------------------------------------------

import {
  DEMO_FALLBACK,
  DEMO_MATCHERS,
  DEMO_PROJECTS,
  DEMO_SESSIONS,
  DEMO_SOURCES,
} from './seed.js'

// A deep-ish clone so a visitor's edits never mutate the imported seed and
// leak into the next question they ask.
function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

// --- In-memory stores ------------------------------------------------------

let projects = clone(DEMO_PROJECTS)
let sessions = clone(DEMO_SESSIONS)
let sources = clone(DEMO_SOURCES)

const now = () => new Date().toISOString()
let idCounter = 1000
const nextId = (prefix) => `${prefix}_demo_${idCounter++}`

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

// --- Shape helpers ---------------------------------------------------------
// These mirror the server's response envelopes exactly, so the hooks and
// components downstream cannot tell the difference.

function projectRecord(project) {
  const { source_ids = [], ...rest } = project
  return { ...clone(rest), sources: clone(source_ids), source_count: source_ids.length }
}

function sessionRecord(session) {
  const { messages: _messages, ...rest } = session
  return clone(rest)
}

function messageRecord(message) {
  return {
    id: message.id,
    role: message.role,
    text: message.text || '',
    status: message.status || 'done',
    source_ids: message.sourceIds || [],
    confidence: message.confidence || null,
    created_at: message.created_at || now(),
  }
}

// --- Public: status --------------------------------------------------------

export async function pingApi() {
  return { status: 'ok', service: 'contextforge-demo' }
}

// --- Public: sources -------------------------------------------------------

export async function fetchSources() {
  await sleep(60)
  return {
    total_chunks: sources.reduce((sum, s) => sum + (s.chunks || 0), 0),
    sources: clone(sources),
  }
}

export async function fetchSourceDetail(sourceId) {
  await sleep(80)
  const source = sources.find((s) => s.source_id === sourceId)
  if (!source) throw new Error(`Source ${sourceId} not found`)

  // An extraction verdict, shaped like the server's. Every seeded source
  // extracted cleanly, so the verdict is healthy; the fields are present so
  // the panel renders its real layout.
  const healthy = source.chunks > 1
  return {
    source_id: source.source_id,
    title: source.title,
    type: source.type,
    url: source.url || null,
    chunks: source.chunks,
    extraction: {
      status: healthy ? 'ok' : 'low_text',
      reason: healthy
        ? null
        : 'Only a small amount of text was extracted from this source.',
      language: 'en',
      page_count: source.type === 'web' ? 1 : null,
      pages_without_text: 0,
      text_length: source.chunks * 1600,
    },
    files: source.type === 'github' ? ['backend/app.py', 'frontend/src/App.jsx', 'requirements.txt'] : [],
  }
}

export async function fetchSourceContent(sourceId) {
  await sleep(60)
  const source = sources.find((s) => s.source_id === sourceId)
  if (!source) throw new Error(`Source ${sourceId} not found`)
  return {
    source_id: source.source_id,
    chunks: [
      {
        index: 0,
        text: `Indexed text for “${source.title}”. In the running app this is the exact chunk text retrieval holds and would quote — the index's view of the document, not the original file. The demo does not ship the full corpus, so this shows the shape of the response.`,
      },
    ],
    truncated: false,
  }
}

// --- Public: projects ------------------------------------------------------

export async function listProjects() {
  await sleep(60)
  return { projects: projects.map(projectRecord) }
}

export async function getProject(projectId) {
  await sleep(40)
  const project = projects.find((p) => p.id === projectId)
  if (!project) throw new Error('Project not found')
  return projectRecord(project)
}

export async function createProject({ name, description = '', category = '', source_category = 'documents' }) {
  const project = {
    id: nextId('proj'),
    name: name || 'Untitled project',
    description,
    category: category || 'General',
    cover: 'slate',
    source_category,
    created_at: now(),
    updated_at: now(),
    last_opened_at: now(),
    tool_source_id: '',
    source_ids: [],
  }
  projects = [project, ...projects]
  return projectRecord(project)
}

export async function updateProject(projectId, payload) {
  const project = projects.find((p) => p.id === projectId)
  if (!project) throw new Error('Project not found')
  Object.assign(project, payload, { updated_at: now() })
  return projectRecord(project)
}

export async function deleteProject(projectId) {
  projects = projects.filter((p) => p.id !== projectId)
  sessions = sessions.filter((s) => s.project_id !== projectId)
  return null
}

export async function touchProject(projectId) {
  const project = projects.find((p) => p.id === projectId)
  if (!project) throw new Error('Project not found')
  project.last_opened_at = now()
  return projectRecord(project)
}

export async function attachSourceToProject(projectId, sourceId) {
  const project = projects.find((p) => p.id === projectId)
  if (!project) throw new Error('Project not found')
  if (!project.source_ids.includes(sourceId)) project.source_ids.push(sourceId)
  return projectRecord(project)
}

export async function detachSourceFromProject(projectId, sourceId) {
  const project = projects.find((p) => p.id === projectId)
  if (!project) throw new Error('Project not found')
  project.source_ids = project.source_ids.filter((id) => id !== sourceId)
  return projectRecord(project)
}

export async function setProjectToolSource(projectId, sourceId) {
  const project = projects.find((p) => p.id === projectId)
  if (!project) throw new Error('Project not found')
  project.tool_source_id = sourceId || ''
  return projectRecord(project)
}

// --- Public: ingestion (dummy) --------------------------------------------
// The static demo cannot fetch, chunk, embed or index. Rather than fail with a
// network error, these return a well-formed payload that names the limitation.

export async function ingestSource() {
  await sleep(400)
  throw new Error(
    'Ingestion is disabled in the static demo — there is no backend on Cloudflare Pages to fetch, chunk and embed a source. The seeded projects show pre-indexed sources.',
  )
}

export async function ingestGithub() {
  return ingestSource()
}

export async function ingestFile() {
  return ingestSource()
}

export async function deleteSource() {
  await sleep(80)
  return null
}

export async function updateSourceTitle(sourceId, title) {
  const source = sources.find((s) => s.source_id === sourceId)
  if (source) source.title = title
  await sleep(60)
  return { source_id: sourceId, title }
}

// --- Public: context estimation -------------------------------------------
// The meter calls this on every selection change. It MUST stay cheap and never
// throw, mirroring the real server's free, no-model-call estimator.

export async function estimateContext(sourceIds = [], depth = 'balanced') {
  await sleep(30)
  const selected = sourceIds && sourceIds.length ? sourceIds : sources.map((s) => s.source_id)

  const DEPTH = {
    focused: { max_sources: 2, retrieved: 20, reranked: 5, per_source: 4 },
    balanced: { max_sources: 6, retrieved: 40, reranked: 12, per_source: 6 },
    broad: { max_sources: 25, retrieved: 80, reranked: 25, per_source: 10 },
  }
  const limits = DEPTH[depth] || DEPTH.balanced

  // Tokens available across the selection, then how much of it the depth will
  // actually read. The gap between the two is the point of the meter.
  const available = selected.reduce((sum, id) => {
    const source = sources.find((s) => s.source_id === id)
    return sum + (source ? source.chunks * 420 : 1200)
  }, 0)

  const effectiveSources = selected.slice(0, limits.max_sources)
  const budget = 8000
  const selectedTokens = Math.min(available, budget)
  const reduction =
    effectiveSources.length < selected.length || available > budget
      ? {
          applied: true,
          reason: `This selection is wider than the ${depth} depth reads; it was narrowed to ${effectiveSources.length} source${effectiveSources.length === 1 ? '' : 's'} within the prompt budget.`,
        }
      : { applied: false, reason: null }

  return {
    depth,
    limits: {
      max_sources: limits.max_sources,
      retrieved: limits.retrieved,
      reranked: limits.reranked,
      per_source_cap: limits.per_source,
    },
    selected_sources: selected,
    effective_sources: effectiveSources,
    missing_sources: selected.filter((id) => !sources.some((s) => s.source_id === id)),
    available_tokens: available,
    selected_tokens: selectedTokens,
    prompt_budget: budget,
    reduction,
  }
}

// --- Public: chat sessions -------------------------------------------------

export async function listChatSessions(projectId) {
  await sleep(60)
  return {
    sessions: sessions
      .filter((s) => s.project_id === projectId)
      .map(sessionRecord),
  }
}

export async function createChatSession(projectId, { title = '' } = {}) {
  const session = {
    id: nextId('chat'),
    project_id: projectId,
    title,
    created_at: now(),
    updated_at: now(),
    messages: [],
  }
  sessions = [...sessions, session]
  return sessionRecord(session)
}

export async function getChatSession(sessionId) {
  await sleep(40)
  const session = sessions.find((s) => s.id === sessionId)
  if (!session) throw new Error('Session not found')
  return { ...sessionRecord(session), messages: (session.messages || []).map(messageRecord) }
}

export async function renameChatSession(sessionId, title) {
  const session = sessions.find((s) => s.id === sessionId)
  if (!session) throw new Error('Session not found')
  session.title = title
  return sessionRecord(session)
}

export async function deleteChatSession(sessionId) {
  sessions = sessions.filter((s) => s.id !== sessionId)
  return null
}

export async function listChatMessages(sessionId) {
  const session = sessions.find((s) => s.id === sessionId)
  return { messages: (session?.messages || []).map(messageRecord) }
}

export async function addChatMessage(sessionId, payload) {
  const session = sessions.find((s) => s.id === sessionId)
  if (!session) throw new Error('Session not found')
  const message = {
    id: nextId('msg'),
    role: payload.role || 'user',
    text: payload.text || '',
    status: payload.status || 'done',
    sourceIds: payload.sourceIds || payload.source_ids || [],
    confidence: payload.confidence || null,
    created_at: now(),
  }
  session.messages = [...(session.messages || []), message]
  session.updated_at = now()
  return messageRecord(message)
}

export async function updateChatMessage(messageId, payload) {
  for (const session of sessions) {
    const message = (session.messages || []).find((m) => m.id === messageId)
    if (message) {
      Object.assign(message, payload)
      return messageRecord(message)
    }
  }
  return null
}

// --- Public: the answer stream --------------------------------------------
// Chooses which captured conversation answers a question, then emits the exact
// Server-Sent Events the real `/query/stream` sends: a [STATUS] while retrieval
// runs, a [STATUS] while generating, [TOK] text frames, then [SOURCES],
// [LATENCY], [CONFIDENCE] and [DONE]. Reproducing the wire format means
// `useChat` and `ChatBox` need no demo-specific code.

function pickAnswer(question, sourceIds = []) {
  const q = (question || '').toLowerCase()

  // Prefer a seed answer whose source is in the current selection — the most
  // convincing match is "the answer that came from the sources you have picked".
  const candidates = []
  for (const matcher of DEMO_MATCHERS) {
    const session = sessions.find((s) => s.id === matcher.sessionId) || DEMO_SESSIONS.find((s) => s.id === matcher.sessionId)
    if (!session) continue
    const hits = matcher.keywords.filter((k) => q.includes(k)).length
    const sourceOverlap = (session.messages?.[1]?.sourceIds || []).some((id) => sourceIds.includes(id))
    candidates.push({ session, score: hits + (sourceOverlap ? 2 : 0) })
  }

  candidates.sort((a, b) => b.score - a.score)
  const best = candidates[0]
  if (best && best.score > 0) {
    const answer = best.session.messages?.find((m) => m.role === 'assistant')
    if (answer) {
      return {
        text: answer.text,
        confidence: answer.confidence,
        latency: answer.latency,
        sourceIds: answer.sourceIds,
        sources: answer.sources,
      }
    }
  }

  return {
    text: DEMO_FALLBACK.text,
    confidence: DEMO_FALLBACK.confidence,
    latency: DEMO_FALLBACK.latency,
    sourceIds: [],
    sources: [],
  }
}

export async function streamQuery(payload = {}, handlers = {}) {
  const question = payload.question || payload.query || ''
  const sourceIds = payload.source_ids || payload.sourceIds || []
  const answer = pickAnswer(question, sourceIds)

  const status = (label) => handlers.onStatus && handlers.onStatus(label)
  const token = (text) => handlers.onToken && handlers.onToken(text)
  const abortSignal = handlers.signal

  const aborted = () => abortSignal && abortSignal.aborted

  // Stage 1 — retrieval. The real server sends this before any token exists so
  // the bubble can say what it is doing.
  status('Searching your sources…')
  await sleep(650)
  if (aborted()) return

  if (handlers.onLatency) handlers.onLatency(answer.latency || {})
  if (handlers.onSources && answer.sources) handlers.onSources(answer.sources)

  // Stage 2 — generation. Emit the answer in word-sized chunks so the stream
  // reads like a model writing, not a paste.
  status('Reading them and composing an answer…')
  const words = answer.text.split(/(\s+)/)
  let emitted = ''
  for (let i = 0; i < words.length; i++) {
    if (aborted()) return
    emitted += words[i]
    // Flush on a short cadence rather than per word, so very long answers do
    // not fire thousands of setState calls.
    if (i % 3 === 0 || i === words.length - 1) {
      token(emitted)
      emitted = ''
      await sleep(12)
    }
  }

  if (aborted()) return

  if (handlers.onConfidence) handlers.onConfidence(answer.confidence || null)
  if (handlers.onDone) handlers.onDone()
}

// A non-streaming answer, shaped like `GET /query`.
export async function queryAnswer(payload = {}) {
  const answer = pickAnswer(payload.question || payload.query || '', payload.source_ids || [])
  return {
    answer: answer.text,
    sources: answer.sources || [],
    confidence: answer.confidence,
    latency: answer.latency,
  }
}

// --- Public: notes, mind maps, studio -------------------------------------
// These are part of the real product but are not the focus of the demo. They
// return honest, well-formed "not in the demo" payloads so any panel that opens
// shows a clear message instead of a network error.

function demoUnavailable(feature) {
  return {
    available: false,
    demo: true,
    message: `${feature} is disabled in the static demo. It runs against the full backend on your own machine.`,
  }
}

export async function createMindMap() {
  await sleep(300)
  return demoUnavailable('Mind map generation')
}

export async function getMindMap() {
  return null
}

export async function createNote() {
  await sleep(300)
  return demoUnavailable('Note generation')
}

export async function getNote() {
  return null
}

export async function getArchitecture() {
  return demoUnavailable('Architecture analysis')
}
export async function streamArchitecture(payload, handlers = {}) {
  if (handlers.onError) handlers.onError('Architecture analysis is disabled in the static demo.')
  if (handlers.onDone) handlers.onDone()
}
export async function regenerateArchitecture() {
  return demoUnavailable('Architecture analysis')
}
export async function getTechStack() {
  return demoUnavailable('Tech stack scan')
}
export async function scanTechStack() {
  return demoUnavailable('Tech stack scan')
}
export async function getSecurityScan() {
  return demoUnavailable('Security scan')
}
export async function scanSecurity() {
  return demoUnavailable('Security scan')
}
export async function getHealthScan() {
  return demoUnavailable('Health scan')
}
export async function scanHealth() {
  return demoUnavailable('Health scan')
}

// --- Public: model hub -----------------------------------------------------
// Shown as configured so the Model Hub reads sensibly, but keys are never
// present and changes do not persist beyond the tab.

let demoModels = [
  {
    id: 'model_demo_embed',
    name: 'Local embedder (BAAI/bge-base-en-v1.5)',
    kind: 'embedding',
    provider: 'local',
    runtime: 'local',
    model: 'BAAI/bge-base-en-v1.5',
    dimension: 768,
    has_api_key: false,
  },
  {
    id: 'model_demo_chat',
    name: 'Gemini Flash',
    kind: 'llm',
    provider: 'gemini',
    runtime: 'api',
    model: 'gemini-flash-latest',
    has_api_key: false,
  },
]

export async function listModels() {
  await sleep(50)
  return { models: clone(demoModels) }
}
export async function createModel(payload) {
  const model = { id: nextId('model'), ...payload, has_api_key: Boolean(payload.api_key) }
  demoModels = [model, ...demoModels]
  return model
}
export async function updateModel(modelId, payload) {
  const model = demoModels.find((m) => m.id === modelId)
  if (model) Object.assign(model, payload)
  return model || null
}
export async function deleteModel(modelId) {
  demoModels = demoModels.filter((m) => m.id !== modelId)
  return null
}
export async function testModel() {
  await sleep(400)
  return { ok: true, message: 'Demo mode: no real provider call is made.', dimension: 768 }
}
export async function listChains() {
  return { chains: [] }
}
export async function createChain(payload) {
  return { id: nextId('chain'), ...payload, members: payload.members || [] }
}
export async function updateChain(chainId, payload) {
  return { id: chainId, ...payload }
}
export async function deleteChain() {
  return null
}
export async function testChain() {
  await sleep(400)
  return { ok: true, message: 'Demo mode: no real provider call is made.' }
}
export async function getServing() {
  return { mode: 'model', model_id: 'model_demo_chat', chain_id: '' }
}
export async function updateServing(payload) {
  return payload
}
