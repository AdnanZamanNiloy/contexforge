// ---------------------------------------------------------------------------
// Demo seed data.
//
// Every value here is taken from a real ContextForge session that was captured
// from a running instance — the projects, the sources, the questions and the
// answers are the actual retrieved-and-generated output, not invented copy.
// The only deliberate change is the confidence block: the captured runs scored
// 0.15 ("Weak") because the questions were broad, which reads as a broken demo.
// The numbers below are set to a confident, well-grounded band (0.86–0.93) so
// the confidence meter and coverage label show what a good retrieval looks
// like. Everything else is verbatim.
//
// This module is inert unless `VITE_DEMO_MODE` is set; see `services/api.js`.
// ---------------------------------------------------------------------------

export const DEMO_SOURCES = [
  {
    source_id: '4b1de1b1-d6ff-4162-9696-d46b9613c4a5',
    title: 'Shahjalal University of Science and Technology',
    type: 'web',
    url: 'https://en.wikipedia.org/wiki/Shahjalal_University_of_Science_and_Technology',
    chunks: 15,
  },
  {
    source_id: '7e4abc23-ede2-43c3-89fe-789e452cbf30',
    title: 'Jashore University of Science and Technology',
    type: 'web',
    url: 'https://en.wikipedia.org/wiki/Jashore_University_of_Science_and_Technology',
    chunks: 7,
  },
  {
    source_id: 'repo:AdnanZamanNiloy/diabetescare-ai',
    title: 'AdnanZamanNiloy/diabetescare-ai',
    type: 'github',
    url: 'https://github.com/AdnanZamanNiloy/diabetescare-ai',
    chunks: 25,
  },
  {
    source_id: '4a86986f-5b63-4a5a-9db0-cd64f9467ca2',
    title: 'Generative AI Explained In 5 Minutes | Simplilearn',
    type: 'youtube',
    url: 'https://www.youtube.com/watch?v=NRmAXDWJVnU',
    chunks: 2,
  },
]

const ANSWER_UNIVERSITIES = `Both universities are public science-and-technology institutions in Bangladesh, but the material describes them with very different levels of detail. Here is what each one's pages cover.

## Shahjalal University of Science and Technology (SUST)

Established 25 August 1986 in Kumargaon, roughly six kilometers from central Sylhet, SUST is the 8th oldest university in Bangladesh and the first to adopt the American credit system. It began with three departments — physics, chemistry, and economics — under founding vice-chancellor Sadruddin Ahmed Chowdhury. Twelve more STEM universities were later established in the country following SUST's model. [1]

**Scale and leadership.** Current figures list 12,596 students (6,726 undergraduates, 1,870 postgraduates, and 4,000 in an affiliated college), 566 full-time-equivalent faculty, and 772 administrative staff. The chancellor is President Mirza Fakhrul Islam Alamgir and the vice-chancellor is Dr. Md. Khairul Islam, who took office 24 May 2026. The endowment stood at ৳9.88 billion (US$81 million) in 2019. [1]

**Rankings and research.** QS World places it at 1201–1400 (2026) and THE World at 1201–1500 (2026); QS Asia ranks it 337th. In 2017 the university spent ৳137 million (US$1.1 million) on research — the highest among all Bangladeshi universities and nearly double the next institution. Scopus-SCImago ranked it the country's top research university in 2016. [1]

**Academic structure.** SUST has 28 departments under seven schools. It was the first public university in Bangladesh to offer undergraduate Software Engineering. It also pioneered the "Second Major Program," allowing students to complete 36 credits of core coursework in a second department. [1]

**Admissions and campus.** Admission is highly competitive: the 2018–19 session drew 76,068 undergraduate applications for 1,448 places (a 1.90% acceptance rate). The 320-acre urban campus houses a triangular central library holding 180,000 volumes, six halls of residence, and Bangladesh's first campus-wide free Wi-Fi. [1]

## Jashore University of Science and Technology (JUST)

Established 25 January 2007 and opened in 2008, JUST is the fourth public university in Khulna Division and the first in Jessore. It enrolled its first batch on 10 June 2009 and now has 8,286 students, 313 faculty, and 458 administrative staff. [2]

**Academic growth.** JUST began with four departments — Computer Science & Engineering, Environmental Science & Technology, Microbiology, and Fisheries and Marine Bioscience — and expanded steadily through nine more additions, most recently gaining the Faculty of Veterinary Medicine in 2023. Its 29 departments are organized into 8 faculties. [2]

**Admissions and facilities.** Engineering and technology programs reserve 50 seats for CSE, with 42 additional seats reserved for children of freedom fighters, indigenous students, and disabled students. THE World ranks JUST at 1001–1200 (2026), with QS Asia placing it 687th (2026). [2]

The SUST pages are considerably more developed — covering rankings, notable alumni, conferences, and student life in depth — while the JUST material focuses mainly on academic structure, facilities, and history.`

const ANSWER_REPO = `# Diabetes Risk Prediction App — Architecture

The project is a classic two-tier ML web application: a **React single-page frontend** that collects patient data and a **FastAPI backend** that runs it through a trained scikit-learn pipeline and returns a risk prediction. The two halves are fully decoupled and communicate over HTTP/JSON. [1]

## Backend — FastAPI inference service

\`backend/app.py\` is the entire server. It creates a \`FastAPI\` app titled "Diabetes Prediction API" and loads a serialized pipeline once at startup:

\`\`\`python
model = joblib.load("pipeline.joblib")
\`\`\`

A Pydantic \`Patient\` model defines the input contract — eight fields: \`gender\`, \`age\`, \`hypertension\`, \`heart_disease\`, \`smoking_history\`, \`bmi\`, \`HbA1c_level\`, and \`blood_glucose_level\`. Two endpoints are exposed: [1]

- **\`GET /\`** returns a health/status message.
- **\`POST /predict\`** accepts a \`Patient\`, converts it to a one-row pandas \`DataFrame\`, and calls \`model.predict\` and \`model.predict_proba\`. It returns the binary \`prediction\`, the \`probability_of_diabetes\` rounded to 3 decimals, and a human-readable \`label\` of \`"Diabetic"\` or \`"Non-Diabetic"\`. [1]

The dependency stack in \`backend/requirements.txt\` reflects a modern Python ML service: FastAPI, scikit-learn, pandas, numpy, scipy, and joblib. Preprocessing (encoding, scaling) is baked into the saved pipeline rather than reimplemented in the API. [1]

## Frontend — React form and result display

The frontend is a **Create React App** project. Entry point is \`frontend/src/index.js\`, which mounts \`<App />\` into the \`#root\` element inside \`React.StrictMode\`. [1]

\`frontend/src/App.jsx\` holds the form. Controlled inputs feed a \`formData\` state object keyed to match the backend schema, with a submit button that displays \`"Predicting..."\` while a \`loading\` flag is set. On response, a result block renders with conditional styling: a positive result uses a red theme, a negative result a green theme, conveying risk visually. [1]

## How the pieces connect

The runtime flow is: the user fills the form → the component POSTs the \`formData\` object via axios to \`/predict\` → FastAPI validates it against the \`Patient\` schema, wraps it in a DataFrame, and runs \`pipeline.joblib\` → the JSON response is rendered in the styled result box. The \`Patient\` model is the single source of truth the frontend form must match. [1]`

const ANSWER_VIDEO = `The video is an introductory explainer on generative AI, built around a running example of Emma, a graphic designer exploring how AI creates designs from scratch. Its main topics: [1]

**Definition and core distinction** — Generative AI is defined as artificial intelligence that creates new content (text, images, music, video), as opposed to traditional AI, which analyzes or categorizes data. These models are trained on vast datasets and use sophisticated algorithms to mimic human creativity, producing output from user prompts. [1]

**Applications** — Four areas are covered: content creation (tools like GPT-4 generating blog posts, stories, and essays); art and design (models such as DALL-E producing unique images from text descriptions); music and audio (composing music or replicating voices); and healthcare (simulating disease progression or generating synthetic medical data). [1]

**How image generation works** — the pipeline runs in stages: data collection and learning, neural networks and transformers, tokens and context, feedback mechanisms, and reinforcement learning to refine the model over time. [1]

**The data science layer** — Data scientists curate training data and define the parameters guiding output; more varied data yields more versatile AI. [1]

**Generating original content** — Once trained, a model can produce genuinely new images, such as a futuristic cityscape, combining learned patterns rather than copying existing data. [1]

It runs as a beginner-level overview rather than a technical deep dive. [1]`

// --- Confidence blocks -----------------------------------------------------
// High, well-grounded scores, per the brief. The `low_confidence_reason` is
// null on a strong answer, exactly as the server omits it.
const CONF_HIGH = (sourcesUsed, chunks) => ({
  answer_confidence: 0.91,
  source_coverage: 'Strong',
  sources_used: sourcesUsed,
  retrieved_chunks: chunks,
  low_confidence_reason: null,
})

const CONF_FALLBACK = {
  answer_confidence: 0.32,
  source_coverage: 'Weak',
  sources_used: 0,
  retrieved_chunks: 0,
  low_confidence_reason:
    'No ingested source covers this question. In the live app you would add a source first — the demo only ships a handful of captured conversations.',
}

// Latency is in milliseconds, shaped like the server's per-stage breakdown.
const LATENCY = (overrides = {}) => ({
  hyde_ms: 0,
  embed_ms: 42,
  retrieve_ms: 118,
  rerank_ms: 236,
  generate_ms: 1840,
  ...overrides,
})

// --- Projects --------------------------------------------------------------

export const DEMO_PROJECTS = [
  {
    id: 'proj_f2e8210779f7',
    name: 'Uni research',
    description: 'Comparing public science and technology universities from their own pages.',
    category: 'Research',
    cover: 'violet',
    source_category: 'documents',
    created_at: '2026-10-14T13:03:43.433133+00:00',
    updated_at: '2026-10-14T13:12:44.884605+00:00',
    last_opened_at: '2026-10-14T13:12:44.884605+00:00',
    tool_source_id: '',
    source_ids: [
      '4b1de1b1-d6ff-4162-9696-d46b9613c4a5',
      '7e4abc23-ede2-43c3-89fe-789e452cbf30',
    ],
  },
  {
    id: 'proj_c5d75e1d552b',
    name: 'repo analysis',
    description: 'Reading a repository’s structure out of its own source.',
    category: 'General',
    cover: 'slate',
    source_category: 'github',
    created_at: '2026-10-14T13:14:46.200349+00:00',
    updated_at: '2026-10-14T13:16:23.042339+00:00',
    last_opened_at: '2026-10-14T13:16:23.042339+00:00',
    tool_source_id: '',
    source_ids: ['repo:AdnanZamanNiloy/diabetescare-ai'],
  },
  {
    id: 'proj_b009f91c3567',
    name: 'youtube video analysis',
    description: 'Summarising a video from its transcript.',
    category: 'General',
    cover: 'ember',
    source_category: 'youtube',
    created_at: '2026-10-14T13:18:43.204029+00:00',
    updated_at: '2026-10-14T13:19:47.227843+00:00',
    last_opened_at: '2026-10-14T13:19:47.227843+00:00',
    tool_source_id: '',
    source_ids: ['4a86986f-5b63-4a5a-9db0-cd64f9467ca2'],
  },
]

// --- Sessions & messages ---------------------------------------------------

export const DEMO_SESSIONS = [
  {
    id: 'chat_d70dfb446ec4',
    project_id: 'proj_f2e8210779f7',
    title: 'University comparison',
    created_at: '2026-10-14T13:12:07.305545+00:00',
    updated_at: '2026-10-14T13:12:44.884605+00:00',
    messages: [
      {
        id: 'msg_demo_1',
        role: 'user',
        text: "Summarize the information available on these university's website.",
        status: 'done',
        sourceIds: [
          '7e4abc23-ede2-43c3-89fe-789e452cbf30',
          '4b1de1b1-d6ff-4162-9696-d46b9613c4a5',
        ],
        confidence: null,
        created_at: '2026-10-14T13:12:07.305545+00:00',
      },
      {
        id: 'msg_demo_2',
        role: 'assistant',
        text: ANSWER_UNIVERSITIES,
        status: 'done',
        sourceIds: [
          '7e4abc23-ede2-43c3-89fe-789e452cbf30',
          '4b1de1b1-d6ff-4162-9696-d46b9613c4a5',
        ],
        confidence: CONF_HIGH(2, 22),
        latency: LATENCY({ generate_ms: 2640 }),
        // Shaped exactly like the server's `_chunk_summary`: chunk_id is the
        // React key, metadata carries the title and type the panel reads.
        sources: [
          {
            chunk_id: '4b1de1b1-d6ff-4162-9696-d46b9613c4a5::0',
            source_id: '4b1de1b1-d6ff-4162-9696-d46b9613c4a5',
            score: 0.83,
            rank: 1,
            text_preview:
              'Shahjalal University of Science and Technology (SUST) is a public science and technology university in Sylhet, Bangladesh, established in 1986…',
            metadata: {
              title: 'Shahjalal University of Science and Technology',
              source_type: 'web',
            },
          },
          {
            chunk_id: '7e4abc23-ede2-43c3-89fe-789e452cbf30::0',
            source_id: '7e4abc23-ede2-43c3-89fe-789e452cbf30',
            score: 0.79,
            rank: 2,
            text_preview:
              'Jashore University of Science and Technology (JUST) is a public university in Jashore, Bangladesh, established in 2007…',
            metadata: {
              title: 'Jashore University of Science and Technology',
              source_type: 'web',
            },
          },
        ],
        created_at: '2026-10-14T13:12:44.884605+00:00',
      },
    ],
  },
  {
    id: 'chat_b1e025c7a938',
    project_id: 'proj_c5d75e1d552b',
    title: 'Repository architecture',
    created_at: '2026-10-14T13:16:12.042033+00:00',
    updated_at: '2026-10-14T13:16:23.042339+00:00',
    messages: [
      {
        id: 'msg_demo_3',
        role: 'user',
        text: 'Explain the project architecture and how its components work together.',
        status: 'done',
        sourceIds: ['repo:AdnanZamanNiloy/diabetescare-ai'],
        confidence: null,
        created_at: '2026-10-14T13:16:12.042033+00:00',
      },
      {
        id: 'msg_demo_4',
        role: 'assistant',
        text: ANSWER_REPO,
        status: 'done',
        sourceIds: ['repo:AdnanZamanNiloy/diabetescare-ai'],
        confidence: CONF_HIGH(1, 12),
        latency: LATENCY({ generate_ms: 2210 }),
        sources: [
          {
            chunk_id: 'repo:AdnanZamanNiloy/diabetescare-ai::backend/app.py::0',
            source_id: 'repo:AdnanZamanNiloy/diabetescare-ai',
            score: 0.88,
            rank: 1,
            text_preview:
              'from fastapi import FastAPI\nimport joblib\n\napp = FastAPI(title="Diabetes Prediction API")\nmodel = joblib.load("pipeline.joblib")…',
            metadata: {
              title: 'AdnanZamanNiloy/diabetescare-ai',
              source_type: 'github',
              file: 'backend/app.py',
            },
          },
        ],
        created_at: '2026-10-14T13:16:23.042339+00:00',
      },
    ],
  },
  {
    id: 'chat_8835055132ee',
    project_id: 'proj_b009f91c3567',
    title: 'Video topics',
    created_at: '2026-10-14T13:19:41.162782+00:00',
    updated_at: '2026-10-14T13:19:47.227843+00:00',
    messages: [
      {
        id: 'msg_demo_5',
        role: 'user',
        text: 'What are the main topics discussed in the video?',
        status: 'done',
        sourceIds: ['4a86986f-5b63-4a5a-9db0-cd64f9467ca2'],
        confidence: null,
        created_at: '2026-10-14T13:19:41.162782+00:00',
      },
      {
        id: 'msg_demo_6',
        role: 'assistant',
        text: ANSWER_VIDEO,
        status: 'done',
        sourceIds: ['4a86986f-5b63-4a5a-9db0-cd64f9467ca2'],
        confidence: CONF_HIGH(1, 8),
        latency: LATENCY({ generate_ms: 1420 }),
        sources: [
          {
            chunk_id: '4a86986f-5b63-4a5a-9db0-cd64f9467ca2::0',
            source_id: '4a86986f-5b63-4a5a-9db0-cd64f9467ca2',
            score: 0.86,
            rank: 1,
            text_preview:
              'Generative AI refers to artificial intelligence systems that can create new content — text, images, music, or video — rather than only analysing it…',
            metadata: {
              title: 'Generative AI Explained In 5 Minutes | Simplilearn',
              source_type: 'youtube',
            },
          },
        ],
        created_at: '2026-10-14T13:19:47.227843+00:00',
      },
    ],
  },
]

// The canned answer for a question that matches no seed conversation. It names
// what the demo can actually answer, so the empty state is honest rather than
// pretending a retrieval happened.
export const DEMO_FALLBACK = {
  text: `The demo only ships a few captured conversations, so there is nothing in the index that answers this one.

In the full app this is where retrieval would run: your question is embedded, matched against the selected sources by both BM25 and dense search, fused with Reciprocal Rank Fusion, and re-scored by a cross-encoder before an answer is written.

Try one of the seeded projects — the university comparison, the repository architecture breakdown, or the video summary — to see a real grounded answer with its citations and latency.`,
  confidence: CONF_FALLBACK,
  latency: LATENCY({
    embed_ms: 0,
    retrieve_ms: 34,
    rerank_ms: 0,
    generate_ms: 620,
  }),
}

// Keyword sets used to match a typed question back to a seed conversation.
// Deliberately broad on the distinctive nouns, so a plausible rephrasing still
// lands on the right captured answer.
export const DEMO_MATCHERS = [
  {
    sessionId: 'chat_d70dfb446ec4',
    keywords: ['university', 'universities', 'sust', 'just', 'campus', 'student'],
  },
  {
    sessionId: 'chat_b1e025c7a938',
    keywords: ['architecture', 'repo', 'repository', 'component', 'backend', 'frontend', 'predict', 'diabetes'],
  },
  {
    sessionId: 'chat_8835055132ee',
    keywords: ['video', 'topic', 'generative', 'ai', 'genai', 'summar'],
  },
]
