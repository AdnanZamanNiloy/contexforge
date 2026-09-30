// Shared helpers + curated demo content for the Projects library.
//
// Featured templates pair a real photograph with the notebook's subject; the
// `cover` token (aurora / ember / tide / moss / violet / slate) is the gradient
// fallback and drives the abstract artwork behind a user's own projects, which
// have no photograph.
// Featured + Discover entries are static, clearly-labelled example projects —
// they never imply a private user project is publicly visible.

import aiAgentsImage from '../assets/featured/ai-agents.jpg'
import historyOfComputingImage from '../assets/featured/history-of-computing.jpg'
import largeLanguageModelsImage from '../assets/featured/large-language-models.jpg'
import openSourceIntelligenceImage from '../assets/featured/open-source-intelligence.jpg'
import softwareArchitectureImage from '../assets/featured/software-architecture.jpg'

export const COVERS = ['aurora', 'ember', 'tide', 'moss', 'violet', 'slate']

// The three source families a project can focus on.  The choice is made at
// creation and scopes which ingest options the workspace offers.
export const SOURCE_CATEGORIES = [
  {
    id: 'documents',
    label: 'Documents & Web',
    hint: 'PDF, DOCX, TXT, Web URLs',
    icon: 'doc',
  },
  {
    id: 'youtube',
    label: 'YouTube Videos',
    hint: 'YouTube links',
    icon: 'youtube',
  },
  {
    id: 'github',
    label: 'Code Repositories',
    hint: 'GitHub repositories',
    icon: 'github',
  },
]

export function sourceCategoryLabel(id) {
  return SOURCE_CATEGORIES.find((c) => c.id === id)?.label || 'Documents & Web'
}

// Which workspace ingest cards a project scope allows.  Unknown / legacy
// ("all") projects keep every option.
export function ingestScopeFor(sourceCategory) {
  switch (sourceCategory) {
    case 'youtube':
      return ['youtube']
    case 'github':
      return ['github']
    case 'documents':
      return ['files', 'web', 'text']
    default:
      return ['files', 'web', 'github', 'youtube', 'text']
  }
}

// Which Knowledge-Base sidebar rows a project scope allows.  `null` means
// every row (legacy / unscoped projects).  Single-family scopes drop the
// "All Documents" rollup since it would duplicate the only row.
export function sidebarTypesFor(sourceCategory) {
  switch (sourceCategory) {
    case 'youtube':
      return ['youtube']
    case 'github':
      return ['github']
    case 'documents':
      return ['all', 'pdf', 'docx', 'web', 'text']
    default:
      return null
  }
}

export function coverForId(id) {
  if (!id) return 'aurora'
  let hash = 0
  for (let i = 0; i < id.length; i += 1) hash = (hash * 31 + id.charCodeAt(i)) % 997
  return COVERS[hash % COVERS.length]
}

// Library filter pills.
//
// These filter on `source_category`, the family a project was created for,
// rather than on the free-text `category` the user types.  `source_category` is
// set once at creation and is a closed set, which is what makes it usable as a
// row of pills — the free-text field has as many values as the user invented,
// so it can only be a dropdown.
//
// "All" and "Any family" both match everything: a project saved as `all`
// (the legacy default, before families existed) is not scoped to one, so it
// should not disappear from a family filter.
export const FAMILY_FILTERS = [
  { id: 'all', label: 'All', icon: 'all' },
  { id: 'documents', label: SOURCE_CATEGORIES[0].label, icon: 'doc', short: 'Documents' },
  { id: 'youtube', label: SOURCE_CATEGORIES[1].label, icon: 'youtube', short: 'YouTube' },
  { id: 'github', label: SOURCE_CATEGORIES[2].label, icon: 'github', short: 'Repositories' },
]

export function filterByFamily(projects, familyId = 'all') {
  if (!familyId || familyId === 'all') return projects
  return projects.filter((p) => (p.source_category || 'all') === familyId)
}

export function familyLabel(project) {
  const id = project?.source_category || 'all'
  if (id === 'all') return project?.category || 'Uncategorised'
  return SOURCE_CATEGORIES.find((c) => c.id === id)?.label || 'Uncategorised'
}

// Short form for the card badge, where a four-word label will not fit.
export function familyShort(project) {
  const id = project?.source_category || 'all'
  const found = FAMILY_FILTERS.find((f) => f.id === id)
  if (found && found.short) return found.short
  return project?.category || 'Notes'
}

export function timeAgo(iso) {
  if (!iso) return 'Never opened'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'Unknown'
  const diff = Date.now() - then
  const minute = 60 * 1000
  const hour = 60 * minute
  const day = 24 * hour
  const week = 7 * day
  if (diff < hour) {
    const mins = Math.max(1, Math.round(diff / minute))
    if (mins < 2) return 'Updated just now'
    if (mins < 60) return `Updated ${mins} minutes ago`
    return 'Updated 1 hour ago'
  }
  if (diff < 2 * hour) return 'Updated 1 hour ago'
  if (diff < day) return `Updated ${Math.round(diff / hour)} hours ago`
  if (diff < 2 * day) return 'Updated yesterday'
  if (diff < week) return `Updated ${Math.round(diff / day)} days ago`
  if (diff < 2 * week) return 'Updated last week'
  if (diff < 30 * day) return `Updated ${Math.round(diff / week)} weeks ago`
  const months = Math.round(diff / (30 * day))
  if (months < 2) return 'Updated last month'
  if (months < 12) return `Updated ${months} months ago`
  return `Updated ${Math.round(months / 12)} year${Math.round(months / 12) > 1 ? 's' : ''} ago`
}

export function lastOpenedLabel(iso) {
  if (!iso) return 'Never opened'
  const label = timeAgo(iso)
  return label.replace(/^Updated/, 'Opened')
}

// Compact relative time for the library card footer.
//
// The full label ("Opened 59 minutes ago") is 21 characters, and a four-across
// card is ~238px with a 12px meta row — the tail truncated to "Opened 59
// minutes…" on exactly the card a user is most likely to have just opened.
// Units are abbreviated so the whole phrase fits at four-across density.
export function lastOpenedLabelShort(iso) {
  if (!iso) return 'Never opened'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'Unknown'
  const diff = Date.now() - then
  const minute = 60 * 1000
  const hour = 60 * minute
  const day = 24 * hour
  const week = 7 * day
  if (diff < 2 * minute) return 'Opened just now'
  if (diff < hour) return `Opened ${Math.round(diff / minute)}m ago`
  if (diff < day) return `Opened ${Math.round(diff / hour)}h ago`
  if (diff < 2 * day) return 'Opened yesterday'
  if (diff < week) return `Opened ${Math.round(diff / day)}d ago`
  if (diff < 2 * week) return 'Opened last week'
  if (diff < 30 * day) return `Opened ${Math.round(diff / week)}w ago`
  const months = Math.round(diff / (30 * day))
  if (months < 12) return `Opened ${months}mo ago`
  return `Opened ${Math.round(months / 12)}y ago`
}

// Featured templates ship a real photograph per notebook so the cover reads as
// the subject it describes.  `coverImage` is bundled locally (see
// `src/assets/featured/CREDITS.md` for attribution); `cover` remains as the
// gradient fallback and still drives the abstract artwork used for a user's own
// projects, which have no photograph.
export const FEATURED_PROJECTS = [
  {
    id: 'featured-ai-agents',
    title: 'The Future of AI Agents',
    description:
      'Planning, tool use, memory and multi-agent orchestration — the papers and posts shaping autonomous systems.',
    sourceCount: 18,
    updatedAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    provider: 'Curated collection',
    cover: 'aurora',
    coverImage: aiAgentsImage,
    tags: ['AI', 'Agents'],
    featured: true,
  },
  {
    id: 'featured-software-arch',
    title: 'Modern Software Architecture',
    description:
      'Event-driven systems, modular monoliths, platform engineering and the trade-offs behind them.',
    sourceCount: 14,
    updatedAt: new Date(Date.now() - 26 * 60 * 60 * 1000).toISOString(),
    provider: 'Curated collection',
    cover: 'tide',
    coverImage: softwareArchitectureImage,
    tags: ['Architecture'],
    featured: true,
  },
  {
    id: 'featured-llms',
    title: 'Understanding Large Language Models',
    description:
      'Transformers, pretraining, alignment and evaluation — a guided path from first principles to frontier practice.',
    sourceCount: 22,
    updatedAt: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
    provider: 'Curated collection',
    cover: 'violet',
    coverImage: largeLanguageModelsImage,
    tags: ['LLMs', 'Research'],
    featured: true,
  },
  {
    id: 'featured-history-computing',
    title: 'The History of Computing',
    description:
      'From stored programs to the personal computer era — key machines, people and turning points.',
    sourceCount: 11,
    updatedAt: new Date(Date.now() - 8 * 24 * 60 * 60 * 1000).toISOString(),
    provider: 'Curated collection',
    cover: 'ember',
    coverImage: historyOfComputingImage,
    tags: ['History'],
    featured: true,
  },
  {
    id: 'featured-osint',
    title: 'Open Source Intelligence',
    description:
      'Collection methods, verification workflows and case studies for open-source investigation.',
    sourceCount: 9,
    updatedAt: new Date(Date.now() - 12 * 24 * 60 * 60 * 1000).toISOString(),
    provider: 'Curated collection',
    cover: 'moss',
    coverImage: openSourceIntelligenceImage,
    tags: ['OSINT'],
    featured: true,
  },
]

export const DISCOVER_PROJECTS = [
  {
    id: 'discover-crypto',
    title: 'Public-Key Cryptography, Explained',
    description: 'A starter library: RSA, Diffie–Hellman, elliptic curves and what “trust” means.',
    sources: '8 sources',
    cover: 'slate',
  },
  {
    id: 'discover-climate',
    title: 'Climate Systems Primer',
    description: 'Feedback loops, modelling and mitigation pathways in one place.',
    sources: '12 sources',
    cover: 'moss',
  },
  {
    id: 'discover-design',
    title: 'Design Engineering Notes',
    description: 'Typography, spacing systems and interaction patterns that age well.',
    sources: '6 sources',
    cover: 'ember',
  },
]

export const SORT_OPTIONS = [
  { id: 'recent', label: 'Last opened' },
  { id: 'updated', label: 'Last updated' },
  { id: 'name', label: 'Name (A–Z)' },
  { id: 'sources', label: 'Most sources' },
  { id: 'created', label: 'Newest first' },
]

export function sortProjects(projects, sortId) {
  const list = [...projects]
  switch (sortId) {
    case 'name':
      return list.sort((a, b) => (a.name || '').localeCompare(b.name || ''))
    case 'sources':
      return list.sort((a, b) => (b.source_count || 0) - (a.source_count || 0))
    case 'created':
      return list.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
    case 'updated':
      return list.sort((a, b) => new Date(b.updated_at || 0) - new Date(a.updated_at || 0))
    case 'recent':
    default:
      return list.sort(
        (a, b) =>
          new Date(b.last_opened_at || b.updated_at || 0) -
          new Date(a.last_opened_at || a.updated_at || 0),
      )
  }
}

export function filterProjects(projects, { query = '', category = 'all' } = {}) {
  const q = query.trim().toLowerCase()
  return projects.filter((p) => {
    if (category !== 'all' && (p.category || 'General') !== category) return false
    if (!q) return true
    return (
      (p.name || '').toLowerCase().includes(q) ||
      (p.description || '').toLowerCase().includes(q) ||
      (p.category || '').toLowerCase().includes(q)
    )
  })
}
