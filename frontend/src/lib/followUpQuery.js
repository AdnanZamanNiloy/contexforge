// Makes a follow-up question self-contained before it reaches retrieval.
//
// A question like "give me details about it" contains no searchable topic: the
// only content word is a pronoun. Sent as-is, the retriever matches it against
// the corpus essentially at random, the cross-encoder scores the chunks it
// happens to get near zero, and the UI reports a 15% confidence that looks like
// a broken tool rather than an under-specified question. The user has to guess
// that rephrasing would help.
//
// The history already holds the subject — the previous turn named it — so the
// fix is to carry that subject forward into the retrieval query. The text the
// user typed is still what gets displayed and persisted; only the string sent
// for retrieval is expanded, which is what search engines have always done.

// Words that carry no topic of their own. Stripping these leaves the question's
// actual subject, if it names one.
const STOP_WORDS = new Set([
  'a', 'an', 'the', 'and', 'or', 'but', 'of', 'in', 'on', 'at', 'to', 'for', 'from', 'by',
  'with', 'about', 'into', 'over', 'is', 'are', 'was', 'were', 'be', 'been', 'am',
  'me', 'my', 'i', 'you', 'your', 'we', 'our', 'us', 'please', 'can', 'could',
  'would', 'will', 'shall', 'should', 'may', 'might', 'must', 'do', 'does', 'did',
  'there', 'here', 'that', 'this',
  // Interrogatives ask *for* a subject without supplying one, so "what about
  // it" carries no more topic than "tell me about it" does.
  'what', 'whats', 'when', 'where', 'who', 'whom', 'whose', 'which', 'why', 'how',
])

// Verbs and nouns that describe the *shape* of the request rather than its
// subject. "give me details about it" is entirely these plus a pronoun.
const INTENT_WORDS = new Set([
  'tell', 'show', 'give', 'explain', 'describe', 'summarize', 'summarise',
  'details', 'detail', 'more', 'info', 'information', 'know', 'say', 'elaborate',
  'expand', 'brief', 'short', 'long', 'quick', 'again', 'go', 'on',
  'continue', 'list', 'find', 'search', 'get', 'make', 'write', 'provide',
])

// Pronouns that refer back to something already mentioned. Their presence with
// no other topic word is the signal that the question needs a subject.
const PRONOUNS = new Set([
  'it', 'its', 'this', 'that', 'these', 'those', 'them', 'they', 'their',
  'he', 'him', 'his', 'she', 'her', 'hers',
])

// Above this length a question almost always names its own subject, so it is
// left untouched rather than risk a bad rewrite.
const MAX_QUESTION_WORDS = 7

// The topic is capped so a long previous question does not become a keyword
// salad; the leading clause is what carries the subject.
const MAX_TOPIC_WORDS = 12

const TOKEN_SPLIT = /[^0-9A-Za-z\u0980-\u09ff']+/

function tokenize(text) {
  return String(text || '')
    .toLowerCase()
    .split(TOKEN_SPLIT)
    .filter(Boolean)
}

/** The words of a question that could plausibly name a subject. */
function contentWords(text) {
  return tokenize(text).filter(
    (w) => !STOP_WORDS.has(w) && !INTENT_WORDS.has(w) && !PRONOUNS.has(w),
  )
}

/**
 * Whether a question refers to a subject instead of naming one.
 *
 * Both conditions must hold: a back-referring pronoun has to be present, and
 * nothing else in the question can stand in for a subject. A question that
 * says "what did the university do in 2008" has a pronoun-free subject and is
 * returned as-is.
 */
export function isUnderspecified(question) {
  const words = tokenize(question)
  if (words.length === 0 || words.length > MAX_QUESTION_WORDS) {
    return false
  }
  if (!words.some((w) => PRONOUNS.has(w))) {
    return false
  }
  return contentWords(question).length === 0
}

/**
 * The subject of the most recent turn that actually named one.
 *
 * Walks backwards past the assistant's replies and past any follow-up that was
 * itself underspecified, so two vague turns in a row still resolve against the
 * real subject rather than against "it".
 */
function subjectFromHistory(messages) {
  if (!Array.isArray(messages)) {
    return ''
  }
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i]
    if (!message || message.role !== 'user' || !message.text) {
      continue
    }
    const subject = contentWords(message.text)
    if (subject.length) {
      return subject.slice(0, MAX_TOPIC_WORDS).join(' ')
    }
  }
  return ''
}

/**
 * Build a retrieval query that stands on its own.
 *
 * Resolution order, most to least trustworthy:
 *   1. The subject of the last turn that named one.
 *   2. The title of a single selected source, when exactly one is in scope —
 *      "tell me about it" after selecting one document means that document.
 *   3. Nothing, in which case the question is sent unchanged. Guessing here
 *      would be worse than letting the low confidence surface the problem.
 *
 * @param {string} question  What the user typed.
 * @param {object} [context]
 * @param {Array}  [context.messages]    Prior turns, oldest first.
 * @param {Array}  [context.sourceTitles] Titles of the selected sources.
 * @returns {{question: string, rewritten: boolean, reason: string|null}}
 */
export function resolveFollowUpQuery(question, { messages = [], sourceTitles = [] } = {}) {
  const original = String(question || '').trim()
  if (!original || !isUnderspecified(original)) {
    return { question: original, rewritten: false, reason: null }
  }

  const fromHistory = subjectFromHistory(messages)
  const titles = (Array.isArray(sourceTitles) ? sourceTitles : [])
    .map((t) => String(t || '').trim())
    .filter(Boolean)

  // One selected source is a reliable referent; several are not, since "it"
  // does not say which of them is meant.
  const fromSource = titles.length === 1 ? contentWords(titles[0]).slice(0, MAX_TOPIC_WORDS).join(' ') : ''

  const subject = fromHistory || fromSource
  if (!subject) {
    return { question: original, rewritten: false, reason: null }
  }

  return {
    question: `${subject} — ${original}`,
    rewritten: true,
    reason: fromHistory ? 'followed-up-question' : 'single-source',
  }
}
