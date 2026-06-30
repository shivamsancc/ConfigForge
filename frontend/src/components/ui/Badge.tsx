import type { ReactNode } from 'react'

type Variant = 'success' | 'warning' | 'error' | 'info' | 'neutral'

export function Badge({
  variant = 'neutral',
  children,
}: {
  variant?: Variant
  children: ReactNode
}) {
  return <span className={`badge badge-${variant}`}>{children}</span>
}

export function SeverityBadge({ severity }: { severity: string }) {
  const map: Record<string, Variant> = {
    error: 'error',
    warning: 'warning',
    info: 'info',
    success: 'success',
  }
  return <Badge variant={map[severity] ?? 'neutral'}>{severity}</Badge>
}
