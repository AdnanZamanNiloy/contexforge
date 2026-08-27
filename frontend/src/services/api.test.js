import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fetchSources, deleteSource, pingApi } from './api'

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
