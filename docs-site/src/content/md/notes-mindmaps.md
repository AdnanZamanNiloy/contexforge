# Notes & mind maps

Turn a selection of sources into something you keep: a structured note or an
interactive diagram.

## Notes

Pick one source or several, and the system writes a structured Markdown note from
their indexed content — the same act as a mind map, in prose instead of a
diagram. The selection is the cache key, so a note is generated once and reused
until the selection changes; `refresh` forces a regeneration.

The prompt is about writing, not summarising: it leads with the point rather than
naming the subject the heading already names, requires a section heading that
carries its argument, and requires three or more discrete things to become a
list. Notes carry **no** `[n]` passage markers.

- `POST /note/generate` — generate or fetch the cached note.
- `GET /note/{key}` — fetch a stored note.
- Output downloadable as `.md`.

## Mind maps

Generate an interactive SVG mind map from any ingested source — or from a
selection of several — with zoom, pan, search, and fullscreen mode.

- `POST /mindmap/generate` — generate or fetch the cached mind map.
- `GET /mindmap/{key}` — fetch a stored mind map.

## One notion of a selection

Notes and mind maps **share** one notion of a selection — a lone source keys by
its own id, several by a sorted composite key — so both features cache side by
side over the same sources. Change the selection and it regenerates.
