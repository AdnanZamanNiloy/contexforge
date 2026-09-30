// The ContextForge brand mark: a knowledge stack (three faceted bars) on a
// gradient badge with a spark accent. Pure inline SVG so it scales crisply at
// any size and needs no network request.
//
// The gradient carries the workspace's own blue rather than the violet the mark
// originally shipped with — the sidebar, the buttons and the mind map all read
// blue, and a violet badge beside them looked like a different product.  The two
// stops keep the original light-to-deep relationship, so the plate still has
// depth: --primary-soft into --primary-deep.  These are the literal hex values
// of those tokens, because SVG gradient stops cannot read a CSS variable from a
// stylesheet at this call site; keep them in step with main.css.

const GRAD_ID = 'cf-mark-badge'

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
      viewBox="0 0 140 140"
      fill="none"
      role="img"
      aria-label={title}
    >
      <defs>
        <linearGradient id={GRAD_ID} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#6b92ff" />
          <stop offset="100%" stopColor="#2f5fe0" />
        </linearGradient>
      </defs>

      {withPlate && <rect x="0" y="0" width="140" height="140" rx="32" fill={`url(#${GRAD_ID})`} />}

      <rect x="30" y="34" width="80" height="16" rx="4" fill="#FFFFFF" />
      <rect x="57" y="50" width="26" height="34" rx="3" fill="#FFFFFF" />
      <rect x="38" y="84" width="64" height="20" rx="4" fill="#FFFFFF" />
      <rect
        x="112"
        y="16"
        width="16"
        height="16"
        rx="3"
        fill="#EF9F27"
        transform="rotate(45 120 24)"
      />
    </svg>
  )
}
