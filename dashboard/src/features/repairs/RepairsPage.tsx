import { useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { useRepairStore } from '@/stores'
import { api } from '@/services/api'
import { formatRelative } from '@/utils'
import { toast } from 'sonner'

export function RepairsPage() {
  const jobs = useRepairStore((s) => s.setJobs)
  const allJobs = useRepairStore((s) => s.jobs)

  const grouped = useMemo(() => ({
    pending: allJobs.filter((j) => j.status === 'PENDING'),
    running: allJobs.filter((j) => ['COPYING', 'VERIFYING'].includes(j.status)),
    failed: allJobs.filter((j) => j.status === 'FAILED'),
    completed: allJobs.filter((j) => j.status === 'COMPLETED'),
  }), [allJobs])

  async function runRepair() {
    try {
      await api.runRepairs()
      const updated = await api.repairs()
      jobs(updated)
      toast.success('Repair cycle started')
    } catch {
      toast.error('Failed to start repair cycle')
    }
  }

  async function retryFailed(_jobId: string, blockId: string) {
    try {
      await api.rebuildBlock(blockId)
      toast.success(`Retrying repair for ${blockId}`)
    } catch {
      toast.error('Retry failed')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Repairs</h2>
          <p className="text-sm text-muted">Self-healing repair job management</p>
        </div>
        <Button onClick={runRepair}>Run Repair Cycle</Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-4">
        <SummaryCard title="Pending" count={grouped.pending.length} />
        <SummaryCard title="Running" count={grouped.running.length} variant="warning" />
        <SummaryCard title="Failed" count={grouped.failed.length} variant="danger" />
        <SummaryCard title="Completed" count={grouped.completed.length} variant="success" />
      </div>

      <RepairTable title="Pending Repairs" data={grouped.pending} onRetry={retryFailed} />
      <RepairTable title="Running Repairs" data={grouped.running} showProgress />
      <RepairTable title="Failed Repairs" data={grouped.failed} onRetry={retryFailed} />
      <RepairTable title="Completed Repairs" data={grouped.completed.slice(0, 10)} />
    </div>
  )
}

function SummaryCard({ title, count, variant }: { title: string; count: number; variant?: 'warning' | 'danger' | 'success' }) {
  const colors = { warning: 'text-warning', danger: 'text-danger', success: 'text-success' }
  return (
    <div className="glass rounded-xl p-4">
      <p className="text-xs text-muted uppercase">{title}</p>
      <p className={`text-3xl font-bold ${variant ? colors[variant] : ''}`}>{count}</p>
    </div>
  )
}

function RepairTable({
  title,
  data,
  onRetry,
  showProgress,
}: {
  title: string
  data: import('@/types').RepairJob[]
  onRetry?: (jobId: string, blockId: string) => void
  showProgress?: boolean
}) {
  if (data.length === 0) return null
  return (
    <div>
      <h3 className="text-lg font-semibold mb-2">{title}</h3>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Job ID</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Block</TableHead>
            <TableHead>Status</TableHead>
            {showProgress && <TableHead>Progress</TableHead>}
            <TableHead>Started</TableHead>
            <TableHead>Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((j) => (
            <TableRow key={j.job_id}>
              <TableCell className="font-mono text-xs">{j.job_id.slice(0, 10)}</TableCell>
              <TableCell className="text-xs">{j.repair_type}</TableCell>
              <TableCell className="font-mono text-xs">{j.block_id}</TableCell>
              <TableCell>
                <Badge variant={j.status === 'FAILED' ? 'danger' : j.status === 'COMPLETED' ? 'success' : 'warning'}>
                  {j.status}
                </Badge>
              </TableCell>
              {showProgress && (
                <TableCell>
                  <div className="h-2 w-24 rounded-full bg-border overflow-hidden">
                    <div className="h-full bg-primary rounded-full" style={{ width: j.status === 'VERIFYING' ? '80%' : '50%' }} />
                  </div>
                </TableCell>
              )}
              <TableCell className="text-xs text-muted">{formatRelative(j.created_at)}</TableCell>
              <TableCell>
                {onRetry && j.status === 'FAILED' && (
                  <Button size="sm" variant="ghost" onClick={() => onRetry(j.job_id, j.block_id)}>Retry</Button>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
