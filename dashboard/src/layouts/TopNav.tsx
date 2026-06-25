import { GlobalSearch } from '@/components/GlobalSearch'
import { AlertCenter } from '@/components/AlertCenter'
import { ThemeToggle } from '@/components/ThemeToggle'
import { StatusDot } from '@/components/ui/badge'
import { useClusterStore } from '@/stores'
export function TopNav() {
  const connected = useClusterStore((s) => s.connected)
  const overview = useClusterStore((s) => s.overview)

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-card/30 px-4 backdrop-blur-xl">
      <div className="flex items-center gap-4">
        <h1 className="text-sm font-medium text-muted hidden lg:block">
          Infrastructure Management Platform
        </h1>
      </div>
      <div className="flex items-center gap-3">
        <GlobalSearch />
        <div className="hidden sm:flex items-center gap-2 rounded-lg border border-border bg-background/40 px-3 py-1.5 text-xs">
          <StatusDot status={connected ? 'healthy' : 'degraded'} />
          <span className="text-muted">Cluster</span>
          <span className="font-medium capitalize">{overview?.health ?? '—'}</span>
        </div>
        <AlertCenter />
        <ThemeToggle />      </div>
    </header>
  )
}
