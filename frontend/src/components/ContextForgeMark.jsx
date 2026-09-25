// The ContextForge brand mark: a faceted "layered anvil" — a knowledge stack
// (faceted cube) seated on a retrieval node, fusing the forge metaphor with
// grounded retrieval. Pure inline SVG so it inherits currentColor, scales
// crisply at any size and needs no network request.

const GRAD_ID = 'cf-mark-face'
const TOP_GRAD_ID = 'cf-mark-top'

export default function ContextForgeMark({
  size = 40,
  title = 'ContextForge',
  withPlate = true,
  className,
}) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      role="img"
      aria-label={title}
    >
      <defs>
        <linearGradient id={GRAD_ID} x1="14" y1="12" x2="50" y2="54" gradientUnits="userSpaceOnUse">
          <stop stopColor="var(--accent-2, #9aa8ff)" />
          <stop offset="1" stopColor="var(--accent, #7aa2f7)" />
        </linearGradient>
        <linearGradient id={TOP_GRAD_ID} x1="16" y1="10" x2="48" y2="30" gradientUnits="userSpaceOnUse">
          <stop stopColor="#c3ccff" />
          <stop offset="1" stopColor="#8fa9f8" />
        </linearGradient>
      </defs>

      {withPlate && (
        <>
          <rect x="3" y="3" width="58" height="58" rx="16" fill="var(--bg, #1a1d23)" />
          <rect
            x="3.75"
            y="3.75"
            width="56.5"
            height="56.5"
            rx="15.25"
            stroke="var(--accent, #7aa2f7)"
            strokeOpacity="0.35"
            strokeWidth="1.5"
          />
        </>
      )}

      {/* knowledge stack — the faceted top of the anvil */}
      <path d="M18 24.5 32 16l14 8.5-14 8.5-14-8.5Z" fill={`url(#${TOP_GRAD_ID})`} />
      <path d="M18 24.5 32 33v7l-14-8.5v-7Z" fill={`url(#${GRAD_ID})`} />
      <path d="M46 24.5 32 33v7l14-8.5v-7Z" fill="var(--accent, #7aa2f7)" fillOpacity="0.72" />

      {/* retrieval paths converging on a grounded source */}
      <path
        d="M23 38.5 32 44l9-5.5"
        stroke="var(--text, #e6e7ea)"
        strokeOpacity="0.9"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="32" cy="46.5" r="3.1" fill="var(--cf-teal, #6fd6c0)" />
      <circle cx="32" cy="46.5" r="6.4" stroke="var(--cf-teal, #6fd6c0)" strokeOpacity="0.4" strokeWidth="1.4" />
    </svg>
  )
}
