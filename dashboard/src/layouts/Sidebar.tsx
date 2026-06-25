import { Link, useRouterState } from '@tanstack/react-router'
import { motion } from 'framer-motion'
import {
  LayoutDashboard,
  Server,
  Network,
  MapPin,
  Copy,
  ShieldCheck,
  HardDrive,
  Database,
  Camera,
  Archive,
  Wrench,
  Briefcase,
  Bell,
  Calendar,
  BarChart3,
  Gauge,
  FileText,
  GitBranch,
  Users,
  Settings,
  Key,
  ScrollText,
  ChevronLeft,
  ChevronRight,
  Activity,
} from 'lucide-react'
import { cn } from '@/utils'
import { useUiStore, useClusterStore } from '@/stores'
import { StatusDot } from '@/components/ui/badge'

interface NavItem {
  label: string
  path: string
  icon: React.ElementType
}

interface NavSection {
  title?: string
  items: NavItem[]
}

const navigation: (NavItem | NavSection)[] = [
  { label: 'Dashboard', path: '/', icon: LayoutDashboard },
  {
    title: 'CLUSTER',
    items: [
      { label: 'Nodes', path: '/nodes', icon: Server },
      { label: 'Topology', path: '/topology', icon: Network },
      { label: 'Placement', path: '/placement', icon: MapPin },
      { label: 'Replication', path: '/replication', icon: Copy },
      { label: 'Consistency', path: '/consistency', icon: ShieldCheck },
    ],
  },
  {
    title: 'STORAGE',
    items: [
      { label: 'Blocks', path: '/blocks', icon: HardDrive },
      { label: 'Capacity', path: '/capacity', icon: Database },
      { label: 'Snapshots', path: '/snapshots', icon: Camera },
      { label: 'Backups', path: '/backups', icon: Archive },
    ],
  },
  {
    title: 'OPERATIONS',
    items: [
      { label: 'Repairs', path: '/repairs', icon: Wrench },
      { label: 'Jobs', path: '/jobs', icon: Briefcase },
      { label: 'Alerts', path: '/alerts', icon: Bell },
      { label: 'Events', path: '/events', icon: Calendar },
    ],
  },
  {
    title: 'OBSERVABILITY',
    items: [
      { label: 'Metrics', path: '/metrics', icon: BarChart3 },
      { label: 'Performance', path: '/performance', icon: Gauge },
      { label: 'Logs', path: '/logs', icon: FileText },
      { label: 'Traces', path: '/traces', icon: GitBranch },
    ],
  },
  {
    title: 'SYSTEM',
    items: [
      { label: 'Users', path: '/users', icon: Users },
      { label: 'Settings', path: '/settings', icon: Settings },
      { label: 'API Keys', path: '/api-keys', icon: Key },
      { label: 'Audit Logs', path: '/audit', icon: ScrollText },
    ],
  },
]

function isSection(item: NavItem | NavSection): item is NavSection {
  return 'items' in item
}

export function Sidebar() {
  const collapsed = useUiStore((s) => s.sidebarCollapsed)
  const toggle = useUiStore((s) => s.toggleSidebar)
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const connected = useClusterStore((s) => s.connected)
  const overview = useClusterStore((s) => s.overview)

  return (
    <motion.aside
      animate={{ width: collapsed ? 64 : 240 }}
      transition={{ duration: 0.2 }}
      className="flex h-full flex-col border-r border-border bg-card/40 backdrop-blur-xl"
    >
      <div className="flex h-14 items-center gap-2 border-b border-border px-4">
        <Activity className="h-6 w-6 shrink-0 text-primary" />
        {!collapsed && (
          <div className="overflow-hidden">
            <p className="text-sm font-bold tracking-tight">NanoFabric</p>
            <p className="text-[10px] text-muted">Cluster Console</p>
          </div>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto p-2" aria-label="Main navigation">
        {navigation.map((item, i) => {
          if (isSection(item)) {
            return (
              <div key={i} className="mb-3">
                {!collapsed && (
                  <p className="mb-1 px-3 text-[10px] font-semibold tracking-widest text-muted">{item.title}</p>
                )}
                {item.items.map((nav) => (
                  <NavLink key={nav.path} item={nav} active={pathname === nav.path || pathname.startsWith(nav.path + '/')} collapsed={collapsed} />
                ))}
              </div>
            )
          }
          return <NavLink key={item.path} item={item} active={pathname === item.path} collapsed={collapsed} />
        })}
      </nav>

      <div className="border-t border-border p-3">
        {!collapsed && (
          <div className="mb-2 flex items-center gap-2 rounded-lg bg-background/50 px-2 py-1.5 text-xs">
            <StatusDot status={connected ? 'healthy' : 'degraded'} />
            <span>{connected ? 'Live' : 'Polling'}</span>
            {overview && (
              <span className="ml-auto capitalize text-muted">{overview.health}</span>
            )}
          </div>
        )}
        <button
          onClick={toggle}
          className="flex w-full items-center justify-center rounded-lg p-2 text-muted hover:bg-card hover:text-foreground"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>
    </motion.aside>
  )
}

function NavLink({ item, active, collapsed }: { item: NavItem; active: boolean; collapsed: boolean }) {
  const Icon = item.icon
  return (
    <Link
      to={item.path}
      className={cn(
        'mb-0.5 flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
        active ? 'bg-primary/15 text-primary font-medium' : 'text-muted hover:bg-card/80 hover:text-foreground',
        collapsed && 'justify-center px-2',
      )}
      title={collapsed ? item.label : undefined}
      aria-current={active ? 'page' : undefined}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {!collapsed && <span>{item.label}</span>}
    </Link>
  )
}
