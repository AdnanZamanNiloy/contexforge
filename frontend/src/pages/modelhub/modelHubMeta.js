// Shared labels and helpers for the Model Hub UI.

export const MODEL_TYPES = [
  { id: 'llm', label: 'LLM', hint: 'Chat / generation model' },
  { id: 'embedding', label: 'Embedding', hint: 'Vector embedding model' },
]

export const RUNTIMES = [
  { id: 'api', label: 'API', hint: 'Hosted provider endpoint' },
  { id: 'local', label: 'Local', hint: 'Runs on this machine' },
]

export const PROVIDERS = [
  { id: 'openai', label: 'OpenAI' },
  { id: 'google', label: 'Google Gemini' },
  { id: 'groq', label: 'Groq' },
  { id: 'openrouter', label: 'OpenRouter' },
  { id: 'cerebras', label: 'Cerebras' },
  { id: 'nvidia', label: 'NVIDIA NIM' },
  { id: 'together', label: 'Together' },
  { id: 'mistral', label: 'Mistral' },
  { id: 'deepseek', label: 'DeepSeek' },
  { id: 'voyage', label: 'Voyage AI' },
  { id: 'custom', label: 'Custom (OpenAI-compatible)' },
]

export const LOCAL_BACKENDS = [
  { id: 'sentence_transformers', label: 'sentence-transformers (local embeddings)' },
]

export const DEVICES = [
  { id: 'auto', label: 'Auto' },
  { id: 'cpu', label: 'CPU' },
  { id: 'cuda', label: 'CUDA' },
]

export const STATUS_LABEL = {
  ready: 'Connected',
  error: 'Error',
  untested: 'Untested',
}

export function providerLabel(id) {
  return PROVIDERS.find((p) => p.id === id)?.label || id
}

export function statusClass(status) {
  if (status === 'ready') return 'is-ready'
  if (status === 'error') return 'is-error'
  return 'is-untested'
}

// A model is "local" only when its runtime says so; everything else is API.
export function runtimeLabel(model) {
  return model.runtime === 'local' ? 'Local' : 'API'
}

export function typeLabel(model) {
  return model.model_type === 'embedding' ? 'Embedding' : 'LLM'
}
