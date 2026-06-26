import { useQuery } from '@tanstack/react-query'
import { StatCard } from '@/components/StatCard'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { api } from '@/services/api'
import { formatRelative } from '@/utils'
import { Crown, GitBranch, Layers, Timer } from 'lucide-react'

export function ControlPlanePage() {
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['raft-status'],
    queryFn: api.raftStatus,
    refetchInterval: 3000,
  })

  const { data: leader } = useQuery({
    queryKey: ['raft-leader'],
    queryFn: api.raftLeader,
    refetchInterval: 3000,
  })

  const { data: metrics } = useQuery({
    queryKey: ['raft-metrics'],
    queryFn: api.raftMetrics,
    refetchInterval: 5000,
  })

  if (statusLoading) {
    return <p className="text-muted">Loading control plane status…</p>
  }

  const roleColor = status?.role === 'LEADER' ? 'healthy' : status?.role === 'CANDIDATE' ? 'warning' : 'info'

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Cluster Control Plane</h2>
        <p className="text-sm text-muted">
          Raft consensus — leader election, log replication, and metadata HA
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="Current Leader"
          value={leader?.leader ?? 'Electing…'}
          icon={Crown}
          subtitle={leader?.leader_url ? `at ${leader.leader_url}` : undefined}
        />
        <StatCard title="Term" value={status?.term ?? 0} icon={GitBranch} />
        <StatCard title="Commit Index" value={status?.commit_index ?? 0} icon={Layers} />
        <StatCard title="Replication Lag" value={status?.replication_lag ?? 0} icon={Timer} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-border bg-card/40 p-4">
          <h3 className="mb-3 font-semibold">This Node</h3>
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted">Node ID</dt>
            <dd>{status?.node_id}</dd>
            <dt className="text-muted">Role</dt>
            <dd>
              <Badge variant={roleColor as 'healthy'}>{status?.role}</Badge>
            </dd>
            <dt className="text-muted">Log Length</dt>
            <dd>{status?.log_length}</dd>
            <dt className="text-muted">Last Applied</dt>
            <dd>{status?.last_applied}</dd>
          </dl>
        </div>

        <div className="rounded-xl border border-border bg-card/40 p-4">
          <h3 className="mb-3 font-semibold">Raft Metrics</h3>
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-muted">Leader Changes</dt>
            <dd>{metrics?.raft_leader_changes ?? 0}</dd>
            <dt className="text-muted">Elections</dt>
            <dd>{metrics?.raft_election_count ?? 0}</dd>
            <dt className="text-muted">Log Entries</dt>
            <dd>{metrics?.raft_log_entries ?? 0}</dd>
            <dt className="text-muted">Append Latency</dt>
            <dd>{metrics?.raft_append_latency_ms ?? 0} ms</dd>
          </dl>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card/40 p-4">
        <h3 className="mb-3 font-semibold">Cluster Peers</h3>
        <div className="flex flex-wrap gap-2">
          {status?.peers?.map((peer) => (
            <Badge key={peer} variant={peer === leader?.leader ? 'healthy' : 'default'}>
              {peer}
              {peer === leader?.leader && ' (leader)'}
            </Badge>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card/40 p-4">
        <h3 className="mb-3 font-semibold">Election History</h3>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Term</TableHead>
              <TableHead>Winner</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Time</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(metrics?.election_history ?? []).slice().reverse().map((e, i) => (
              <TableRow key={`${e.term}-${i}`}>
                <TableCell>{e.term}</TableCell>
                <TableCell>{e.winner ?? '—'}</TableCell>
                <TableCell>{e.reason}</TableCell>
                <TableCell>{formatRelative(e.timestamp)}</TableCell>
              </TableRow>
            ))}
            {!metrics?.election_history?.length && (
              <TableRow>
                <TableCell colSpan={4} className="text-muted">
                  No elections recorded yet
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
