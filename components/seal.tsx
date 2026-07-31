import { useId } from "react"
import { cn } from "@/lib/utils"

type SealProps = {
  /** pixel size of the square mark */
  size?: number
  /** spin + pulse, for the "thinking" state */
  spinning?: boolean
  className?: string
}

/**
 * The "גילוי נאות" mark: a stamped seal of concentric rings cut by a clear
 * horizontal band (an unredacted line — information being disclosed).
 * Inherits `currentColor`, so colour it with a text-* utility.
 */
export function Seal({ size = 32, spinning = false, className }: SealProps) {
  const maskId = `giluy-band-cut-${useId()}`

  return (
    <svg
      viewBox="0 0 200 200"
      width={size}
      height={size}
      aria-hidden="true"
      className={cn("shrink-0", spinning && "seal-spin", className)}
      style={{ color: "currentColor" }}
    >
      <defs>
        <mask id={maskId}>
          <rect x="0" y="0" width="200" height="200" fill="#fff" />
          <rect x="0" y="82" width="200" height="36" fill="#000" />
        </mask>
      </defs>

      <g mask={`url(#${maskId})`} fill="none" stroke="currentColor">
        <circle cx="100" cy="100" r="94" strokeWidth="7" />
        <circle cx="100" cy="100" r="82" strokeWidth="4" />
        <circle cx="100" cy="100" r="68" strokeWidth="3.4" />
        <circle cx="100" cy="100" r="61" strokeWidth="3.2" />
        <circle cx="100" cy="100" r="54" strokeWidth="3.2" />
        <circle cx="100" cy="100" r="47" strokeWidth="3.2" />
        <circle cx="100" cy="100" r="40" strokeWidth="3.2" />
        <circle cx="100" cy="100" r="33" strokeWidth="3.2" />
        <circle cx="100" cy="100" r="26" strokeWidth="3.2" />
        <circle cx="100" cy="100" r="19" strokeWidth="3.2" />
        <circle cx="100" cy="100" r="12" strokeWidth="3.2" />
      </g>

      <g fill="currentColor">
        <rect x="2" y="82" width="196" height="7" />
        <rect x="2" y="111" width="196" height="7" />
      </g>
    </svg>
  )
}
