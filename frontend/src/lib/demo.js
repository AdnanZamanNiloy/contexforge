// Whether the app is running as the static demo (Cloudflare build).
//
// The demo ships a fixed, captured set of projects and sources and has no
// backend to write to, so the controls that would create or ingest are disabled
// rather than left to fail with a network error. This is the single place the
// flag is read from the UI; `services/api.js` reads it separately to swap in the
// mock, but components should import this rather than repeat the expression.
export const IS_DEMO = import.meta.env.VITE_DEMO_MODE === 'true'

// Shown as the tooltip on a disabled control so the reason is visible rather
// than the button simply doing nothing.
export const DEMO_DISABLED_HINT =
  'Disabled in the static demo — it runs read-only, with no backend to write to.'
