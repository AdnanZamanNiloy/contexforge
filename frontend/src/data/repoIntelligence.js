// Mock repository-intelligence data for the Repository Intelligence page.
// These structures are shaped to be replaced by real backend analysis later:
// every section exposes plain objects/arrays the page can hydrate from an API.

export const repo = {
  owner: 'contextforge',
  name: 'contextforge',
  fullName: 'contextforge/contextforge',
  description:
    'Grounded AI developer workspace — ingests PDFs, websites and GitHub repositories to deliver source-aware, conversational answers.',
  visibility: 'public',
  branch: 'main',
  language: 'Python',
  files: 1284,
  modules: 42,
  commits: 8700,
  contributors: 76,
  branches: 6,
  pullRequests: 214,
  issues: 89,
  lastAnalyzed: '2026-08-25T09:41:00Z',
  defaultBranch: 'main',
};

export const overviewStats = {
  files: 1284,
  modules: 42,
  commits: 8700,
  contributors: 76,
  branches: 6,
  pullRequests: 214,
  issues: 89,
};

export const repoHealth = {
  score: 82,
  dimensions: [
    { label: 'Code Quality', value: 88, tone: 'good' },
    { label: 'Test Coverage', value: 74, tone: 'good' },
    { label: 'Dependencies', value: 69, tone: 'warn' },
    { label: 'Security', value: 91, tone: 'good' },
  ],
};

export const rankedModules = [
  { name: 'retrieval/', value: 96 },
  { name: 'orchestrator.py', value: 88 },
  { name: 'generation/', value: 82 },
  { name: 'services/', value: 76 },
  { name: 'routes/', value: 64 },
];

export const recentActivity = [
  { id: 'a1', hash: '8f3d2c1', message: 'Refactor hybrid retrieval fusion into RRF', time: '2026-08-25T09:12:00Z', author: 'daniel', kind: 'commit' },
  { id: 'a2', hash: 'b7e90aa', message: 'Add SSE streaming latency markers', time: '2026-08-24T18:03:00Z', author: 'priya', kind: 'commit' },
  { id: 'a3', hash: '4c1f0d9', message: 'Introduce multi-provider LLM fallback chain', time: '2026-08-24T11:47:00Z', author: 'sam', kind: 'commit' },
  { id: 'a4', hash: 'e62b5c4', message: 'Stage 4 — fix answer confidence gating', time: '2026-08-23T15:20:00Z', author: 'daniel', kind: 'commit' },
  { id: 'a5', hash: '0a9d4ef', message: 'Add decision tree to compute answer coverage', time: '2026-08-22T09:58:00Z', author: 'maria', kind: 'commit' },
  { id: 'a6', hash: 'c3b28f7', message: 'Wrap dedup provider to skip duplicate chunks', time: '2026-08-21T20:31:00Z', author: 'lia', kind: 'commit' },
];

export const suggestedQuestions = [
  'How does GitHub ingestion work?',
  'What are the main dependencies?',
  'Which files are most coupled?',
  'Show me the query pipeline',
  'Why is this module high risk?',
];

// Sizes for architecture graph nodes (components)
export const graphDimensions = { width: 1240, height: 860 };

// Interactive architecture graph — hierarchical abstraction:
// Repository -> Area -> Directory -> Module -> File
export const architecture = {
  nodes: [
    { id: 'repo', label: 'contextforge', kind: 'repo', x: 70, y: 400, meta: { path: '/', files: 1284, loc: 128400, deps: 0, dependents: 0, risk: 'Low', coverage: 82 } },
    // --- Frontend area ---
    { id: 'frontend', label: 'Frontend / UI', kind: 'area', x: 300, y: 190, meta: { path: 'frontend/', files: 96, loc: 15200, deps: 9, dependents: 3, risk: 'Low', coverage: 61, changed: '5d ago' } },
    { id: 'fe-pages', label: 'pages/', kind: 'directory', x: 530, y: 90, meta: { path: 'frontend/src/pages/', files: 2, loc: 1900, deps: 4, dependents: 1, risk: 'Low', coverage: 40 } },
    { id: 'fe-components', label: 'components/', kind: 'directory', x: 530, y: 200, meta: { path: 'frontend/src/components/', files: 6, loc: 3400, deps: 6, dependents: 8, risk: 'Medium', coverage: 55 } },
    { id: 'fe-hooks', label: 'hooks/', kind: 'directory', x: 530, y: 310, meta: { path: 'frontend/src/hooks/', files: 2, loc: 800, deps: 3, dependents: 2, risk: 'Low', coverage: 48 } },
    { id: 'fe-home', label: 'Home.jsx', kind: 'file', x: 790, y: 150, meta: { path: 'frontend/src/pages/Home.jsx', files: 1, loc: 676, deps: 12, dependents: 1, risk: 'High', coverage: 35, changed: '3d ago' } },
    { id: 'fe-chatbox', label: 'ChatBox.jsx', kind: 'file', x: 790, y: 290, meta: { path: 'frontend/src/components/ChatBox.jsx', files: 1, loc: 330, deps: 8, dependents: 1, risk: 'High', coverage: 0, changed: '9d ago' } },
    // --- Backend area ---
    { id: 'backend', label: 'Backend / Services', kind: 'area', x: 300, y: 620, meta: { path: 'backend/', files: 320, loc: 64200, deps: 22, dependents: 11, risk: 'High', coverage: 71, changed: '2d ago' } },
    { id: 'be-app', label: 'app/', kind: 'directory', x: 530, y: 470, meta: { path: 'backend/app/', files: 42, loc: 7800, deps: 18, dependents: 6, risk: 'Medium', coverage: 68 } },
    { id: 'be-services', label: 'services/', kind: 'module', x: 790, y: 380, meta: { path: 'backend/app/services/', files: 2, loc: 360, deps: 6, dependents: 5, risk: 'High', coverage: 72, changed: '2d ago' } },
    { id: 'be-routes', label: 'routes/', kind: 'module', x: 790, y: 480, meta: { path: 'backend/app/routes/', files: 3, loc: 310, deps: 9, dependents: 4, risk: 'High', coverage: 64, changed: '2d ago' } },
    { id: 'fe-files', label: 'services/ingest.py', kind: 'file', x: 1040, y: 340, meta: { path: 'backend/app/services/ingest_service.py', files: 1, loc: 180, deps: 7, dependents: 3, risk: 'High', coverage: 70, changed: '2d ago' } },
    { id: 'fe-query', label: 'services/query.py', kind: 'file', x: 1040, y: 440, meta: { path: 'backend/app/services/query_service.py', files: 1, loc: 160, deps: 8, dependents: 4, risk: 'High', coverage: 66, changed: '2d ago' } },
    // --- Core area (grouped under backend) ---
    { id: 'core', label: 'Core', kind: 'area', x: 530, y: 660, meta: { path: 'backend/core/', files: 318, loc: 24541, deps: 18, dependents: 7, risk: 'High', coverage: 68, changed: '2d ago' } },
    { id: 'core-ingestion', label: 'ingestion/', kind: 'module', x: 790, y: 570, meta: { path: 'backend/core/ingestion/', files: 8, loc: 490, deps: 4, dependents: 3, risk: 'Medium', coverage: 80, changed: '2d ago' } },
    { id: 'core-chunking', label: 'chunking/', kind: 'module', x: 790, y: 660, meta: { path: 'backend/core/chunking/', files: 3, loc: 360, deps: 5, dependents: 4, risk: 'Medium', coverage: 74, changed: '6d ago' } },
    { id: 'core-embedding', label: 'embedding/', kind: 'module', x: 790, y: 750, meta: { path: 'backend/core/embedding/', files: 2, loc: 520, deps: 7, dependents: 5, risk: 'High', coverage: 62, changed: '4d ago' } },
    { id: 'core-retrieval', label: 'retrieval/', kind: 'module', x: 1040, y: 610, meta: { path: 'backend/core/retrieval/', files: 5, loc: 890, deps: 14, dependents: 9, risk: 'Critical', coverage: 78, changed: '2d ago' } },
    { id: 'core-storage', label: 'storage/', kind: 'module', x: 1040, y: 710, meta: { path: 'backend/core/storage/', files: 2, loc: 430, deps: 3, dependents: 6, risk: 'Medium', coverage: 84, changed: '8d ago' } },
    { id: 'core-generation', label: 'generation/', kind: 'module', x: 790, y: 840, meta: { path: 'backend/core/generation/', files: 6, loc: 610, deps: 8, dependents: 2, risk: 'Medium', coverage: 71, changed: '4d ago' } },
    { id: 'core-orchestrator', label: 'orchestrator.py', kind: 'file', x: 1040, y: 810, meta: { path: 'backend/core/orchestrator.py', files: 1, loc: 240, deps: 16, dependents: 6, risk: 'Critical', coverage: 70, changed: '2d ago' } },
    { id: 'core-hybrid', label: 'hybrid_retriever.py', kind: 'file', x: 1040, y: 520, meta: { path: 'backend/core/retrieval/hybrid_retriever.py', files: 1, loc: 180, deps: 9, dependents: 4, risk: 'Critical', coverage: 76, changed: '2d ago' } },
  ],
  edges: [
    { source: 'repo', target: 'frontend', kind: 'contains' },
    { source: 'repo', target: 'backend', kind: 'contains' },
    { source: 'frontend', target: 'fe-pages', kind: 'contains' },
    { source: 'frontend', target: 'fe-components', kind: 'contains' },
    { source: 'frontend', target: 'fe-hooks', kind: 'contains' },
    { source: 'fe-pages', target: 'fe-home', kind: 'contains' },
    { source: 'fe-components', target: 'fe-chatbox', kind: 'contains' },
    { source: 'backend', target: 'be-app', kind: 'contains' },
    { source: 'be-app', target: 'be-services', kind: 'contains' },
    { source: 'be-app', target: 'be-routes', kind: 'contains' },
    { source: 'be-services', target: 'fe-files', kind: 'contains' },
    { source: 'be-services', target: 'fe-query', kind: 'contains' },
    { source: 'backend', target: 'core', kind: 'contains' },
    { source: 'core', target: 'core-ingestion', kind: 'contains' },
    { source: 'core', target: 'core-chunking', kind: 'contains' },
    { source: 'core', target: 'core-embedding', kind: 'contains' },
    { source: 'core', target: 'core-retrieval', kind: 'contains' },
    { source: 'core', target: 'core-storage', kind: 'contains' },
    { source: 'core', target: 'core-generation', kind: 'contains' },
    { source: 'core', target: 'core-orchestrator', kind: 'contains' },
    { source: 'core-retrieval', target: 'core-hybrid', kind: 'contains' },
    // dependency edges (decorative relationships)
    { source: 'core-orchestrator', target: 'fe-query', kind: 'calls' },
    { source: 'fe-query', target: 'core-retrieval', kind: 'calls' },
    { source: 'core-retrieval', target: 'core-orchestrator', kind: 'imports' },
    { source: 'core-embedding', target: 'core-storage', kind: 'writes' },
    { source: 'core-generation', target: 'core-retrieval', kind: 'reads' },
    { source: 'fe-components', target: 'fe-pages', kind: 'imports' },
  ],
};

// Dependencies view — friendly, curated relationships around a selected node
export const dependencyGraph = {
  nodes: [
    { id: 'hybrid', label: 'hybrid_retriever.py', kind: 'file', x: 620, y: 430, meta: { path: 'core/retrieval/hybrid_retriever.py', risk: 'Critical' } },
    { id: 'rrf', label: 'Fusion / RRF', kind: 'func', x: 620, y: 640, meta: { path: 'core/retrieval/hybrid_retriever.py::fuse', risk: 'Medium' } },
    { id: 'query', label: 'QueryService', kind: 'module', x: 250, y: 250, meta: { path: 'app/services/query_service.py', risk: 'High' } },
    { id: 'route', label: '/query', kind: 'route', x: 250, y: 80, meta: { path: 'app/routes/query.py', risk: 'High' } },
    { id: 'orchestrator', label: 'Orchestrator', kind: 'module', x: 250, y: 620, meta: { path: 'core/orchestrator.py', risk: 'High' } },
    { id: 'hyde', label: 'HyDE', kind: 'module', x: 250, y: 810, meta: { path: 'core/retrieval/hyde.py', risk: 'Medium' } },
    { id: 'bm25', label: 'BM25Retriever', kind: 'module', x: 990, y: 250, meta: { path: 'core/retrieval/bm25_retriever.py', risk: 'Medium' } },
    { id: 'faiss', label: 'FaissStore', kind: 'module', x: 990, y: 520, meta: { path: 'core/storage/faiss_store.py', risk: 'Medium' } },
    { id: 'front', label: 'Frontend Chat', kind: 'module', x: 990, y: 790, meta: { path: 'frontend/src/components/ChatBox.jsx', risk: 'Low' } },
    { id: 'tests', label: 'integration tests', kind: 'module', x: 990, y: 990, meta: { path: 'backend/tests/integration/', risk: 'Low' } },
  ],
  edges: [
    { source: 'query', target: 'hybrid', kind: 'calls' },
    { source: 'route', target: 'query', kind: 'calls' },
    { source: 'query', target: 'hyde', kind: 'calls' },
    { source: 'hybrid', target: 'rrf', kind: 'calls' },
    { source: 'hybrid', target: 'bm25', kind: 'reads' },
    { source: 'hybrid', target: 'faiss', kind: 'reads' },
    { source: 'orchestrator', target: 'query', kind: 'calls' },
    { source: 'hybrid', target: 'front', kind: 'result' },
    { source: 'front', target: 'tests', kind: 'tested_by' },
    { source: 'rrf', target: 'front', kind: 'result' },
  ],
};

// Data-flow pipelines
export const dataFlows = {
  query: {
    title: 'Query Flow',
    steps: [
      { id: 'q1', label: 'Question', kind: 'input' },
      { id: 'q2', label: 'QueryService', kind: 'service' },
      { id: 'q3', label: 'Orchestrator', kind: 'core' },
      { id: 'q4', label: 'HyDE', kind: 'module' },
      { id: 'q5', label: 'Hybrid Retrieval', kind: 'module' },
      { id: 'q6', label: 'RRF Fusion', kind: 'module' },
      { id: 'q7', label: 'Reranker', kind: 'module' },
      { id: 'q8', label: 'Prompt Builder', kind: 'module' },
      { id: 'q9', label: 'LLM', kind: 'llm' },
      { id: 'q10', label: 'SSE', kind: 'transport' },
      { id: 'q11', label: 'Frontend', kind: 'output' },
    ],
  },
  ingestion: {
    title: 'Ingestion Flow',
    steps: [
      { id: 'i1', label: 'GitHub', kind: 'input' },
      { id: 'i2', label: 'Loader', kind: 'service' },
      { id: 'i3', label: 'Chunker', kind: 'core' },
      { id: 'i4', label: 'Processing', kind: 'core' },
      { id: 'i5', label: 'Embedding', kind: 'llm' },
      { id: 'i6', label: 'FAISS / BM25', kind: 'storage' },
      { id: 'i7', label: 'Cache', kind: 'storage' },
    ],
  },
};

export const gitHistory = {
  range: 'Last 30 days',
  branches: [
    { name: 'main', commits: 4032, color: '#7aa2f7', active: true },
    { name: 'feat/hybrid-rrf', commits: 214, color: '#67e0c8' },
    { name: 'feat/llm-fallback', commits: 96, color: '#b6a1ff' },
    { name: 'fix/confidence-gate', commits: 41, color: '#e07b7b' },
  ],
  timeline: [
    { week: 'W1', commits: 180 },
    { week: 'W2', commits: 240 },
    { week: 'W3', commits: 310 },
    { week: 'W4', commits: 268 },
    { week: 'W5', commits: 356 },
  ],
  fileChurn: [
    { name: 'core/retrieval/hybrid_retriever.py', value: 92 },
    { name: 'core/orchestrator.py', value: 84 },
    { name: 'app/services/query_service.py', value: 71 },
    { name: 'core/chunking/text_chunker.py', value: 55 },
    { name: 'app/routes/query.py', value: 48 },
    { name: 'core/ingestion/web_loader.py', value: 39 },
  ],
  commits: [
    { hash: '8f3d2c1', message: 'Refactor hybrid retrieval fusion into RRF', author: 'daniel-w', time: '2 hours ago', files: 9, inserts: 142, deletes: 61 },
    { hash: 'b7e90aa', message: 'Add SSE streaming latency markers', author: 'priya-k', time: '9 hours ago', files: 4, inserts: 38, deletes: 5 },
    { hash: '4c1f0d9', message: 'Introduce multi-provider LLM fallback chain', author: 'sam-r', time: '1 day ago', files: 6, inserts: 210, deletes: 90 },
    { hash: 'e62b5c4', message: 'Fix answer confidence gating', author: 'daniel-w', time: '2 days ago', files: 3, inserts: 27, deletes: 12 },
    { hash: '0a9d4ef', message: 'Add decision tree for answer coverage', author: 'maria-l', time: '3 days ago', files: 5, inserts: 84, deletes: 30 },
  ],
};

export const ownership = {
  contributors: [
    { name: 'daniel-w', commits: 2890, percent: 33, color: '#7aa2f7' },
    { name: 'priya-k', commits: 2170, percent: 25, color: '#67e0c8' },
    { name: 'sam-r', commits: 1480, percent: 17, color: '#b6a1ff' },
    { name: 'maria-l', commits: 1100, percent: 13, color: '#f0b36e' },
    { name: 'lia-m', commits: 640, percent: 7, color: '#e07b7b' },
    { name: 'other', commits: 420, percent: 5, color: '#8b94a5' },
  ],
  modules: [
    {
      name: 'app/services/query_service.py', owner: 'priya-k', percent: 64, files: 4,
      contributors: [{ name: 'priya-k', percent: 64 }, { name: 'daniel-w', percent: 24 }, { name: 'sam-r', percent: 12 }],
    },
    {
      name: 'core/retrieval/', owner: 'daniel-w', percent: 58, files: 28,
      contributors: [{ name: 'daniel-w', percent: 58 }, { name: 'maria-l', percent: 22 }, { name: 'priya-k', percent: 20 }],
    },
    {
      name: 'core/orchestrator.py', owner: 'sam-r', percent: 51, files: 1,
      contributors: [{ name: 'sam-r', percent: 51 }, { name: 'daniel-w', percent: 31 }, { name: 'priya-k', percent: 18 }],
    },
    {
      name: 'app/routes/', owner: 'maria-l', percent: 47, files: 9,
      contributors: [{ name: 'maria-l', percent: 47 }, { name: 'lia-m', percent: 30 }, { name: 'priya-k', percent: 23 }],
    },
    {
      name: 'core/ingestion/', owner: 'lia-m', percent: 43, files: 16,
      contributors: [{ name: 'lia-m', percent: 43 }, { name: 'daniel-w', percent: 34 }, { name: 'maria-l', percent: 23 }],
    },
    {
      name: 'frontend/src/components/', owner: 'priya-k', percent: 39, files: 12,
      contributors: [{ name: 'priya-k', percent: 39 }, { name: 'sam-r', percent: 32 }, { name: 'lia-m', percent: 29 }],
    },
  ],
  concentration: { top1: 33, top3: 75, busFactor: 4, risk: 'Medium' },
};

export const changeImpact = {
  selection: 'core/retrieval/hybrid_retriever.py',
  estimated: {
    affectedFiles: 187,
    affectedModules: 24,
    affectedApis: 12,
    affectedTests: 56,
    affectedDependencies: 31,
  },
  risk: 'CRITICAL',
  blastRadius: {
    nodes: [
      { id: 'primary', label: 'hybrid_retriever.py', kind: 'file', x: 620, y: 430, direct: true, risk: 'Critical' },
      { id: 'i1', label: 'RRF Fusion', kind: 'module', x: 250, y: 210, direct: true },
      { id: 'i2', label: 'QueryService', kind: 'module', x: 250, y: 400, direct: true },
      { id: 'i3', label: '/query', kind: 'route', x: 250, y: 590, direct: true },
      { id: 'i4', label: 'Frontend Chat', kind: 'module', x: 250, y: 780, direct: true },
      { id: 'o1', label: 'Bm25Retriever', kind: 'module', x: 990, y: 210, direct: false },
      { id: 'o2', label: 'FaissStore', kind: 'module', x: 990, y: 400, direct: false },
      { id: 'o3', label: 'Reranker', kind: 'module', x: 990, y: 590, direct: false },
      { id: 'o4', label: 'integration tests', kind: 'module', x: 990, y: 780, direct: false },
    ],
    edges: [
      { source: 'primary', target: 'i1', kind: 'direct' },
      { source: 'primary', target: 'i2', kind: 'direct' },
      { source: 'i2', target: 'i3', kind: 'direct' },
      { source: 'i3', target: 'i4', kind: 'direct' },
      { source: 'primary', target: 'o1', kind: 'indirect' },
      { source: 'primary', target: 'o2', kind: 'indirect' },
      { source: 'i1', target: 'o3', kind: 'indirect' },
      { source: 'i4', target: 'o4', kind: 'indirect' },
    ],
  },
  nodes: [
    { id: 'p', label: 'hybrid_retriever.py', files: 187, modules: 24, apis: 12, tests: 56, deps: 31, risk: 'Critical' },
    { id: 'i1', label: 'RRF Fusion', files: 96, modules: 12, apis: 8, tests: 31, deps: 14, risk: 'High' },
    { id: 'i2', label: 'QueryService', files: 74, modules: 9, apis: 6, tests: 24, deps: 11, risk: 'High' },
    { id: 'i3', label: '/query', files: 41, modules: 6, apis: 4, tests: 18, deps: 7, risk: 'Medium' },
    { id: 'i4', label: 'Frontend Chat', files: 22, modules: 4, apis: 2, tests: 9, deps: 4, risk: 'Medium' },
    { id: 'o1', label: 'Bm25Retriever', files: 58, modules: 7, apis: 5, tests: 19, deps: 8, risk: 'Medium' },
    { id: 'o2', label: 'FaissStore', files: 47, modules: 6, apis: 4, tests: 15, deps: 6, risk: 'Medium' },
    { id: 'o3', label: 'Reranker', files: 36, modules: 5, apis: 3, tests: 12, deps: 5, risk: 'Low' },
    { id: 'o4', label: 'integration tests', files: 64, modules: 8, apis: 6, tests: 21, deps: 9, risk: 'Medium' },
  ],
};

export const riskExplanations = {
  High: 'Frequently changed, many dependents, and limited test coverage make this node a hot spot for regressions.',
  Medium: 'Moderate change frequency with a contained dependency footprint — review before large refactors.',
  Critical: 'Central hub with high fan-out. Changes here cascade to a large fraction of the repository.',
  Low: 'Low coupling and stable change rate — safe to evolve in isolation.',
};

export const moduleDetails = {
  path: 'src/core/',
  type: 'Directory',
  files: 318,
  loc: 24541,
  deps: 18,
  dependents: 7,
  risk: 'High',
  coverage: 68,
  changed: '2 days ago',
  contributors: ['daniel-w', 'priya-k', 'sam-r', 'maria-l'],
  topDependencies: ['shared', 'scheduler', 'object-assign', 'fbjs'],
  recentChanges: [
    { hash: '8f3d2c1', message: 'Refactor hybrid retrieval fusion into RRF', time: '2 hours ago' },
    { hash: 'b7e90aa', message: 'Add SSE streaming latency markers', time: '9 hours ago' },
    { hash: '4c1f0d9', message: 'Introduce multi-provider LLM fallback chain', time: '1 day ago' },
  ],
};

// Keyword → node ids to highlight when the AI assistant matches a question.
export const aiHighlightPipelines = {
  'query pipeline': ['fe-query', 'core-orchestrator', 'core-retrieval', 'core-hybrid', 'core-hybrid'],
  'ingestion': ['core-ingestion', 'core-chunking', 'core-embedding'],
  'dependency': ['core-retrieval', 'core-hybrid'],
  'dependencies': ['core-retrieval', 'core-hybrid'],
  'coupled': ['core-hybrid', 'core-orchestrator', 'core-retrieval'],
  'risk': ['core-retrieval', 'core-hybrid'],
  'high risk': ['core-retrieval', 'core-hybrid'],
  'architecture': ['repo', 'frontend', 'backend', 'core'],
};
