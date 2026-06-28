import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { api } from '@/services/api'
import { formatRelative } from '@/utils'
import { toast } from 'sonner'
import { Camera, HardDrive, Clock } from 'lucide-react'
import { StatCard } from '@/components/StatCard'

export function SnapshotsPage() {
  const qc = useQueryClient()
  const { data: snapshots = [], isLoading } = useQuery({
    queryKey: ['snapshots'],
    queryFn: api.snapshots,
    refetchInterval: 5000,
  })
  const { data: metrics } = useQuery({
    queryKey: ['protection-metrics'],
    queryFn: api.protectionMetrics,
    refetchInterval: 5000,
  })

  async function handleCreate() {
    try {
      await api.createSnapshot()
      await qc.invalidateQueries({ queryKey: ['snapshots'] })
      await qc.invalidateQueries({ queryKey: ['protection-metrics'] })
      toast.success('Snapshot created')
    } catch {
      toast.error('Failed to create snapshot')
    }
  }

  async function handleRestore(id: string) {
    try {
      await api.restoreSnapshot(id)
      toast.success('Snapshot restore completed')
      await qc.invalidateQueries({ queryKey: ['restore-jobs'] })
    } catch {
      toast.error('Restore failed')
    }
  }

  async function handleDelete(id: string) {
    try {
      await api.deleteSnapshot(id)
      await qc.invalidateQueries({ queryKey: ['snapshots'] })
      toast.success('Snapshot deleted')
    } catch {
      toast.error('Delete failed')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Snapshots</h2>
          <p className="text-sm text-muted">Point-in-time copy-on-write snapshots</p>
        </div>
        <Button onClick={handleCreate}>Create Snapshot</Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard title="Total Snapshots" value={metrics?.snapshots_total ?? 0} icon={Camera} />
        <StatCard
          title="Snapshot Size"
          value={`${((metrics?.snapshot_size_bytes ?? 0) / 1024).toFixed(1)} KB`}
          icon={HardDrive}
        />
        <StatCard title="Restore Jobs" value={metrics?.restore_jobs_total ?? 0} icon={Clock} />
      </div>

      {isLoading ? (
        <p className="text-muted">Loading snapshots…</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Snapshot ID</TableHead>
              <TableHead>Blocks</TableHead>
              <TableHead>Metadata Ver.</TableHead>
              <TableHead>Size</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {snapshots.map((s) => (
              <TableRow key={s.snapshot_id}>
                <TableCell className="font-mono text-xs">{s.snapshot_id.slice(0, 12)}…</TableCell>
                <TableCell>{s.block_count}</TableCell>
                <TableCell>{s.metadata_version}</TableCell>
                <TableCell>{(s.size_bytes / 1024).toFixed(1)} KB</TableCell>
                <TableCell>
                  <Badge variant={s.status === 'READY' ? 'success' : s.status === 'FAILED' ? 'danger' : 'warning'}>
                    {s.status}
                  </Badge>
                </TableCell>
                <TableCell className="text-xs text-muted">{formatRelative(s.timestamp)}</TableCell>
                <TableCell className="space-x-2">
                  <Button size="sm" variant="outline" onClick={() => handleRestore(s.snapshot_id)}>
                    Restore
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => handleDelete(s.snapshot_id)}>
                    Delete
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {snapshots.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted">
                  No snapshots yet
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
