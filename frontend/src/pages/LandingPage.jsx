import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import ContextForgeMark from '../components/ContextForgeMark'

// ---------------------------------------------------------------------------
// ContextForge landing page.
//
// Design direction (see LANDING_PRODUCT.md): technical editorial, dark, calm.
// The memorable detail is a live retrieval-trace hero that animates the real
// query pipeline (HyDE → Hybrid → RRF → Rerank → Prompt → LLM) and streams a
// grounded, cited answer. Everything else is inspectable product substance —
// no decorative filler, no stock imagery, no gradient-blob hero.
//
// All motion is driven by one IntersectionObserver reveal + one rAF-free
// interval clock so the page stays cheap and respects reduced-motion.
// ---------------------------------------------------------------------------

// The five stages the backend actually reports timings for.  The rail used to
// show six (HyDE, Hybrid, RRF, Rerank, Prompt, LLM) and the caption claimed it
// was "the same six stages the backend runs".  It was not: hybrid search and RRF
// fusion are a single `retrieve_ms` bucket, prompt assembly has no timing key at
// all, and query embedding (`embed_ms`) was missing from the rail entirely.
// These five match the keys returned in `latency_ms`.
const PIPELINE = [
  { key: 'hyde', label: 'HyDE', detail: 'hypothetical passage', ms: 420 },
  { key: 'embed', label: 'Embed', detail: 'query vector', ms: 240 },
  { key: 'retrieve', label: 'Hybrid', detail: 'BM25 ⊕ dense, RRF fused', ms: 380 },
  { key: 'rerank', label: 'Rerank', detail: 'cross-encoder', ms: 460 },
  { key: 'generate', label: 'Generate', detail: 'grounded answer', ms: 520 },
]

const ANSWER_TOKENS = [
  'ContextForge',
  'fuses',
  'BM25',
  'and',
  'dense',
  'retrieval',
  'with',
  'reciprocal',
  'rank',
  'fusion,',
  'then',
  'sharpens',
  'the',
  'shortlist',
  'with',
  'a',
  'cross-encoder',
  'reranker',
  'before',
  'generation.',
]

// Kept short: the shared `core/retrieval/` prefix is stated once in the label so
// the three chips sit on a single row inside the compact hero window.  These are
// the retrieved passages with their scores — the evidence rail the client
// actually renders — not inline `[n]` markers, which ship disabled.
const CITATIONS = [
  { n: 1, label: 'retrieval/hybrid.py', score: '0.87' },
  { n: 2, label: 'retrieval/rrf.py', score: '0.81' },
  { n: 3, label: 'retrieval/reranker.py', score: '0.78' },
]

const SOURCE_KINDS = [
  { id: 'pdf', name: 'PDF', note: 'pypdf' },
  { id: 'docx', name: 'Word', note: 'python-docx' },
  { id: 'web', name: 'Web', note: 'trafilatura' },
  { id: 'youtube', name: 'YouTube', note: 'transcript-api' },
  { id: 'github', name: 'GitHub', note: 'REST + AST' },
  { id: 'text', name: 'Text', note: 'raw loader' },
]

const CAPABILITIES = [
  {
    tag: 'Retrieval',
    title: 'Hybrid search, fused and reranked',
    body: 'BM25 (SQLite FTS5) and FAISS dense vectors run in parallel, merge through Reciprocal Rank Fusion, then pass a cross-encoder reranker before the prompt is built.',
    facts: [
      ['Vector store', 'FAISS IndexFlatIP'],
      ['Sparse index', 'SQLite FTS5 · BM25'],
      ['Reranker', 'ms-marco-MiniLM-L-6-v2'],
    ],
  },
  {
    tag: 'Answer delivery',
    title: 'Grounded, streamed, inspectable',
    body: 'Tokens stream over Server-Sent Events, and every response carries the retrieved passages with their scores, per-stage latency, and server-side confidence for source coverage.',
    facts: [
      ['Transport', 'SSE token streaming'],
      ['Evidence', 'passages + relevance scores'],
      ['Metrics', 'confidence · latency'],
    ],
  },
  {
    tag: 'Serving',
    title: 'You choose what runs',
    body: 'There is no built-in provider order. You register models in the Model Hub, then serve a single one or an ordered fallback chain. A provider returning 429 is put in cooldown and the next one answers.',
    facts: [
      ['Targets', '9 hosted + any local server'],
      ['Selection', 'single model or chain'],
      ['Keys at rest', 'Fernet-encrypted'],
    ],
  },
]

// The workspace is what the product became after the retrieval pipeline was
// finished.  Everything here is a shipped feature with a route behind it; the
// landing page used to describe a RAG pipeline and said nothing about the
// application built on top of it.
const WORKSPACE = [
  {
    tag: 'Projects',
    title: 'Separate spaces, not one pile',
    body: 'Every project keeps its own sources, its own chat history and its own analysis target. Membership is reconciled against the live index, so a deleted source cannot linger in a project.',
  },
  {
    tag: 'Notes',
    title: 'Turn a selection into a note',
    body: 'Pick one source or several and the system writes a structured Markdown note from their indexed content, cached per selection, regenerable on demand, downloadable as a file.',
  },
  {
    tag: 'Mind maps',
    title: 'The same selection, drawn',
    body: 'A selection also renders as a bounded mind map: a nested outline the canvas draws directly, generated once and reused until the selection changes.',
  },
  {
    tag: 'Studio',
    title: 'Four repository analyzers',
    body: 'Architecture diagram, security and quality scan, dependency and tech stack, and health score. Each targets one repository and caches against its content fingerprint.',
  },
  {
    tag: 'Context control',
    title: 'See what a selection costs',
    body: 'The sidebar prices the current selection against the prompt budget in real time. Focused, Balanced and Broad each map to concrete retrieval limits, so widening the depth does something measurable.',
  },
  {
    tag: 'Inspection',
    title: 'Confirm what was actually read',
    body: 'Every source reports an extraction verdict, because a scanned PDF and a healthy one are not the same, alongside page counts, language, file listing and the indexed chunk text itself.',
  },
]

const RETRIEVAL_STEPS = [
  ['01', 'HyDE expansion', 'Optional hypothetical passage widens recall before search begins.'],
  ['02', 'Hybrid search', 'Keyword and dense retrievers run in parallel over the same corpus.'],
  ['03', 'Rank fusion', 'RRF merges both ranked lists into one ordering without score scaling.'],
  ['04', 'Cross-encoder', 'Top candidates are rescored pairwise for true relevance.'],
  ['05', 'Grounded answer', 'Reranked chunks become a streamed answer with its evidence attached.'],
]

const STATS = [
  { value: '6', label: 'source formats', sub: 'PDF · DOCX · Web · YouTube · GitHub · Text' },
  { value: '2', label: 'retrievers fused', sub: 'BM25 ⊕ dense vectors' },
  { value: '10', label: 'LLM targets', sub: '9 hosted providers + local' },
  { value: '59', label: 'API endpoints', sub: 'one self-hosted backend' },
]

// ---------------------------------------------------------------------------

function useReveal() {
  const ref = useRef(null)
  useEffect(() => {
    const node = ref.current
    if (!node) return undefined
    if (typeof IntersectionObserver === 'undefined') {
      node.dataset.reveal = 'in'
      return undefined
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.dataset.reveal = 'in'
            observer.unobserve(entry.target)
          }
        })
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.12 },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])
  return ref
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const sync = () => setReduced(mq.matches)
    sync()
    mq.addEventListener('change', sync)
    return () => mq.removeEventListener('change', sync)
  }, [])
  return reduced
}

// The hero trace. Advances the active pipeline stage on a timer, then types the
// answer tokens, then settles on a citations bar. Restarts gently so the hero
// always has a live state without ever feeling busy.
function useRetrievalTrace(reduced) {
  const [stage, setStage] = useState(reduced ? PIPELINE.length : 0)
  const [tokens, setTokens] = useState(reduced ? ANSWER_TOKENS.length : 0)
  const [phase, setPhase] = useState(reduced ? 'done' : 'running')

  // The initial `useState` reads `reduced`, but that is still `false` on the
  // first render — the media query is only synced in an effect, one commit
  // later. So the reduced-motion branch below never ran and the hero sat on an
  // empty answer box with a permanently blinking caret for anyone who had
  // reduced motion enabled. Snap to the finished state once the flag settles.
  useEffect(() => {
    if (!reduced) return
    setStage(PIPELINE.length)
    setTokens(ANSWER_TOKENS.length)
    setPhase('done')
  }, [reduced])

  useEffect(() => {
    if (reduced) return undefined
    let cancelled = false
    const timers = []

    const runOnce = () => {
      if (cancelled) return
      setTokens(0)
      setPhase('running')
      let elapsed = 0
      PIPELINE.forEach((step, index) => {
        elapsed += step.ms
        const id = setTimeout(() => {
          if (cancelled) return
          setStage(index + 1)
        }, elapsed)
        timers.push(id)
      })
      const answerStart = elapsed + 260
      ANSWER_TOKENS.forEach((_, index) => {
        const id = setTimeout(
          () => {
            if (cancelled) return
            setTokens(index + 1)
          },
          answerStart + index * 46,
        )
        timers.push(id)
      })
      const finish = answerStart + ANSWER_TOKENS.length * 46 + 300
      const id = setTimeout(() => {
        if (cancelled) return
        setPhase('done')
      }, finish)
      timers.push(id)
      const restart = setTimeout(runOnce, finish + 5200)
      timers.push(restart)
    }

    // Kick off after a short beat; the reset lives inside the callback so the
    // effect body itself never calls setState synchronously (no cascading render).
    const kickoff = setTimeout(() => {
      if (cancelled) return
      setStage(0)
      setTokens(0)
      runOnce()
    }, 400)
    timers.push(kickoff)

    return () => {
      cancelled = true
      timers.forEach(clearTimeout)
    }
  }, [reduced])

  return { stage, tokens, phase }
}

function SectionHeading({ eyebrow, title, lede, align = 'start' }) {
  const ref = useReveal()
  return (
    <header ref={ref} className="lp-head" data-reveal="out" data-align={align}>
      <span className="lp-eyebrow">{eyebrow}</span>
      <h2 className="lp-h2">{title}</h2>
      {lede ? <p className="lp-lede">{lede}</p> : null}
    </header>
  )
}

function BrandMark({ size = 24 }) {
  return <ContextForgeMark size={size} withPlate className="lp-mark" />
}

// ---------------------------------------------------------------------------

// Canonical repo slug. It was previously written capitalised as
// `ContexForge` in every GitHub link on this page; GitHub redirects, but the
// canonical form in the README and `git remote` is lowercase.
const REPO = 'https://github.com/AdnanZamanNiloy/contexforge'
const DOCS = `${REPO}/tree/main/docs`

const NAV_LINKS = [
  { href: '#features', label: 'Features' },
  { href: '#how-it-works', label: 'How it works' },
  { href: '#quickstart', label: 'Quick start' },
]

function Nav() {
  const [open, setOpen] = useState(false)
  const panelId = 'lp-nav-menu'

  // Close on Escape and return focus to the toggle, so the disclosure is not a
  // keyboard trap once opened.
  const toggleRef = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const onKey = (event) => {
      if (event.key !== 'Escape') return
      setOpen(false)
      toggleRef.current?.focus()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <header className="lp-nav">
      <div className="lp-nav-inner">
        <Link to="/" className="lp-brand" aria-label="ContextForge home">
          <BrandMark />
          <span className="lp-brand-name">Context<span className="lp-brand-accent">Forge</span></span>
        </Link>

        <nav className="lp-nav-links" aria-label="Sections" id={panelId} data-open={open}>
          {NAV_LINKS.map((link) => (
            <a key={link.href} href={link.href} onClick={() => setOpen(false)}>
              {link.label}
            </a>
          ))}
        </nav>

        <div className="lp-nav-actions">
          <a className="lp-btn lp-btn-ghost" href={REPO} target="_blank" rel="noreferrer">
            GitHub
          </a>
          <a className="lp-btn lp-btn-ghost" href={DOCS} target="_blank" rel="noreferrer">
            Docs
          </a>
          <Link className="lp-btn lp-btn-primary" to="/projects">
            Open projects
          </Link>
          <button
            ref={toggleRef}
            type="button"
            className="lp-nav-toggle"
            aria-expanded={open}
            aria-controls={panelId}
            aria-label={open ? 'Close menu' : 'Open menu'}
            onClick={() => setOpen((value) => !value)}
          >
            <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" focusable="false">
              {open ? (
                <path
                  d="M5 5l10 10M15 5L5 15"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                />
              ) : (
                <path
                  d="M3 6h14M3 10h14M3 14h14"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                />
              )}
            </svg>
          </button>
        </div>
      </div>
    </header>
  )
}

function HudFrame({ children, rail }) {
  return (
    <figure className="lp-hud">
      <div className="lp-hud-bar">
        <span className="lp-hud-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span className="lp-hud-path">contextforge · /query/stream</span>
        <span className="lp-hud-live">
          <span className="lp-pulse" aria-hidden="true" />
          SSE
        </span>
      </div>
      {children}
      {rail ? <figcaption className="lp-hud-rail">{rail}</figcaption> : null}
    </figure>
  )
}

function RetrievalTrace() {
  const reduced = useReducedMotion()
  const { stage, tokens, phase } = useRetrievalTrace(reduced)
  const question = 'How does ContextForge rank retrieved chunks?'

  return (
    <HudFrame rail="Live trace: the same five stages, and the same timing keys, the backend reports per query.">
      <div className="lp-trace">
        <div className="lp-trace-q">
          <span className="lp-trace-role">you</span>
          <p>{question}</p>
        </div>

        <ol className="lp-rails" aria-label="Retrieval pipeline stages">
          {PIPELINE.map((step, index) => {
            const state = stage > index ? 'done' : stage === index ? 'active' : 'idle'
            return (
              <li key={step.key} className="lp-rail" data-state={state}>
                <span className="lp-rail-idx">{String(index + 1).padStart(2, '0')}</span>
                <span className="lp-rail-body">
                  <span className="lp-rail-label">{step.label}</span>
                  <span className="lp-rail-detail">{step.detail}</span>
                </span>
                <span className="lp-rail-meter" aria-hidden="true">
                  <i style={{ '--rail-ms': `${step.ms}ms` }} />
                </span>
              </li>
            )
          })}
        </ol>

        <div className="lp-answer" data-phase={phase} data-empty={tokens === 0}>
          <span className="lp-trace-role">forge</span>
          <p className="lp-answer-text">
            {ANSWER_TOKENS.slice(0, tokens).map((token, index) => (
              <span key={`${token}-${index}`}>{token} </span>
            ))}
            {phase === 'running' ? <i className="lp-caret" aria-hidden="true" /> : null}
          </p>
          <div className="lp-cites-slot" data-visible={phase === 'done'}>
            <div className="lp-cites">
              {CITATIONS.map((cite) => (
                <span key={cite.n} className="lp-cite">
                  <b>{cite.n}</b>
                  <code>{cite.label}</code>
                  <em>{cite.score}</em>
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </HudFrame>
  )
}

function Hero() {
  const ref = useReveal()
  return (
    <section className="lp-hero" aria-labelledby="lp-hero-title">
      <div ref={ref} className="lp-hero-grid" data-reveal="out">
        <div className="lp-hero-copy">
          <span className="lp-badge">
            <span className="lp-pulse" aria-hidden="true" />
            Local-first · self-hosted
          </span>
          <h1 id="lp-hero-title" className="lp-h1">
            Answers grounded in
            <span className="lp-h1-accent"> sources you control.</span>
          </h1>
          <p className="lp-hero-lede">
            ContextForge turns your PDFs, docs, web pages, YouTube videos and GitHub repositories
            into a workspace you can ask, read and analyse: hybrid retrieval, rank fusion and
            reranking underneath, projects, notes and mind maps on top.
          </p>
          <div className="lp-hero-cta">
            <Link className="lp-btn lp-btn-primary lp-btn-lg" to="/projects">
              Browse projects
            </Link>
            <a className="lp-btn lp-btn-ghost lp-btn-lg" href="#how-it-works">
              See how it works
            </a>
            {/* The About section was removed as a page section; the design
                principles it carried live in the README's Overview, so the
                hero action points there rather than at a dead anchor. */}
            <a
              className="lp-btn lp-btn-ghost lp-btn-lg"
              href={`${REPO}#design-principles`}
              target="_blank"
              rel="noreferrer"
            >
              About
            </a>
          </div>
          <ul className="lp-hero-facts">
            <li>Your documents stay on your disk</li>
            <li>You choose the model that answers</li>
            <li>MIT licensed</li>
          </ul>
        </div>
        <div className="lp-hero-visual">
          <RetrievalTrace />
        </div>
      </div>

      <ul className="lp-sources" aria-label="Supported source formats">
        {SOURCE_KINDS.map((kind) => (
          <li key={kind.id} className="lp-source">
            <span className="lp-source-name">{kind.name}</span>
            <span className="lp-source-note">{kind.note}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function StatsStrip() {
  const ref = useReveal()
  return (
    <section ref={ref} className="lp-stats" data-reveal="out" aria-label="Product by the numbers">
      {STATS.map((stat) => (
        <div key={stat.label} className="lp-stat">
          <span className="lp-stat-value">{stat.value}</span>
          <span className="lp-stat-label">{stat.label}</span>
          <span className="lp-stat-sub">{stat.sub}</span>
        </div>
      ))}
    </section>
  )
}

function PipelineSection() {
  const ref = useReveal()
  return (
    <section id="how-it-works" className="lp-section" aria-labelledby="lp-pipeline-title">
      <SectionHeading
        eyebrow="How it works"
        title="Five stages between a question and a grounded answer"
        lede="Every query walks the same path. Each stage is timed, and the timings come back with the answer."
      />
      <ol ref={ref} className="lp-steps" data-reveal="out">
        {RETRIEVAL_STEPS.map(([num, title, body]) => (
          <li key={num} className="lp-step">
            <span className="lp-step-num">{num}</span>
            <h3 className="lp-step-title">{title}</h3>
            <p className="lp-step-body">{body}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}

function CapabilitiesSection() {
  const ref = useReveal()
  return (
    <section id="capabilities" className="lp-section" aria-labelledby="lp-cap-title">
      <SectionHeading
        eyebrow="Capabilities"
        title="Built as a system, not a chat wrapper"
        lede="Each capability is a real subsystem with its own interfaces, tests, and measurable output."
      />
      <div ref={ref} className="lp-caps" data-reveal="out">
        {CAPABILITIES.map((cap) => (
          <article key={cap.tag} className="lp-cap">
            <span className="lp-cap-tag">{cap.tag}</span>
            <h3 className="lp-cap-title">{cap.title}</h3>
            <p className="lp-cap-body">{cap.body}</p>
            <dl className="lp-cap-facts">
              {cap.facts.map(([term, value]) => (
                <div key={term} className="lp-cap-fact">
                  <dt>{term}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </article>
        ))}
      </div>
    </section>
  )
}

function FeaturesSection() {
  const ref = useReveal()
  return (
    <section id="features" className="lp-section" aria-labelledby="lp-workspace-title">
      <SectionHeading
        eyebrow="Features"
        title="The part you actually use every day"
        lede="The retrieval pipeline is the foundation. These are the tools built on top of it, each one a shipped feature with an endpoint behind it."
      />
      <div ref={ref} className="lp-workspace" data-reveal="out">
        {WORKSPACE.map((item) => (
          <article key={item.tag} className="lp-ws">
            <span className="lp-ws-tag">{item.tag}</span>
            <h3 className="lp-ws-title">{item.title}</h3>
            <p className="lp-ws-body">{item.body}</p>
          </article>
        ))}
      </div>
    </section>
  )
}

// The Backend/Frontend technology tables were removed from this page; the
// README and docs/architecture.md are the better home for a stack listing, and
// a visitor deciding whether to self-host does not need it above the fold. The
// quickstart survived because a self-hosted product is unusable without it, so
// it now stands alone as a single compact step.
// Both of these are real Makefile targets. There is no bare `make dev`, so the
// two servers are listed as the separate targets the Makefile actually defines.
const QUICKSTART = [
  { cmd: 'make install', note: 'Creates backend/.venv and installs both sides.' },
  { cmd: 'make dev-backend', note: 'API on :8000.' },
  { cmd: 'make dev-frontend', note: 'UI on :5173.' },
  {
    cmd: 'Add a model in the Model Hub',
    note: 'No provider key goes in .env — the app starts without one and names the model that needs a key.',
  },
]

function QuickStartSection() {
  const ref = useReveal()
  return (
    <section id="quickstart" className="lp-section lp-section-quickstart" aria-labelledby="lp-quickstart-title">
      <SectionHeading
        eyebrow="Quick start"
        title="Clone it, run it, add a model"
        lede="No hosted vector database and no account. Three commands take you from a fresh clone to a running workspace."
      />
      <ol ref={ref} className="lp-quickstart" data-reveal="out">
        {QUICKSTART.map((step, index) => (
          <li key={step.cmd} className="lp-quickstart-step">
            <span className="lp-quickstart-num">{index + 1}</span>
            <code className="lp-quickstart-cmd">{step.cmd}</code>
            <span className="lp-quickstart-note">{step.note}</span>
          </li>
        ))}
      </ol>
    </section>
  )
}

function Footer() {
  return (
    <footer className="lp-footer">
      <div className="lp-footer-inner">
        <div className="lp-footer-brand">
          <BrandMark size={22} />
          <div>
            <strong>ContextForge</strong>
            <span>Grounded retrieval-augmented generation workspace.</span>
          </div>
        </div>
        <nav className="lp-footer-links" aria-label="Footer">
          <div className="lp-footer-col">
            <span className="lp-footer-head">Product</span>
            <Link to="/projects">Projects</Link>
            <Link to="/workspace">Workspace</Link>
            <Link to="/models">Model Hub</Link>
            <a href="#features">Features</a>
            <a href="#how-it-works">How it works</a>
            <a href="#quickstart">Quick start</a>
          </div>
          <div className="lp-footer-col">
            <span className="lp-footer-head">Documentation</span>
            <a href={REPO} target="_blank" rel="noreferrer">
              GitHub
            </a>
            <a href={DOCS} target="_blank" rel="noreferrer">
              Docs
            </a>
            <a href={`${REPO}#quick-start`} target="_blank" rel="noreferrer">
              Quick start
            </a>
            <a href={`${REPO}#architecture`} target="_blank" rel="noreferrer">
              Architecture
            </a>
          </div>
          <div className="lp-footer-col">
            <span className="lp-footer-head">License</span>
            <span className="lp-footer-note">MIT · self-hosted</span>
            <span className="lp-footer-note">Maintained by @AdnanZamanNiloy</span>
          </div>
        </nav>
      </div>
      <div className="lp-footer-base">
        <span>© {new Date().getFullYear()} ContextForge</span>
        <span className="lp-footer-mono">retrieval · fusion · reranking · citations</span>
      </div>
    </footer>
  )
}

export default function LandingPage() {
  return (
    <div className="lp-root">
      <Nav />
      <main id="top">
        <Hero />
        <StatsStrip />
        <FeaturesSection />
        <PipelineSection />
        <CapabilitiesSection />
        <QuickStartSection />
      </main>
      <Footer />
    </div>
  )
}
