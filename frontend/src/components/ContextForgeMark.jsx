// The ContextForge brand mark: a knowledge stack (three faceted bars) on a
// gradient badge with a spark accent. Pure inline SVG so it scales crisply at
// any size and needs no network request.

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
          <stop offset="0%" stopColor="#8F87ED" />
          <stop offset="100%" stopColor="#332C77" />
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
