import { cn } from '@/utils'

const variants = {
  default: 'bg-border/40 text-foreground',
  success: 'bg-success/15 text-success border border-success/30',
  warning: 'bg-warning/15 text-warning border border-warning/30',
  danger: 'bg-danger/15 text-danger border border-danger/30',
  info: 'bg-primary/15 text-primary border border-primary/30',
  outline: 'border border-border text-muted',
}

interface BadgeProps {
  children: React.ReactNode
  variant?: keyof typeof variants
  className?: string
}

export function Badge({ children, variant = 'default', className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium',
        variants[variant],
        className,
      )}
    >
      {children}
    </span>
  )
}

export function StatusDot({ status }: { status: 'healthy' | 'degraded' | 'critical' | 'UP' | 'DOWN' | string }) {
  const color =
    status === 'healthy' || status === 'UP'
      ? 'bg-success'
      : status === 'degraded' || status === 'WARNING'
        ? 'bg-warning'
        : 'bg-danger'
  return (
    <span className="relative flex h-2 w-2">
      <span className={cn('absolute inline-flex h-full w-full animate-ping rounded-full opacity-40', color)} />
      <span className={cn('relative inline-flex h-2 w-2 rounded-full', color)} />
    </span>
  )
}
