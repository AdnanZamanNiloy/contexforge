// Extends Vitest with Testing Library's DOM matchers (toBeInTheDocument, etc.).
import '@testing-library/jest-dom'
import { configure } from '@testing-library/react'

// Testing Library's default async budget is 1000ms. That is fine on an idle
// machine and too tight on a busy one: `userEvent` yields to the event loop
// between every simulated event, so under CPU contention a `waitFor` can miss
// its budget and fail a test whose logic is correct. This showed up as a
// handful of failures across unrelated files — ContextMeter, HealthReport,
// SourceDetailPanel, AddModelTab and others — that all passed on a re-run.
//
// 5000ms does not slow the suite down: `waitFor` returns as soon as the
// condition holds, so the timeout is only ever reached when something is
// genuinely wrong, in which case the failure is worth waiting for.
configure({ asyncUtilTimeout: 5000 })
