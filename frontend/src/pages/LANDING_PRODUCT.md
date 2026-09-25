# ContextForge — Landing Design Direction

Design-direction record for `frontend/src/pages/LandingPage.jsx`, per the
`frontend-design-direction` skill. Read this before changing the landing page.

## 1 · Purpose

The landing page has one job: **prove that ContextForge is a grounded, local-first
RAG workspace** in the first viewport, then hand the operator a working entry point.
It is not vague marketing — every section carries inspectable product substance
(real pipeline stages, real capability surfaces, real configuration facts).

## 2 · Audience

Engineers, technical founders, and RAG/agent builders who are evaluating whether
ContextForge is worth self-hosting. They scan for:

1. What it does (grounded answers, not a chatbot).
2. What it ingests (PDF · DOCX · Web · YouTube · GitHub · Text).
3. Whether it is real (hybrid retrieval, RRF, reranking, repo intelligence).
4. How they hold it (local-first, own hardware, cited answers).

## 3 · Tone

**Technical editorial.** Dense-but-legible, terminal-adjacent, calm. Not playful,
not maximal. The visual language borrows from the repo's own product: monospace
metadata labels, subdued hairline strokes, restrained motion.

## 4 · Memorable detail

A **live, animated retrieval trace** in the hero: numbered pipeline rails
(`HyDE → Hybrid → RRF → Rerank → Prompt → LLM`) that sequentially resolve
while a grounded answer card types out with inline citation chips. This is the
product's actual query pipeline — the memorable detail *is* the product.

## 5 · Constraints

- Framework: React 19 + Vite 8 + Tailwind v4. No new dependencies.
- Reuse existing tokens in `styles/main.css` (`--accent`, `--bg`, `--panel`,
  `--stroke`, `--radius`, `--ease`, `--shadow-*`) and the repo's fonts
  (Space Grotesk / Space Mono).
- Accessibility: semantic landmarks, real `<a>`/`<button>`, visible focus rings,
  `aria-hidden` on decorative SVG, `prefers-reduced-motion` respected.
- Motion must be high-signal (clarifies pipeline state), never decorative.
- Responsive with **stable dimensions** for rails, cards, and counters.

## 6 · Anti-patterns explicitly avoided

- No purple gradient hero, no decorative blobs, no stock atmospheric media.
- No cards-inside-cards.
- No oversized vague hero copy; the product's real capability is the headline.
- No describing features that the UI could show instead.

## Route

`/` renders the landing page (marketing entry) with a primary **Open workspace**
CTA to `/workspace`, which hosts the existing working RAG interface.
