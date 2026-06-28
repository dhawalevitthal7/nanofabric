import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { api } from '@/services/api'
import { formatRelative } from '@/utils'
import { toast } from 'sonner'
import { Archive, RefreshCw } from 'lucide-react'
import { StatCard } from '@/components/StatCard'

export function BackupsPage() {
  const qc = useQueryClient()
  const [backupType, setBackupType] = useState<'FULL' | 'INCREMENTAL'>('FULL')

  const { data: backups = [], isLoading } = useQuery({
    queryKey: ['backups'],
    queryFn: api.backups,
    refetchInterval: 5000,
  })
  const { data: metrics } = useQuery({
    queryKey: ['protection-metrics'],
    queryFn: api.protectionMetrics,
    refetchInterval: 5000,
  })

  async function handleCreate() {
    try {
      const lastFull = backups.find((b) => b.backup_type === 'FULL')
      await api.createBackup(
        backupType === 'INCREMENTAL' && lastFull
          ? { backup_type: 'INCREMENTAL', base_backup_id: lastFull.backup_id }
          : { backup_type: 'FULL' },
      )
      await qc.invalidateQueries({ queryKey: ['backups'] })
      await qc.invalidateQueries({ queryKey: ['protection-metrics'] })
      toast.success(`${backupType} backup created`)
    } catch {
      toast.error('Backup failed')
    }
  }

  async function handleRestore(id: string) {
    try {
      await api.restoreBackup(id)
      toast.success('Backup restore completed')
      await qc.invalidateQueries({ queryKey: ['restore-jobs'] })
    } catch {
      toast.error('Restore failed')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Backups</h2>
          <p className="text-sm text-muted">Full and incremental backup archives</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
            value={backupType}
            onChange={(e) => setBackupType(e.target.value as 'FULL' | 'INCREMENTAL')}
          >
            <option value="FULL">Full</option>
            <option value="INCREMENTAL">Incremental</option>
          </select>
          <Button onClick={handleCreate}>Create Backup</Button>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <StatCard title="Total Backups" value={metrics?.backups_total ?? 0} icon={Archive} />
        <StatCard
          title="Avg Restore Time"
          value={`${metrics?.restore_duration_ms?.toFixed(0) ?? 0} ms`}
          icon={RefreshCw}
        />
      </div>

      {isLoading ? (
        <p className="text-muted">Loading backups…</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Backup ID</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Blocks</TableHead>
              <TableHead>Size</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {backups.map((b) => (
              <TableRow key={b.backup_id}>
                <TableCell className="font-mono text-xs">{b.backup_id.slice(0, 12)}…</TableCell>
                <TableCell>
                  <Badge variant={b.backup_type === 'FULL' ? 'info' : 'warning'}>{b.backup_type}</Badge>
                </TableCell>
                <TableCell>{b.block_count}</TableCell>
                <TableCell>{(b.size_bytes / 1024).toFixed(1)} KB</TableCell>
                <TableCell>
                  <Badge variant={b.status === 'READY' ? 'success' : 'danger'}>{b.status}</Badge>
                </TableCell>
                <TableCell className="text-xs text-muted">{formatRelative(b.timestamp)}</TableCell>
                <TableCell>
                  <Button size="sm" variant="outline" onClick={() => handleRestore(b.backup_id)}>
                    Restore
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {backups.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted">
                  No backups yet
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
