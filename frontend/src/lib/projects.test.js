import { describe, it, expect } from 'vitest'

import {
  filterProjects,
  sortProjects,
  timeAgo,
  coverForId,
  ingestScopeFor,
  sidebarTypesFor,
  sourceCategoryLabel,
  SOURCE_CATEGORIES,
} from './projects'

describe('projects lib', () => {
  it('sorts by recency, name, and source count', () => {
    const projects = [
      {
        id: 'a',
        name: 'Zebra',
        source_count: 2,
        last_opened_at: '2026-01-01T00:00:00Z',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
      {
        id: 'b',
        name: 'Alpha',
        source_count: 9,
        last_opened_at: '2026-09-01T00:00:00Z',
        created_at: '2026-09-01T00:00:00Z',
        updated_at: '2026-09-01T00:00:00Z',
      },
    ]
    expect(sortProjects(projects, 'name')[0].id).toBe('b')
    expect(sortProjects(projects, 'sources')[0].id).toBe('b')
    expect(sortProjects(projects, 'recent')[0].id).toBe('b')
  })

  it('filters by query across name, description, and category', () => {
    const projects = [
      { id: 'a', name: 'AI Research', description: 'agents', category: 'Research' },
      { id: 'b', name: 'Crypto', description: 'ciphers', category: 'Study' },
    ]
    expect(filterProjects(projects, { query: 'agent' })).toHaveLength(1)
    expect(filterProjects(projects, { query: 'crypto' })[0].id).toBe('b')
    expect(filterProjects(projects, { query: '', category: 'Study' })[0].id).toBe('b')
    expect(filterProjects(projects, { query: 'nope' })).toHaveLength(0)
  })

  it('formats relative timestamps without crashing on bad input', () => {
    expect(timeAgo(null)).toBe('Never opened')
    expect(timeAgo('not-a-date')).toBe('Unknown')
    expect(timeAgo(new Date().toISOString())).toMatch(/just now|minute/)
  })

  it('maps ids to a stable cover token', () => {
    expect(coverForId('proj_abc')).toBe(coverForId('proj_abc'))
  })

  it('offers exactly the three source families', () => {
    expect(SOURCE_CATEGORIES.map((c) => c.id)).toEqual(['documents', 'youtube', 'github'])
    expect(sourceCategoryLabel('youtube')).toBe('YouTube Videos')
    expect(sourceCategoryLabel('nope')).toBe('Documents & Web')
  })

  it('scopes workspace ingest options per family, legacy keeps all', () => {
    expect(ingestScopeFor('documents')).toEqual(['files', 'web', 'text'])
    expect(ingestScopeFor('youtube')).toEqual(['youtube'])
    expect(ingestScopeFor('github')).toEqual(['github'])
    expect(ingestScopeFor('all')).toEqual(['files', 'web', 'github', 'youtube', 'text'])
    expect(ingestScopeFor(undefined)).toEqual(['files', 'web', 'github', 'youtube', 'text'])
  })

  it('scopes sidebar rows per family, legacy keeps all', () => {
    expect(sidebarTypesFor('documents')).toEqual(['all', 'pdf', 'docx', 'web', 'text'])
    expect(sidebarTypesFor('youtube')).toEqual(['youtube'])
    expect(sidebarTypesFor('github')).toEqual(['github'])
    expect(sidebarTypesFor('all')).toBeNull()
    expect(sidebarTypesFor(undefined)).toBeNull()
  })
})
