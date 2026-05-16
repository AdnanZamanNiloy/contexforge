const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

const DEFAULT_TIMEOUT_MS = 25000;

function buildUrl(path) {
  if (!path.startsWith('/')) {
    return `${API_BASE}/${path}`;
  }
  return `${API_BASE}${path}`;
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  try {
    const response = await fetch(buildUrl(path), {
      ...options,
      headers,
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = 'Request failed';
      try {
        const data = await response.json();
        detail = data.detail || data.message || JSON.stringify(data);
      } catch {
        detail = await response.text();
      }
      throw new Error(detail);
    }

    if (response.status === 204) {
      return null;
    }

    return response.json();
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function pingApi() {
  return request('/health', { method: 'GET' });
}

export async function ingestSource(payload) {
  return request('/ingest/source', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function ingestGithub(payload) {
  return request('/github/ingest', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function ingestFile({ source_type, file }) {
  const formData = new FormData();
  formData.append('upload', file);

  const response = await fetch(buildUrl(`/ingest/file?source_type=${source_type}`), {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    let detail = 'Upload failed';
    try {
      const data = await response.json();
      detail = data.detail || data.message || JSON.stringify(data);
    } catch {
      detail = await response.text();
    }
    throw new Error(detail);
  }

  return response.json();
}

export async function queryAnswer(payload) {
  return request('/query', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function streamQuery(payload, handlers = {}) {
  const response = await fetch(buildUrl('/query/stream'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
    signal: handlers.signal,
  });

  if (!response.ok || !response.body) {
    throw new Error('Streaming request failed to start');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      const cleaned = line.replace(/\r$/, '');
      if (!cleaned.startsWith('data:')) {
        continue;
      }
      let data = cleaned.slice(5);
      if (data.startsWith(' ')) {
        data = data.slice(1);
      }
      if (!data) {
        continue;
      }

      if (data.startsWith('[SOURCES]')) {
        const json = data.replace('[SOURCES]', '').trim();
        if (handlers.onSources) {
          try {
            handlers.onSources(JSON.parse(json));
          } catch {
            handlers.onSources([]);
          }
        }
        continue;
      }

      if (data.startsWith('[LATENCY]')) {
        const json = data.replace('[LATENCY]', '').trim();
        if (handlers.onLatency) {
          try {
            handlers.onLatency(JSON.parse(json));
          } catch {
            handlers.onLatency({});
          }
        }
        continue;
      }

      if (data.startsWith('[CONFIDENCE]')) {
        const json = data.replace('[CONFIDENCE]', '').trim();
        if (handlers.onConfidence) {
          try {
            handlers.onConfidence(JSON.parse(json));
          } catch {
            handlers.onConfidence(null);
          }
        }
        continue;
      }

      if (data.startsWith('[ERROR]')) {
        const message = data.replace('[ERROR]', '').trim();
        if (handlers.onError) {
          handlers.onError(message || 'Streaming error');
        }
        continue;
      }

      if (data.startsWith('[DONE]')) {
        if (handlers.onDone) {
          handlers.onDone();
        }
        continue;
      }

      if (handlers.onToken) {
        handlers.onToken(data);
      }
    }
  }
}
