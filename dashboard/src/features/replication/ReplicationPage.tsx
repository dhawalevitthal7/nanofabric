import { useState, useEffect } from 'react'
import { ChartCard, MetricAreaChart, MetricLineChart, COLORS } from '@/components/charts/MetricCharts'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { useClusterStore } from '@/stores'
import { fetchNodeReplicationStats, fetchReplicationJobs } from '@/services/api'
import { generateTimeSeries } from '@/utils'

export function ReplicationPage() {
  const nodes = useClusterStore((s) => s.nodes)
  const [jobs, setJobs] = useState<unknown[]>([])
  const [failed, setFailed] = useState<unknown[]>([])
  const [stats, setStats] = useState({ latency: 0, throughput: 0, degraded: 0, pending: 0, retries: 0 })

  useEffect(() => {
    const nodeList = Object.values(nodes)
    if (nodeList.length === 0) return

    Promise.all(
      nodeList.map(async (n) => {
        const s = await fetchNodeReplicationStats(n.address)
        const j = await fetchReplicationJobs(n.address)
        return { stats: s, jobs: j }
      }),
    ).then((results) => {
      let latency = 0
      let retries = 0
      let degraded = 0
      const allJobs: { status?: string; job_id?: string; block_id?: string; attempt_count?: number }[] = []
      results.forEach((r) => {
        if (r.stats) {
          latency += r.stats.replication_latency_ms
          retries += r.stats.retry_count
          degraded += r.stats.degraded_replications
        }
        allJobs.push(...(r.jobs as typeof allJobs))
      })
      setStats({
        latency: latency / Math.max(results.length, 1),
        throughput: allJobs.length * 10,
        degraded,
        pending: allJobs.filter((j) => j.status === 'PENDING').length,
        retries,
      })
      setJobs(allJobs.slice(0, 20))
      setFailed(allJobs.filter((j) => j.status === 'FAILED'))
    })
  }, [nodes])

  const latencyData = generateTimeSeries('latency', stats.latency || 5, '1h').points
  const throughputData = generateTimeSeries('throughput', stats.throughput || 50, '1h').points

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Replication</h2>
        <p className="text-sm text-muted">Replication jobs, degraded replicas, and throughput</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-4">
        <Stat label="Pending" value={stats.pending} />
        <Stat label="Degraded" value={stats.degraded} variant="warning" />
        <Stat label="Retry Count" value={stats.retries} />
        <Stat label="Avg Latency" value={`${stats.latency.toFixed(1)} ms`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Replication Latency">
          <MetricAreaChart data={latencyData} color={COLORS.warning} unit="ms" />
        </ChartCard>
        <ChartCard title="Replication Throughput">
          <MetricLineChart series={[{ name: 'Throughput', data: throughputData, color: COLORS.primary }]} />
        </ChartCard>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Job ID</TableHead>
            <TableHead>Block</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Retries</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.length === 0 ? (
            <TableRow><TableCell colSpan={4} className="text-center text-muted">No replication jobs</TableCell></TableRow>
          ) : (
            (jobs as { job_id?: string; block_id?: string; status?: string; attempt_count?: number }[]).map((j, i) => (
              <TableRow key={j.job_id ?? i}>
                <TableCell className="font-mono text-xs">{j.job_id?.slice(0, 12) ?? '—'}</TableCell>
                <TableCell className="font-mono text-xs">{j.block_id}</TableCell>
                <TableCell><Badge variant={j.status === 'FAILED' ? 'danger' : 'info'}>{j.status}</Badge></TableCell>
                <TableCell>{j.attempt_count ?? 0}</TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>

      {failed.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-2">Failed Replications</h3>
          <Table>
            <TableBody>
              {(failed as { block_id?: string; status?: string }[]).map((f, i) => (
                <TableRow key={i}>
                  <TableCell className="font-mono">{f.block_id}</TableCell>
                  <TableCell><Badge variant="danger">{f.status}</Badge></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, variant }: { label: string; value: string | number; variant?: 'warning' }) {
  return (
    <div className="glass rounded-xl p-4">
      <p className="text-xs text-muted uppercase tracking-wider">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${variant === 'warning' ? 'text-warning' : ''}`}>{value}</p>
    </div>
  )
}
