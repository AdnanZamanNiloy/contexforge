// Shared source representation for ContextForge.  Every capability in the
// product — the workspace, source exploration, chat, mind maps and Repository
// Intelligence — speaks the same source model so a YouTube video, a PDF, a web
// page and a GitHub repository all present identically and feel native to the
// same knowledge layer.

export const SOURCE_TYPE_LABEL = {
  pdf: 'PDF',
  docx: 'DOCX',
  web: 'Web',
  github: 'GitHub',
  youtube: 'YouTube',
  text: 'Text',
};

export const SOURCE_STATUS = {
  indexed: { label: 'Indexed', dot: 'status-dot is-indexed' },
  processing: { label: 'Processing', dot: 'status-dot is-processing' },
  failed: { label: 'Failed', dot: 'status-dot is-failed' },
};

// The GitHub octocat mark is reused everywhere a repository is represented.
export function GithubMark({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z" />
    </svg>
  );
}

export function FileMark({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  );
}

export function GlobeMark({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

export function YoutubeMark({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="2" y="4" width="20" height="16" rx="4" fill="#FF0000" />
      <path d="M10 9l6 3-6 3z" fill="#FFFFFF" />
    </svg>
  );
}

export function PdfMark({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="2" y="2" width="20" height="20" rx="4" fill="#EF4444" />
      <rect x="2" y="2" width="13" height="7" rx="4" fill="#DC2626" />
      <text x="12" y="16" textAnchor="middle" fill="white" fontSize="7.5" fontWeight="bold" fontFamily="Arial,sans-serif">PDF</text>
    </svg>
  );
}

// A single, canonical source glyph so a source reads the same in the source
// list, the evidence rail and the explore header.
export function SourceGlyph({ type, size = 16 }) {
  switch (type) {
    case 'pdf':
    case 'docx':
      return <PdfMark size={size} />;
    case 'web':
      return <GlobeMark size={size} />;
    case 'github':
      return <GithubMark size={size} />;
    case 'youtube':
      return <YoutubeMark size={size} />;
    default:
      return <FileMark size={size} />;
  }
}

export function sourceIconClass(type) {
  switch (type) {
    case 'pdf': return 'source-item-icon is-pdf';
    case 'web': return 'source-item-icon is-web';
    case 'github': return 'source-item-icon is-github';
    case 'youtube': return 'source-item-icon is-youtube';
    default: return 'source-item-icon';
  }
}

export function chunkIconClass(type) {
  switch (type) {
    case 'pdf': return 'chunk-icon is-pdf';
    case 'web': return 'chunk-icon is-web';
    case 'github': return 'chunk-icon is-github';
    case 'youtube': return 'chunk-icon is-youtube';
    default: return 'chunk-icon';
  }
}

export function formatFileSize(bytes) {
  if (!bytes) return '0 KB';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

// Single source-meta formatter shared by the sidebar list and everywhere a
// source is summarised.
export function formatSourceMeta(source) {
  switch (source.type) {
    case 'pdf':
    case 'docx':
      return `PDF • ${formatFileSize(source.size)}`;
    case 'web':
      return `Web • ${source.date ? new Date(source.date).toLocaleDateString('en-GB') : ''}`;
    case 'github':
      return `GitHub Repo • ${source.chunks || 0} files`;
    case 'youtube':
      return `YouTube • ${source.author || 'Video'}`;
    default:
      return `${(source.type || 'source').toUpperCase()} • ${source.chunks || 0} items`;
  }
}

export function formatTypeLabel(type) {
  return SOURCE_TYPE_LABEL[type] || String(type || 'source').toUpperCase();
}

// Normalise a bare API source record into the shape every view consumes.
export function normalizeSource(raw) {
  return {
    id: raw.source_id,
    type: raw.type || 'unknown',
    title: raw.title || raw.source_id?.slice(0, 12) || 'Unknown source',
    status: 'indexed',
    chunks: raw.chunks || 0,
    url: raw.url || '',
    meta: raw.metadata || {},
  };
}

export function extractDomain(url) {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return null;
  }
}

// Resolve the canonical GitHub repo URL for a source.  Newly indexed repos
// carry `url` in their metadata, but repos indexed before that field existed do
// not — recover those from the `owner/repo` title so Repository Intelligence can
// always be reached from a GitHub source.
export function sourceRepoUrl(source) {
  if (source?.url) return source.url;
  if (source?.type === 'github' && source?.title?.includes('/')) {
    return `https://github.com/${source.title.trim()}`;
  }
  return '';
}
