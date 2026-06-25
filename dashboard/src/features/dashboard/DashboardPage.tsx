import {
  Activity,
  HardDrive,
  Database,
  Layers,
  Copy,
  Server,
  AlertTriangle,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { StatCard } from '@/components/StatCard'
import { ClusterTopology } from '@/components/ClusterTopology'
import {
  ChartCard,
  MetricAreaChart,
  MetricLineChart,
  DonutChart,
  TimeRangeSelector,
  COLORS,
} from '@/components/charts/MetricCharts'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { useClusterStore, useMetricsStore, useRepairStore, useAlertStore } from '@/stores'
import { formatBytes, formatNumber, formatRelative, generateTimeSeries, type TimeRange } from '@/utils'

export function DashboardPage() {
  const overview = useClusterStore((s) => s.overview)
  const health = useClusterStore((s) => s.health)
  const history = useMetricsStore((s) => s.history)
  const readIops = useMetricsStore((s) => s.readIops)
  const writeIops = useMetricsStore((s) => s.writeIops)
  const latency = useMetricsStore((s) => s.latency)
  const throughput = useMetricsStore((s) => s.throughput)
  const jobs = useRepairStore((s) => s.jobs)
  const alerts = useAlertStore((s) => s.alerts)
  const [capacityRange, setCapacityRange] = useState<TimeRange>('1h')
  const navigate = useNavigate()

  const capacityData = useMemo(() => {
    const used = generateTimeSeries('used', overview?.usedCapacity ? overview.usedCapacity / 1e6 : 500, capacityRange)
    const total = generateTimeSeries('total', overview?.totalCapacity ? overview.totalCapacity / 1e6 : 1000, capacityRange, 60, 0.02)
    return [
      { name: 'Used', data: used.points, color: COLORS.primary },
      { name: 'Total', data: total.points, color: COLORS.muted },
      { name: 'Available', data: used.points.map((p, i) => ({ timestamp: p.timestamp, value: Math.max(0, (total.points[i]?.value ?? 0) - p.value) })), color: COLORS.success },
    ]
  }, [capacityRange, overview])

  const repHealth = overview?.replicationHealth ?? { healthy: 0, degraded: 0, failed: 0 }

  const displayAlerts = alerts.filter((a) => a.status === 'active').slice(0, 5)
  const syntheticAlerts = useMemo(() => {
    const items = [...displayAlerts]
    if (health?.under_replicated?.length) {
      health.under_replicated.slice(0, 3).forEach((b) => {
        if (!items.find((a) => a.description.includes(b.block_id))) {
          items.push({
            id: `ur-${b.block_id}`,
            severity: 'WARNING',
            node: b.missing_nodes[0] ?? '—',
            description: `Under-replicated block ${b.block_id}`,
            time: Date.now(),
            status: 'active',
          })
        }
      })
    }
    return items.slice(0, 5)
  }, [displayAlerts, health])

  const recentJobs = jobs.slice(0, 5)

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Cluster Overview</h2>
        <p className="text-sm text-muted">Executive dashboard — real-time cluster health and performance</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
        <StatCard title="Cluster Health" value={overview?.health ?? '—'} icon={Activity} status={overview?.health ?? 'default'} index={0} />
        <StatCard title="Total Capacity" value={formatBytes(overview?.totalCapacity ?? 0)} icon={Database} index={1} />
        <StatCard title="Used Capacity" value={formatBytes(overview?.usedCapacity ?? 0)} icon={HardDrive} index={2} />
        <StatCard title="Total Blocks" value={formatNumber(overview?.totalBlocks ?? 0)} icon={Layers} index={3} />
        <StatCard title="Replication Factor" value={overview?.replicationFactor ?? 3} icon={Copy} index={4} />
        <StatCard title="Active Nodes" value={`${overview?.activeNodes ?? 0}/${overview?.totalNodes ?? 0}`} icon={Server} status={overview?.activeNodes === overview?.totalNodes ? 'healthy' : 'degraded'} index={5} />
        <StatCard title="Alerts" value={overview?.alertCount ?? 0} icon={AlertTriangle} status={(overview?.alertCount ?? 0) > 0 ? 'critical' : 'healthy'} index={6} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Cluster Topology">
          <ClusterTopology compact onNodeClick={(id) => navigate({ to: '/nodes/$nodeId', params: { nodeId: id } })} />
        </ChartCard>
        <ChartCard
          title="Capacity"
          action={<TimeRangeSelector value={capacityRange} onChange={setCapacityRange} />}
        >
          <MetricLineChart series={capacityData} height={240} />
        </ChartCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <ChartCard title="Replication Health">
          <DonutChart
            data={[
              { name: 'Healthy', value: repHealth.healthy, color: COLORS.success },
              { name: 'Degraded', value: repHealth.degraded, color: COLORS.warning },
              { name: 'Failed', value: repHealth.failed, color: COLORS.danger },
            ]}
          />
        </ChartCard>
        <ChartCard title="Read / Write IOPS" className="lg:col-span-2">
          <MetricLineChart
            height={200}
            series={[
              { name: 'Read', data: history.readIops ?? [{ timestamp: Date.now(), value: readIops }], color: COLORS.primary },
              { name: 'Write', data: history.writeIops ?? [{ timestamp: Date.now(), value: writeIops }], color: COLORS.success },
            ]}
          />
        </ChartCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Latency (ms)">
          <MetricAreaChart data={history.latency ?? [{ timestamp: Date.now(), value: latency }]} color={COLORS.warning} unit="ms" />
        </ChartCard>
        <ChartCard title="Throughput (MB/s)">
          <MetricAreaChart data={history.throughput ?? [{ timestamp: Date.now(), value: throughput }]} color={COLORS.success} unit=" MB/s" />
        </ChartCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Active Alerts">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Severity</TableHead>
                <TableHead>Node</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Time</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {syntheticAlerts.length === 0 ? (
                <TableRow>
                  <TableCell className="text-muted text-center" colSpan={5}>No active alerts</TableCell>
                </TableRow>
              ) : (
                syntheticAlerts.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell>
                      <Badge variant={a.severity === 'CRITICAL' ? 'danger' : a.severity === 'WARNING' ? 'warning' : 'info'}>
                        {a.severity}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{a.node}</TableCell>
                    <TableCell className="max-w-[200px] truncate">{a.description}</TableCell>
                    <TableCell className="text-xs text-muted">{formatRelative(a.time)}</TableCell>
                    <TableCell><Badge variant="outline">{a.status}</Badge></TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </ChartCard>

        <ChartCard title="Repair Jobs">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Job ID</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Block</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Progress</TableHead>
                <TableHead>Started</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recentJobs.length === 0 ? (
                <TableRow>
                  <TableCell className="text-muted text-center" colSpan={6}>No repair jobs</TableCell>
                </TableRow>
              ) : (
                recentJobs.map((j) => (
                  <TableRow key={j.job_id}>
                    <TableCell className="font-mono text-xs">{j.job_id.slice(0, 8)}</TableCell>
                    <TableCell className="text-xs">{j.repair_type}</TableCell>
                    <TableCell className="font-mono text-xs">{j.block_id}</TableCell>
                    <TableCell>
                      <Badge variant={j.status === 'COMPLETED' ? 'success' : j.status === 'FAILED' ? 'danger' : 'warning'}>
                        {j.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs">
                      {j.status === 'COMPLETED' ? '100%' : j.status === 'COPYING' ? '50%' : j.status === 'VERIFYING' ? '80%' : '—'}
                    </TableCell>
                    <TableCell className="text-xs text-muted">{formatRelative(j.created_at)}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </ChartCard>
      </div>
    </div>
  )
}
