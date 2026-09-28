import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  createMindMap,
  createModel,
  deleteModel,
  fetchSources,
  deleteSource,
  getServing,
  pingApi,
  testModel,
  updateModel,
  updateServing,
} from './api'

// Reads a numeric constant out of a source file so cross-file invariants are
// checked against the real values rather than restated copies of them.  Paths are
// resolved from the frontend project root, which is vitest's cwd.
const SOURCE_FILES = ['src/services/api.js', '../backend/app/mindmap/service.py']

function readInt(name) {
  for (const rel of SOURCE_FILES) {
    const text = readFileSync(resolve(process.cwd(), rel), 'utf8')
    const at = text.indexOf(name)
    if (at !== -1) {
      const value = text.slice(at + name.length).match(/^\s*([0-9_]+)/)
      if (value) return Number.parseInt(value[1].replace(/_/g, ''), 10)
    }
  }
  throw new Error(`constant ${name} not found`)
}

function mockFetch(response) {
  const fn = vi.fn(async () => response)
  vi.stubGlobal('fetch', fn)
  return fn
}

beforeEach(() => {
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchSources', () => {
  it('requests the sources endpoint and returns parsed JSON', async () => {
    const body = { sources: [] }
    const fetchMock = mockFetch({ ok: true, status: 200, json: async () => body })

    const result = await fetchSources()

    expect(result).toEqual(body)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/ingest/sources')
    expect(options.method).toBe('GET')
  })

  it('surfaces the API detail message on a non-OK response', async () => {
    mockFetch({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'boom' }),
    })

    await expect(fetchSources()).rejects.toThrow('boom')
  })
})

describe('deleteSource', () => {
  it('encodes the source id in the path', async () => {
    const fetchMock = mockFetch({ ok: true, status: 204, json: async () => null })

    await deleteSource('a/b c')

    const [url] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/ingest/source/a%2Fb%20c')
  })
})

describe('pingApi', () => {
  it('returns the parsed health payload', async () => {
    const body = { status: 'ok', service: 'contextforge' }
    const fetchMock = mockFetch({ ok: true, status: 200, json: async () => body })

    const result = await pingApi()

    expect(result).toEqual(body)
    expect(fetchMock.mock.calls[0][0]).toBe('http://localhost:8000/health')
  })
})

describe('model hub API', () => {
  it('posts a new model with the API key in the body (never the URL)', async () => {
    const fetchMock = mockFetch({ ok: true, status: 201, json: async () => ({ id: 'm1' }) })

    await createModel({ name: 'GPT', model_id: 'gpt-4o-mini', api_key: 'sk-secret' })

    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/models')
    expect(url).not.toContain('sk-secret')
    expect(options.method).toBe('POST')
    expect(JSON.parse(options.body).api_key).toBe('sk-secret')
  })

  it('tests a model by POSTing to its test endpoint', async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, json: async () => ({ ok: true }) })

    await testModel('m/1')

    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/models/m%2F1/test')
    expect(options.method).toBe('POST')
  })

  it('patches a model update', async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, json: async () => ({}) })

    await updateModel('m1', { name: 'Renamed' })

    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/models/m1')
    expect(options.method).toBe('PATCH')
  })

  it('deletes a model', async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, json: async () => ({ deleted: true }) })

    await deleteModel('m1')

    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/models/m1')
    expect(options.method).toBe('DELETE')
  })

  it('reads and updates the serving config', async () => {
    mockFetch({ ok: true, status: 200, json: async () => ({ llm_mode: 'disabled' }) })
    await getServing()

    const fetchMock = mockFetch({
      ok: true,
      status: 200,
      json: async () => ({ llm_mode: 'single' }),
    })
    await updateServing({ tier: 'llm', mode: 'single', target: 'm1' })

    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('http://localhost:8000/serving')
    expect(options.method).toBe('PUT')
    expect(JSON.parse(options.body)).toEqual({ tier: 'llm', mode: 'single', target: 'm1' })
  })
})

describe('mind map timeouts', () => {
  it('posts source_ids and carries a client timeout above the server cap', async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, json: async () => ({ markdown: '- a' }) })
    await createMindMap(['a', 'b'])

    const [, init] = fetchMock.mock.calls[0]
    const body = JSON.parse(init.body)
    expect(body.source_ids).toEqual(['a', 'b'])

    // The real invariant, read from both source files: the client window must
    // exceed the server's cap, or the browser aborts first and the user sees an
    // opaque network error instead of the server's clear timeout message.
    const clientWindowMs = readInt('MIND_MAP_TIMEOUT_MS = ')
    const serverCapMs = readInt('MAX_GENERATION_SECONDS = ') * 1000
    expect(clientWindowMs).toBeGreaterThan(serverCapMs)
  })

  it('uses source_id for a single source so the cached entry stays addressable', async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, json: async () => ({ markdown: '- a' }) })
    await createMindMap('a')
    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse(init.body).source_id).toBe('a')
  })

  it('forwards refresh so a changed selection can be regenerated', async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, json: async () => ({ markdown: '- a' }) })
    await createMindMap(['a'], { refresh: true })
    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse(init.body).refresh).toBe(true)
  })

  it('does not leak the internal timeoutMs option into fetch', async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, json: async () => ({ markdown: '- a' }) })
    await createMindMap(['a'])
    const [, init] = fetchMock.mock.calls[0]
    // It is consumed by request(), never forwarded to the network layer.
    expect(init).not.toHaveProperty('timeoutMs')
  })
})
