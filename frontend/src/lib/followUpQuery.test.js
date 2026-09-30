import { describe, it, expect } from 'vitest'

import { isUnderspecified, resolveFollowUpQuery } from './followUpQuery'

// A user message, a reply, then a follow-up that names nothing.
function thread(...turns) {
  return turns.map((text, i) => ({ id: `m${i}`, role: i % 2 === 0 ? 'user' : 'assistant', text }))
}

describe('isUnderspecified', () => {
  it('flags a question built on a pronoun with no subject', () => {
    // The exact question that produced a 15% confidence score in the app.
    expect(isUnderspecified('give me details about it')).toBe(true)
    expect(isUnderspecified('tell me about it')).toBe(true)
    expect(isUnderspecified('more about that')).toBe(true)
    expect(isUnderspecified('summarize them')).toBe(true)
  })

  it('leaves a question that names its own subject alone', () => {
    // Rewriting these would corrupt a query that already works.
    expect(isUnderspecified('what did JUST do in 2008')).toBe(false)
    expect(isUnderspecified('who is the vice chancellor')).toBe(false)
    expect(isUnderspecified('tell me about the university')).toBe(false)
  })

  it('leaves a long question alone even when it contains a pronoun', () => {
    // "that" here is ordinary relative-clause usage, not a bare reference.
    expect(isUnderspecified('what are the admission requirements for engineering')).toBe(false)
  })

  it('handles blank input without claiming it needs a subject', () => {
    expect(isUnderspecified('')).toBe(false)
    expect(isUnderspecified('   ')).toBe(false)
    expect(isUnderspecified('?!')).toBe(false)
  })

  it('does not treat a Bengali question as underspecified', () => {
    // Bengali tokens must survive tokenization, or every Bengali follow-up
    // would be rewritten as if it had no subject.
    expect(isUnderspecified('এটা সম্পর্কে আরও বিস্তারিত বলুন')).toBe(false)
  })
})

describe('resolveFollowUpQuery', () => {
  it('carries the previous turn subject into the retrieval query', () => {
    const resolved = resolveFollowUpQuery('give me details about it', {
      messages: thread('Jashore University of Science and Technology', 'It is a public university in Bangladesh.'),
    })

    expect(resolved.rewritten).toBe(true)
    expect(resolved.reason).toBe('followed-up-question')
    // The subject leads, so it dominates both the keyword and vector legs.
    expect(resolved.question).toContain('jashore')
    // The user's own words are retained, not replaced.
    expect(resolved.question).toContain('give me details about it')
  })

  it('resolves against the last turn that actually named a subject', () => {
    // Two vague turns in a row: the first vague follow-up must not become the
    // subject, or the query degrades into "about it — more about that".
    const resolved = resolveFollowUpQuery('what about it', {
      messages: thread(
        'Jashore University of Science and Technology',
        'It opened in 2008.',
        'tell me about it',
        'It is in Jashore.',
      ),
    })

    expect(resolved.question).toContain('jashore')
    expect(resolved.question).not.toContain('tell me about it')
  })

  it('falls back to a single selected source title', () => {
    const resolved = resolveFollowUpQuery('summarize it', {
      messages: [],
      sourceTitles: ['যশোর বিজ্ঞান ও প্রযুক্তি বিশ্ববিদ্যালয়'],
    })

    expect(resolved.rewritten).toBe(true)
    expect(resolved.reason).toBe('single-source')
    expect(resolved.question).toContain('বিশ্ববিদ্যালয়')
  })

  it('does not guess when several sources are selected', () => {
    // "it" does not say which of them is meant, so inventing a subject would
    // silently answer about the wrong document.
    const resolved = resolveFollowUpQuery('summarize it', {
      messages: [],
      sourceTitles: ['JUST', 'MBSTU'],
    })

    expect(resolved.rewritten).toBe(false)
    expect(resolved.question).toBe('summarize it')
    expect(resolved.reason).toBeNull()
  })

  it('sends the question unchanged when there is no context to use', () => {
    const resolved = resolveFollowUpQuery('give me details about it', { messages: [], sourceTitles: [] })

    expect(resolved.rewritten).toBe(false)
    expect(resolved.question).toBe('give me details about it')
  })

  it('leaves a self-contained question untouched even mid-thread', () => {
    const resolved = resolveFollowUpQuery('When did JUST open?', {
      messages: thread('tell me about the university'),
    })

    expect(resolved.rewritten).toBe(false)
    expect(resolved.question).toBe('When did JUST open?')
  })

  it('caps a very long subject so the query stays readable', () => {
    const longSubject = Array.from({ length: 40 }, (_, i) => `word${i}`).join(' ')
    const resolved = resolveFollowUpQuery('tell me about it', {
      messages: thread(longSubject),
    })

    expect(resolved.question.split(' ').length).toBeLessThan(20)
  })

  it('survives missing and malformed context', () => {
    expect(resolveFollowUpQuery('tell me about it').rewritten).toBe(false)
    expect(resolveFollowUpQuery('tell me about it', { messages: null }).rewritten).toBe(false)
    expect(resolveFollowUpQuery('', {}).question).toBe('')
  })
})
