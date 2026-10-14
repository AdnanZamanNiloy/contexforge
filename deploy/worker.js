// Cloudflare Worker entry point for the static demo.
//
// The bundle holds two single-page apps under one origin:
//
//   /docs/*   the documentation site (its own React app and client routes)
//   /*        the landing page and the demo workspace
//
// Static assets alone cannot express that. `not_found_handling:
// single-page-application` rewrites every miss to the ROOT index.html, so a
// direct hit on /docs/pipeline would load the app shell and the docs route
// would never resolve. A `_redirects` file cannot express it either: the
// obvious rules — `/docs/* /docs/index.html` and `/* /index.html` — rewrite to
// paths that match their own pattern, and Cloudflare rejects them with
// "Infinite loop detected in this rule".
//
// So the fallback lives here. This Worker runs first (see `run_worker_first`
// in wrangler.jsonc), tries the request against the assets binding, and if no
// file matches, serves the shell for the path: the docs shell under /docs,
// the app shell everywhere else.

const DOCS_PREFIX = '/docs'

// Requests that should never be answered with an HTML shell even when nothing
// matches — a missing asset is a missing asset, and returning a page for it
// would hide a broken build.
const NON_HTML = /\.(?:js|mjs|css|map|png|jpe?g|gif|svg|ico|webp|avif|woff2?|ttf|otf|json|txt|xml|webmanifest)$/i

export default {
  async fetch(request, env) {
    const url = new URL(request.url)

    // Serve the real file when one exists (hashed assets, favicons, the built
    // index.html files themselves).
    const asset = await env.ASSETS.fetch(request)
    if (asset.status !== 404) {
      return asset
    }

    // No file matched. A missing asset must stay a 404 so a broken reference is
    // visible rather than silently replaced with the app shell.
    if (NON_HTML.test(url.pathname)) {
      return asset
    }

    // Choose the shell by path prefix and return its real bytes.
    const shell = url.pathname.startsWith(`${DOCS_PREFIX}/`)
      ? `${DOCS_PREFIX}/index.html`
      : '/index.html'

    const shellResponse = await env.ASSETS.fetch(new URL(shell, url.origin))
    // A missing shell means the build did not emit it; surface that rather than
    // returning an empty 200.
    if (shellResponse.status === 404) {
      return new Response(`Not found: ${shell}`, { status: 404 })
    }
    return shellResponse
  },
}
