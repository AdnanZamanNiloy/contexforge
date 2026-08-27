import { describe, it, expect } from 'vitest'
import {
  formatFileSize,
  formatSourceMeta,
  formatTypeLabel,
  normalizeSource,
  sourceRepoUrl,
  extractDomain,
} from './sources'

describe('formatFileSize', () => {
  it('returns 0 KB for a falsy size', () => {
    expect(formatFileSize(0)).toBe('0 KB')
    expect(formatFileSize(undefined)).toBe('0 KB')
  })

  it('formats bytes, KB and MB', () => {
    expect(formatFileSize(512)).toBe('512 B')
    expect(formatFileSize(2048)).toBe('2.0 KB')
    expect(formatFileSize(2 * 1024 * 1024)).toBe('2.0 MB')
  })
})

describe('formatSourceMeta', () => {
  it('renders PDF/DOCX with size', () => {
    expect(formatSourceMeta({ type: 'pdf', size: 2048 })).toBe('PDF • 2.0 KB')
  })

  it('renders web with an optional date', () => {
    expect(formatSourceMeta({ type: 'web', date: undefined })).toBe('Web • ')
  })

  it('renders github with a file count', () => {
    expect(formatSourceMeta({ type: 'github', chunks: 5 })).toBe('GitHub Repo • 5 files')
  })

  it('renders youtube with an author', () => {
    expect(formatSourceMeta({ type: 'youtube', author: 'Adnan' })).toBe('YouTube • Adnan')
  })

  it('falls back to a count for other types', () => {
    expect(formatSourceMeta({ type: 'text', chunks: 3 })).toBe('TEXT • 3 items')
  })
})

describe('formatTypeLabel', () => {
  it('maps known types and uppercases unknown ones', () => {
    expect(formatTypeLabel('pdf')).toBe('PDF')
    expect(formatTypeLabel('youtube')).toBe('YouTube')
    expect(formatTypeLabel('banana')).toBe('BANANA')
    expect(formatTypeLabel(undefined)).toBe('SOURCE')
  })
})

describe('normalizeSource', () => {
  it('normalises a raw API record', () => {
    const raw = { source_id: 's1', type: 'pdf', title: 'Doc', chunks: 4 }
    expect(normalizeSource(raw)).toEqual({
      id: 's1',
      type: 'pdf',
      title: 'Doc',
      status: 'indexed',
      chunks: 4,
      url: '',
      meta: {},
    })
  })

  it('provides a fallback title when missing', () => {
    const normalized = normalizeSource({ source_id: 'abc', type: 'web' })
    expect(normalized.title).toBe('abc')
  })
})

describe('sourceRepoUrl', () => {
  it('prefers an explicit url', () => {
    expect(sourceRepoUrl({ type: 'github', url: 'https://github.com/o/r' })).toBe(
      'https://github.com/o/r',
    )
  })

  it('recovers the URL from an owner/repo title', () => {
    expect(sourceRepoUrl({ type: 'github', title: 'owner/repo' })).toBe(
      'https://github.com/owner/repo',
    )
  })

  it('returns empty for non-GitHub or unparseable titles', () => {
    expect(sourceRepoUrl({ type: 'pdf' })).toBe('')
    expect(sourceRepoUrl({ type: 'github', title: 'no-slash' })).toBe('')
  })
})

describe('extractDomain', () => {
  it('strips the scheme and www prefix', () => {
    expect(extractDomain('https://www.example.com/path')).toBe('example.com')
  })

  it('returns null for invalid urls', () => {
    expect(extractDomain('not a url')).toBe(null)
    expect(extractDomain('')).toBe(null)
  })
})
