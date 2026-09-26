// Regression guard for the sidebar scroll architecture in main.css.
//
// The sidebar broke once because a SECOND `.source-list { display: grid; }`
// rule appeared later in the file and silently overrode the scroller (equal
// specificity, later wins).  These tests fail if the container is ever
// declared more than once or if its scroll properties are removed.
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const cssPath = join(dirname(fileURLToPath(import.meta.url)), 'main.css')
const css = readFileSync(cssPath, 'utf8')

// Ignore comments so commented-out selectors are not counted.
const active = css.replace(/\/\*[\s\S]*?\*\//g, '')

// Top-level single-selector blocks only: no leading whitespace, so indented
// overrides inside @media blocks and compound selectors like
// `.sidebar-shell > *` are intentionally excluded.
const blocks = (selector) =>
  [...active.matchAll(new RegExp(`^${selector}\\s*\\{([^}]*)\\}`, 'gm'))].map((m) => m[1])

describe('sidebar scroll architecture (main.css)', () => {
  it('declares .source-list exactly once', () => {
    expect(blocks('\\.source-list')).toHaveLength(1)
  })

  it('.source-list is the flex scroller (min-height: 0 + overflow-y: auto)', () => {
    const [body] = blocks('\\.source-list')
    expect(body).toMatch(/display:\s*flex/)
    expect(body).toMatch(/min-height:\s*0\b/)
    expect(body).toMatch(/overflow-y:\s*auto/)
    expect(body).toMatch(/flex:\s*1\s+1\s+auto/)
  })

  it('.sources-section is the flexible region that absorbs leftover height', () => {
    const [body] = blocks('\\.sources-section')
    expect(body).toMatch(/min-height:\s*0\b/)
    expect(body).toMatch(/flex:\s*1\s+1\s+auto/)
  })

  it('.sidebar-shell itself never scrolls (header/actions stay pinned)', () => {
    expect(blocks('\\.sidebar-shell')).toHaveLength(1)
    const [body] = blocks('\\.sidebar-shell')
    expect(body).toMatch(/overflow:\s*hidden/)
    expect(body).toMatch(/height:\s*calc\(100vh/)
  })
})
