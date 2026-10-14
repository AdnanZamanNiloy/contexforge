# ContextForge Docs

The documentation website for ContextForge, styled after
[openscience.sh/docs](https://www.openscience.sh/docs): a persistent sidebar, a
top bar with ⌘K search, markdown rendering with heading anchors, and an
"On this page" table of contents.

The colour tokens in `src/index.css` mirror the main app's Voltagent palette
(`frontend/src/styles/main.css`) so both surfaces share the exact same black.
Like the app, the site is dark-only: `color-scheme: dark` is declared and the
background is painted inline in `index.html` before the bundle loads, so
navigating to the docs never flashes white.

## Run it

```bash
cd docs-site
npm install
npm run dev        # http://localhost:5174
```

```bash
npm run build      # static output in docs-site/dist
npm run preview    # preview the production build
```

## Editing content

Documentation lives as plain markdown in `src/content/md/`. Each file maps to a
slug in `src/nav.js` and `src/content/registry.js`:

- **`src/nav.js`** — sidebar groups and ordering.
- **`src/content/registry.js`** — imports each `.md` with Vite's `?raw` and
  registers its title and group.

To add a page: drop a `my-page.md` in `src/content/md/`, add a matching entry to
`nav.js`, and register it in `registry.js`. Markdown supports GFM (tables, task
lists, strikethrough) and gets stable heading ids for deep links.

## Deploy

A `Dockerfile` and `nginx.conf` are included for serving the static build with a
SPA fallback:

```bash
docker build -t contextforge-docs .
docker run -p 8080:80 contextforge-docs
```

Or serve `dist/` from any static host. Since routing is client-side, configure a
catch-all rewrite to `index.html`.
