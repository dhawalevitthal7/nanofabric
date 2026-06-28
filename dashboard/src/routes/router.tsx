import { createRootRoute, createRoute, createRouter, Outlet } from '@tanstack/react-router'
import { AppLayout } from '@/layouts/AppLayout'
import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { NodesPage } from '@/features/nodes/NodesPage'
import { NodeDetailPage } from '@/features/nodes/NodeDetailPage'
import { TopologyPage } from '@/features/topology/TopologyPage'
import { PlacementPage } from '@/features/placement/PlacementPage'
import { ReplicationPage } from '@/features/replication/ReplicationPage'
import { ConsistencyPage } from '@/features/consistency/ConsistencyPage'
import { RepairsPage } from '@/features/repairs/RepairsPage'
import { MetricsPage } from '@/features/metrics/MetricsPage'
import { PerformancePage } from '@/features/metrics/PerformancePage'
import { LogsPage } from '@/features/logs/LogsPage'
import { AlertsPage } from '@/features/alerts/AlertsPage'
import { ControlPlanePage } from '@/features/control-plane/ControlPlanePage'
import { SnapshotsPage } from '@/features/protection/SnapshotsPage'
import { BackupsPage } from '@/features/protection/BackupsPage'
import { RestoreJobsPage, ProtectionPoliciesPage } from '@/features/protection/ProtectionPages'
import { PlaceholderPage } from '@/features/shared/PlaceholderPage'

const rootRoute = createRootRoute({
  component: () => <Outlet />,
})

const layoutRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'layout',
  component: AppLayout,
})

const indexRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/',
  component: DashboardPage,
})

const nodesRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/nodes',
  component: NodesPage,
})

const nodeDetailRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/nodes/$nodeId',
  component: NodeDetailPage,
})

const topologyRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/topology',
  component: TopologyPage,
})

const placementRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/placement',
  component: PlacementPage,
})

const replicationRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/replication',
  component: ReplicationPage,
})

const consistencyRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/consistency',
  component: ConsistencyPage,
})

const repairsRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/repairs',
  component: RepairsPage,
})

const metricsRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/metrics',
  component: MetricsPage,
})

const performanceRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/performance',
  component: PerformancePage,
})

const logsRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/logs',
  component: LogsPage,
})

const alertsRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/alerts',
  component: AlertsPage,
})

const controlPlaneRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/control-plane',
  component: ControlPlanePage,
})

const snapshotsRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/snapshots',
  component: SnapshotsPage,
})

const backupsRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/backups',
  component: BackupsPage,
})

const restoreJobsRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/restore-jobs',
  component: RestoreJobsPage,
})

const protectionPoliciesRoute = createRoute({
  getParentRoute: () => layoutRoute,
  path: '/protection-policies',
  component: ProtectionPoliciesPage,
})

const placeholder = (path: string, title: string, description: string) =>
  createRoute({
    getParentRoute: () => layoutRoute,
    path,
    component: () => <PlaceholderPage title={title} description={description} />,
  })

const routeTree = rootRoute.addChildren([
  layoutRoute.addChildren([
    indexRoute,
    nodesRoute,
    nodeDetailRoute,
    topologyRoute,
    placementRoute,
    replicationRoute,
    consistencyRoute,
    repairsRoute,
    controlPlaneRoute,
    snapshotsRoute,
    backupsRoute,
    restoreJobsRoute,
    protectionPoliciesRoute,
    metricsRoute,
    performanceRoute,
    logsRoute,
    alertsRoute,
    placeholder('/blocks', 'Blocks', 'Block inventory and lifecycle management'),
    placeholder('/capacity', 'Capacity', 'Storage capacity planning and forecasting'),
    placeholder('/jobs', 'Jobs', 'Background job scheduler and history'),
    placeholder('/events', 'Events', 'Cluster event timeline'),
    placeholder('/traces', 'Traces', 'Distributed tracing and request flows'),
    placeholder('/users', 'Users', 'User and role management'),
    placeholder('/settings', 'Settings', 'Cluster configuration'),
    placeholder('/api-keys', 'API Keys', 'API key management'),
    placeholder('/audit', 'Audit Logs', 'Security audit trail'),
  ]),
])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
