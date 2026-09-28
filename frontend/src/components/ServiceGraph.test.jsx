import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import ServiceGraph from './ServiceGraph'

// The service graph view.  The graph itself is built by the backend; these assert
// that the relationships it reports are actually shown, and that the awkward
// shapes — a repository with no root service, a component shared by two
// services — read correctly.

function service(overrides = {}) {
  return {
    id: '.',
    name: 'acme/monorepo',
    path: [],
    tech: null,
    kind: null,
    node_type: 'service',
    techs: [],
    childs: [],
    edges: [],
    in_component: null,
    languages: [],
    manifests: [],
    dependency_count: 0,
    ...overrides,
  }
}

function component(overrides = {}) {
  return service({
    id: '.#postgresql',
    name: 'Postgres',
    tech: 'postgresql',
    kind: 'Database',
    node_type: 'component',
    ...overrides,
  })
}

const GRAPH = {
  services: [
    service({
      childs: [
        service({
          id: 'apps/web',
          name: 'web',
          path: ['apps', 'web'],
          techs: [{ name: 'Next.js', kind: 'UI framework' }],
          manifests: ['apps/web/package.json'],
          in_component: '.#vercel',
        }),
        service({
          id: 'packages/api',
          name: 'api',
          path: ['packages', 'api'],
          techs: [
            { name: 'Postgres', kind: 'Database' },
            { name: 'Fastify', kind: 'Framework' },
          ],
          manifests: ['packages/api/package.json'],
          childs: [component()],
          edges: [{ target: '.#postgresql', read: true, write: true }],
        }),
      ],
    }),
  ],
  components: [component(), component({ id: '.#vercel', name: 'Vercel', tech: 'vercel', kind: 'Hosting' })],
  edges: [
    { from: 'packages/api', to: '.#postgresql', read: true, write: true },
    { from: 'apps/web', to: '.#vercel', read: true, write: true },
  ],
  service_count: 3,
  component_count: 2,
  edge_count: 2,
  monorepo: true,
}

describe('ServiceGraph', () => {
  it('renders nothing when there is no graph', () => {
    const { container } = render(<ServiceGraph graph={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing for a repository with no services', () => {
    const { container } = render(<ServiceGraph graph={{ services: [], components: [] }} />)
    expect(container.firstChild).toBeNull()
  })

  it('nests a service under the repository root', () => {
    const { container } = render(<ServiceGraph graph={GRAPH} />)
    const names = Array.from(container.querySelectorAll('.ts-graph-name')).map((el) => el.textContent)
    expect(names).toEqual(['acme/monorepo', 'web', 'api'])
    // Nesting is real DOM nesting, so the tree is readable to a screen reader.
    expect(container.querySelectorAll('.ts-graph-children .ts-graph-name')).toHaveLength(2)
  })

  it('shows a service connecting to a database as a component chip', () => {
    render(<ServiceGraph graph={GRAPH} />)
    const chips = Array.from(screen.getAllByText('Postgres')).map((el) => el.className)
    expect(chips.some((name) => name.includes('ts-graph-link'))).toBe(true)
  })

  it('shows hosting as a containing component rather than a dependency', () => {
    render(<ServiceGraph graph={GRAPH} />)
    // A hosting provider contains the service rather than being called by it.
    expect(screen.getByText('hosted by')).toBeInTheDocument()
    expect(screen.getByText('Vercel')).toBeInTheDocument()
  })

  it('summarises how many services, components and connections there are', () => {
    const { container } = render(<ServiceGraph graph={GRAPH} />)
    const note = container.querySelector('.ts-section .ts-note').textContent
    expect(note).toContain('3 services')
    expect(note).toContain('2 connected components')
    expect(note).toContain('2 connections')
  })

  it('says a single-service repository is not a monorepo', () => {
    // One service is not a monorepo even when it connects to something, and the
    // section says so rather than implying the repository has several parts.
    const single = {
      ...GRAPH,
      services: [
        service({
          techs: [{ name: 'Django', kind: 'Framework' }],
          manifests: ['requirements.txt'],
          childs: [component()],
          edges: [{ target: '.#postgresql' }],
        }),
      ],
      components: [component()],
      edges: [{ from: '.', to: '.#postgresql' }],
      service_count: 1,
      component_count: 1,
      edge_count: 1,
      monorepo: false,
    }
    const { container } = render(<ServiceGraph graph={single} />)
    expect(screen.getByText(/service and what it connects to/i)).toBeInTheDocument()
    expect(container.querySelector('.ts-section .ts-note').textContent).toContain('single-service repository')
  })

  it('shows top-level services when the repository has no root service', () => {
    // A repository whose only manifest sits in `services/api` has no service at
    // the root, so showing roots alone would render nothing at all.
    const noRoot = {
      ...GRAPH,
      services: [
        service({ id: 'services/api', name: 'api', path: ['services', 'api'], manifests: ['services/api/requirements.txt'] }),
        service({ id: 'services/worker', name: 'worker', path: ['services', 'worker'], manifests: ['services/worker/requirements.txt'] }),
      ],
      service_count: 2,
      monorepo: true,
    }
    const { container } = render(<ServiceGraph graph={noRoot} />)
    const names = Array.from(container.querySelectorAll('.ts-graph-name')).map((el) => el.textContent)
    expect(names).toEqual(['api', 'worker'])
  })

  it('names a shared component even when it is not nested under this service', () => {
    // Two services share one Postgres node; only the first nests it, so the
    // second has to resolve the name from the flat component list.
    const shared = {
      ...GRAPH,
      services: [
        service({
          childs: [
            service({ id: 'services/a', name: 'a', path: ['services', 'a'], edges: [{ target: '.#postgresql' }] }),
            service({
              id: 'services/b',
              name: 'b',
              path: ['services', 'b'],
              childs: [component()],
              edges: [{ target: '.#postgresql' }],
            }),
          ],
        }),
      ],
    }
    const { container } = render(<ServiceGraph graph={shared} />)
    const links = Array.from(container.querySelectorAll('.ts-graph-link')).map((el) => el.textContent)
    // Once as a nested component, once resolved by edge.
    expect(links.filter((label) => label === 'Postgres')).toHaveLength(2)
  })

  it('reports how many technologies a service carries without listing them all', () => {
    // In a monorepo each service's line is what tells them apart, so a service
    // with a long dependency list is counted rather than spelled out.
    const many = {
      ...GRAPH,
      services: [
        service({
          childs: [
            service({
              id: 'apps/big',
              name: 'big',
              path: ['apps', 'big'],
              techs: Array.from({ length: 9 }, (_, i) => ({ name: `lib-${i}`, kind: 'Framework' })),
              manifests: ['apps/big/package.json'],
            }),
          ],
        }),
      ],
    }
    const { container } = render(<ServiceGraph graph={many} />)
    const line = container.querySelector('.ts-graph-libs').textContent
    expect(line).toContain('9 technologies')
    expect(line).not.toContain('lib-0')
  })

  it('spells out a short technology list on the node', () => {
    const { container } = render(<ServiceGraph graph={GRAPH} />)
    const lines = Array.from(container.querySelectorAll('.ts-graph-libs')).map((el) => el.textContent)
    expect(lines.some((line) => line.includes('2 technologies: Postgres, Fastify'))).toBe(true)
  })

  it('shows a manifest count on a service that has one', () => {
    render(<ServiceGraph graph={GRAPH} />)
    // Two services have exactly one manifest each.
    expect(screen.getAllByText('1 manifest')).toHaveLength(2)
  })
})

describe('ServiceGraph truncation', () => {
  const capped = {
    ...GRAPH,
    service_count: 60,
    service_total: 94,
    service_truncated: true,
  }

  it('says how many services were found beyond the cap', () => {
    const { container } = render(<ServiceGraph graph={capped} />)
    const notes = Array.from(container.querySelectorAll('.ts-note')).map((el) => el.textContent)
    expect(notes.some((note) => note.includes('60 services of 94 found'))).toBe(true)
    expect(notes.some((note) => note.includes('94 manifest folders'))).toBe(true)
  })

  it('does not mention truncation when nothing was dropped', () => {
    const { container } = render(<ServiceGraph graph={{ ...GRAPH, service_total: 3, service_truncated: false }} />)
    const notes = Array.from(container.querySelectorAll('.ts-note')).map((el) => el.textContent)
    expect(notes.some((note) => note.includes('manifest folders'))).toBe(false)
  })
})

describe('ServiceGraph component coverage', () => {
  it('shows a component of any category, not only infrastructure ones', () => {
    // A frontend filter on "interesting" categories silently dropped anything not
    // on its list -- an AI vendor a service calls vanished from the graph even
    // though the backend had correctly reported it as a component.
    const withAi = {
      ...GRAPH,
      services: [
        service({
          childs: [
            service({
              id: 'packages/api',
              name: 'api',
              path: ['packages', 'api'],
              childs: [
                component(),
                component({ id: '.#openai', name: 'OpenAI', tech: 'openai', kind: 'AI' }),
                component({ id: '.#stripe', name: 'Stripe', tech: 'stripe', kind: 'Payments' }),
              ],
              edges: [],
            }),
          ],
        }),
      ],
      components: [component()],
    }
    const { container } = render(<ServiceGraph graph={withAi} />)
    const links = Array.from(container.querySelectorAll('.ts-graph-link')).map((el) => el.textContent)
    expect(links).toEqual(['Postgres', 'OpenAI', 'Stripe'])
  })

  it('does not repeat a nested component that also has an edge to it', () => {
    const both = {
      ...GRAPH,
      services: [
        service({
          childs: [
            service({
              id: 'a',
              name: 'a',
              childs: [component()],
              edges: [{ target: '.#postgresql' }],
            }),
          ],
        }),
      ],
      components: [component()],
    }
    const { container } = render(<ServiceGraph graph={both} />)
    const links = Array.from(container.querySelectorAll('.ts-graph-link')).map((el) => el.textContent)
    expect(links).toEqual(['Postgres'])
  })

  it('falls back to the raw target when a component name is unknown', () => {
    const dangling = {
      ...GRAPH,
      services: [
        service({
          childs: [service({ id: 'a', name: 'a', edges: [{ target: '.#unknown' }] })],
        }),
      ],
      components: [],
    }
    const { container } = render(<ServiceGraph graph={dangling} />)
    // Better a visible id than a silently missing relationship.
    expect(container.querySelector('.ts-graph-link').textContent).toBe('.#unknown')
  })
})

describe('ServiceGraph when there is nothing to connect', () => {
  // A plain single-service repository: one manifest, no database client, no
  // infrastructure.  This is the common case, and the section used to render an
  // empty shell reading "0 connected components - 0 connections".
  const BARE = {
    repository: 'acme/django-app',
    services: [
      service({
        name: 'acme/django-app',
        techs: [{ name: 'Django', kind: 'Framework' }],
        manifests: ['requirements.txt'],
      }),
    ],
    components: [],
    edges: [],
    service_count: 1,
    service_total: 1,
    service_truncated: false,
    component_count: 0,
    edge_count: 0,
    monorepo: false,
  }

  it('renders nothing at all for a single service with no connections', () => {
    const { container } = render(<ServiceGraph graph={BARE} />)
    // The technologies list below already names Django, so an empty graph
    // section adds nothing but noise.
    expect(container.firstChild).toBeNull()
  })

  it('renders a single service that does connect to something', () => {
    // A declared Postgres client is exactly what the graph is for, so the
    // section must still appear for one service.
    const withDb = {
      ...BARE,
      services: [
        service({
          name: 'acme/django-app',
          techs: [{ name: 'Django', kind: 'Framework' }, { name: 'Postgres', kind: 'Database' }],
          manifests: ['requirements.txt'],
          childs: [component()],
          edges: [{ target: '.#postgresql' }],
        }),
      ],
      components: [component()],
      component_count: 1,
      edge_count: 1,
    }
    render(<ServiceGraph graph={withDb} />)
    expect(screen.getByText('acme/django-app')).toBeInTheDocument()
    expect(screen.getByText('Postgres')).toBeInTheDocument()
  })

  it('omits the per-service technology line for a single service', () => {
    // With one service the line just repeated the technologies list below it.
    const withDb = {
      ...BARE,
      services: [
        service({
          name: 'acme/django-app',
          techs: [{ name: 'Django', kind: 'Framework' }],
          manifests: ['requirements.txt'],
          childs: [component()],
          edges: [{ target: '.#postgresql' }],
        }),
      ],
      components: [component()],
      component_count: 1,
      edge_count: 1,
    }
    const { container } = render(<ServiceGraph graph={withDb} />)
    expect(container.querySelector('.ts-graph-libs')).toBeNull()
  })

  it('keeps the per-service technology line when services must be told apart', () => {
    render(<ServiceGraph graph={GRAPH} />)
    // In a monorepo the line says which service carries which technologies.
    expect(document.querySelectorAll('.ts-graph-libs').length).toBeGreaterThan(0)
  })

  it('shows a monorepo even when nothing connects yet', () => {
    // Two services and no components is still worth drawing: the shape of the
    // repository is the information.
    const shapeOnly = {
      ...BARE,
      services: [
        service({
          childs: [
            service({ id: 'apps/web', name: 'web', path: ['apps', 'web'], manifests: ['apps/web/package.json'] }),
            service({ id: 'apps/api', name: 'api', path: ['apps', 'api'], manifests: ['apps/api/package.json'] }),
          ],
        }),
      ],
      service_count: 3,
      service_total: 3,
      monorepo: true,
    }
    const { container } = render(<ServiceGraph graph={shapeOnly} />)
    expect(container.querySelector('.ts-graph')).not.toBeNull()
    expect(screen.getByText('web')).toBeInTheDocument()
  })
})
