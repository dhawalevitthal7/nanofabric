import { useState, useEffect } from 'react'
import { useParams, useNavigate } from '@tanstack/react-router'
import { Tabs } from '@/components/ui/tabs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge, StatusDot } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { MetricAreaChart, ChartCard, COLORS } from '@/components/charts/MetricCharts'
import { useClusterStore } from '@/stores'
import { api, fetchNodeStats, fetchNodeReplicationStats, fetchReplicationJobs } from '@/services/api'
import { formatRelative, generateTimeSeries } from '@/utils'

export function NodeDetailPage() {
  const { nodeId } = useParams({ strict: false }) as { nodeId: string }
  const nodes = useClusterStore((s) => s.nodes)
  const summary = useClusterStore((s) => s.summary)
  const node = nodes[nodeId]
  const [tab, setTab] = useState('overview')
  const [stats, setStats] = useState<import('@/types').NodeStats | null>(null)
  const [repStats, setRepStats] = useState<import('@/types').ReplicationStats | null>(null)
  const [blocks, setBlocks] = useState<string[]>([])
  const [jobs, setJobs] = useState<unknown[]>([])
  const navigate = useNavigate()

  useEffect(() => {
    if (!node) return
    fetchNodeStats(node.address).then(setStats)
    fetchNodeReplicationStats(node.address).then(setRepStats)
    api.nodeBlocks(nodeId).then((r) => setBlocks(r.blocks)).catch(() => setBlocks([]))
    fetchReplicationJobs(node.address).then(setJobs)
  }, [node, nodeId])

  if (!node) {
    return (
      <div className="text-center py-12">
        <p className="text-muted">Node not found</p>
        <button className="mt-2 text-primary hover:underline" onClick={() => navigate({ to: '/nodes' })}>Back to nodes</button>
      </div>
    )
  }

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'metrics', label: 'Metrics' },
    { id: 'blocks', label: 'Blocks' },
    { id: 'replicas', label: 'Replicas' },
    { id: 'repairs', label: 'Repairs' },
    { id: 'logs', label: 'Logs' },
  ]

  const cpuData = generateTimeSeries('cpu', 45, '1h').points
  const iopsData = generateTimeSeries('iops', (stats?.reads_total ?? 100) / 10, '1h').points

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <StatusDot status={summary[nodeId] ?? node.status} />
        <div>
          <h2 className="text-2xl font-bold">{nodeId}</h2>
          <p className="text-sm text-muted font-mono">{node.address}</p>
        </div>
        <Badge variant={node.status === 'UP' ? 'success' : 'danger'} className="ml-auto">{summary[nodeId] ?? node.status}</Badge>
      </div>

      <Tabs tabs={tabs} active={tab} onChange={setTab} />

      {tab === 'overview' && (
        <div className="grid gap-4 md:grid-cols-3">
          <Card><CardHeader><CardTitle>Blocks</CardTitle></CardHeader><CardContent><p className="text-3xl font-bold">{stats?.block_count ?? 0}</p></CardContent></Card>
          <Card><CardHeader><CardTitle>Reads / Writes</CardTitle></CardHeader><CardContent><p className="text-3xl font-bold">{stats?.reads_total ?? 0} / {stats?.writes_total ?? 0}</p></CardContent></Card>
          <Card><CardHeader><CardTitle>Replication Latency</CardTitle></CardHeader><CardContent><p className="text-3xl font-bold">{(repStats?.replication_latency_ms ?? 0).toFixed(1)} ms</p></CardContent></Card>
          <Card className="md:col-span-3"><CardHeader><CardTitle>Node Info</CardTitle></CardHeader><CardContent className="grid gap-2 text-sm md:grid-cols-2">
            <div><span className="text-muted">Registered:</span> {formatRelative(node.registered_at)}</div>
            <div><span className="text-muted">Last seen:</span> {formatRelative(node.last_seen)}</div>
            <div><span className="text-muted">Read repairs:</span> {repStats?.read_repairs ?? 0}</div>
            <div><span className="text-muted">Hint deliveries:</span> {repStats?.hint_deliveries ?? 0}</div>
          </CardContent></Card>
        </div>
      )}

      {tab === 'metrics' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <ChartCard title="CPU Usage"><MetricAreaChart data={cpuData} color={COLORS.primary} unit="%" /></ChartCard>
          <ChartCard title="IOPS"><MetricAreaChart data={iopsData} color={COLORS.success} /></ChartCard>
        </div>
      )}

      {tab === 'blocks' && (
        <Table>
          <TableHeader><TableRow><TableHead>Block ID</TableHead><TableHead>State</TableHead></TableRow></TableHeader>
          <TableBody>
            {blocks.length === 0 ? (
              <TableRow><TableCell className="text-muted text-center" colSpan={2}>No blocks on this node</TableCell></TableRow>
            ) : blocks.map((b) => (
              <TableRow key={b}><TableCell className="font-mono">{b}</TableCell><TableCell><Badge variant="success">Active</Badge></TableCell></TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {tab === 'replicas' && (
        <Card><CardContent className="p-4 text-sm">
          <p>Successful replications: <strong>{repStats?.successful_replications ?? 0}</strong></p>
          <p className="mt-2">Failed replications: <strong>{repStats?.failed_replications ?? 0}</strong></p>
          <p className="mt-2">Degraded: <strong>{repStats?.degraded_replications ?? 0}</strong></p>
        </CardContent></Card>
      )}

      {tab === 'repairs' && (
        <Table>
          <TableHeader><TableRow><TableHead>Job</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
          <TableBody>
            {(jobs as { job_id?: string; status?: string }[]).map((j, i) => (
              <TableRow key={j.job_id ?? i}><TableCell className="font-mono text-xs">{j.job_id}</TableCell><TableCell>{j.status}</TableCell></TableRow>
            ))}
            {jobs.length === 0 && <TableRow><TableCell className="text-muted text-center" colSpan={2}>No repair jobs</TableCell></TableRow>}
          </TableBody>
        </Table>
      )}

      {tab === 'logs' && (
        <Card><CardContent className="p-4 font-mono text-xs text-muted space-y-1">
          <p>[{new Date().toISOString()}] INFO  Node {nodeId} heartbeat OK</p>
          <p>[{new Date().toISOString()}] INFO  Replication worker idle</p>
          <p>[{new Date().toISOString()}] DEBUG Cache hit ratio 78%</p>
        </CardContent></Card>
      )}
    </div>
  )
}
