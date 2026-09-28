import { useMemo } from 'react'

// The service graph.
//
// A flat list of technologies answers "what does this repository depend on".
// It does not answer the question a monorepo actually raises, which is where the
// services are and what connects them: that `web` calls `billing`, that `api`
// talks to Postgres, and that all of it is deployed to Vercel.  The scan returns
// that as a tree of services with edges and containing components, and this
// renders it as a nested outline.
//
// The tree is drawn as nested lists rather than a canvas or a diagram library so
// it stays readable, selectable and keyboard-navigable, and so it needs no
// layout pass to be correct.  Edges are shown on the service that owns them,
// which keeps the relationship next to the thing it belongs to.

function ServiceNode({ node, nameById }) {
  const services = (node.childs || []).filter((child) => child.node_type === 'service')

  // Everything a service reaches.  The backend has already decided what counts
  // as a component -- a database or an AI vendor is something a service calls,
  // a framework is a property of the service -- so nothing is filtered again
  // here, or an unrecognised category would silently vanish from the graph.
  //
  // A component nested under this service and an edge pointing at one shared
  // with another service are the same thing shown two ways, so a target that is
  // already nested is not also listed as a link.
  const nested = new Map(
    (node.childs || []).filter((child) => child.node_type === 'component').map((child) => [child.id, child.name]),
  )
  const connections = [
    ...nested,
    ...(node.edges || [])
      .filter((edge) => !nested.has(edge.target))
      .map((edge) => [edge.target, nameById.get(edge.target) || edge.target]),
  ]
  const libraries = node.techs || []

  return (
    <li className="ts-graph-node">
      <div className="ts-graph-row">
        <span className="ts-graph-name" title={node.path?.length ? node.path.join('/') : undefined}>
          {node.name}
        </span>
        {node.manifests?.length ? (
          <span className="ts-graph-meta">
            {node.manifests.length} manifest{node.manifests.length === 1 ? '' : 's'}
          </span>
        ) : null}
        {node.in_component ? (
          <span className="ts-graph-host" title="Hosted by">
            hosted by <strong>{nameById.get(node.in_component) || node.in_component}</strong>
          </span>
        ) : null}
      </div>

      {connections.length ? (
        <div className="ts-graph-links">
          {connections.map(([id, name]) => (
            <span key={id} className="ts-graph-link">
              {name}
            </span>
          ))}
        </div>
      ) : null}

      {libraries.length ? (
        <p className="ts-graph-libs">
          {libraries.length} technolog{libraries.length === 1 ? 'y' : 'ies'}
          {libraries.length <= 3 ? `: ${libraries.map((t) => t.name).join(', ')}` : ''}
        </p>
      ) : null}

      {services.length ? (
        <ul className="ts-graph-children">
          {services.map((child) => (
            <ServiceNode key={child.id} node={child} nameById={nameById} />
          ))}
        </ul>
      ) : null}
    </li>
  )
}

export default function ServiceGraph({ graph }) {
  const nameById = useMemo(() => {
    const names = new Map()
    // Components are listed flat by the scan; services carry their own name.
    ;(graph?.components || []).forEach((node) => names.set(node.id, node.name))
    ;(graph?.services || []).forEach((node) => names.set(node.id, node.name))
    return names
  }, [graph])

  if (!graph?.services?.length) return null

  const roots = graph.services.filter((service) => !service.path?.length)
  const nested = graph.services.filter((service) => service.path?.length && !isNestedIn(graph, service))
  const shown = roots.length ? roots : nested

  return (
    <section className="ts-section">
      <h4 className="ts-section-title">
        {graph.monorepo ? 'Services and what they connect to' : 'Service and what it connects to'}
      </h4>
      <p className="ts-note">
        {graph.service_count} service{graph.service_count === 1 ? '' : 's'}
        {graph.service_truncated && graph.service_total > graph.service_count
          ? ` of ${graph.service_total} found`
          : ''}{' '}
        · {graph.component_count} connected component{graph.component_count === 1 ? '' : 's'} ·{' '}
        {graph.edge_count} connection{graph.edge_count === 1 ? '' : 's'}
        {graph.monorepo ? '' : ' · single-service repository'}
      </p>
      {graph.service_truncated && graph.service_total > graph.service_count ? (
        <p className="ts-note">
          This monorepo has {graph.service_total} manifest folders. The graph shows the {graph.service_count}{' '}
          outermost, which is where the connections are.
        </p>
      ) : null}
      <ul className="ts-graph">
        {shown.map((service) => (
          <ServiceNode key={service.id} node={service} nameById={nameById} />
        ))}
      </ul>
    </section>
  )
}

// A service is nested when another service's folder path is a prefix of its own.
// A repository whose only manifest sits in `services/api` has no root service, so
// its top-level services are shown rather than nothing at all.
function isNestedIn(graph, service) {
  const own = service.path || []
  return (graph.services || []).some(
    (other) => other.id !== service.id && (other.path || []).length < own.length && own.slice(0, (other.path || []).length).join('/') === (other.path || []).join('/'),
  )
}
