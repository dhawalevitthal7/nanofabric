import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { api } from '@/services/api'
import { formatRelative } from '@/utils'
import { toast } from 'sonner'
import { Shield, Calendar } from 'lucide-react'

export function RestoreJobsPage() {
  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ['restore-jobs'],
    queryFn: api.restoreJobs,
    refetchInterval: 5000,
  })

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Restore Jobs</h2>
        <p className="text-sm text-muted">Snapshot and backup restore history</p>
      </div>

      {isLoading ? (
        <p className="text-muted">Loading restore jobs…</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Job ID</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Blocks</TableHead>
              <TableHead>Placements</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Duration</TableHead>
              <TableHead>Started</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {jobs.map((j) => (
              <TableRow key={j.job_id}>
                <TableCell className="font-mono text-xs">{j.job_id.slice(0, 10)}…</TableCell>
                <TableCell className="text-xs">
                  {j.source_type}/{j.source_id.slice(0, 8)}…
                </TableCell>
                <TableCell>{j.blocks_restored}</TableCell>
                <TableCell>{j.placements_restored}</TableCell>
                <TableCell>
                  <Badge
                    variant={
                      j.status === 'COMPLETED' ? 'success' : j.status === 'FAILED' ? 'danger' : 'warning'
                    }
                  >
                    {j.status}
                  </Badge>
                </TableCell>
                <TableCell>{j.duration_ms != null ? `${j.duration_ms} ms` : '—'}</TableCell>
                <TableCell className="text-xs text-muted">{formatRelative(j.created_at)}</TableCell>
              </TableRow>
            ))}
            {jobs.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted">
                  No restore jobs yet
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}
    </div>
  )
}

export function ProtectionPoliciesPage() {
  const qc = useQueryClient()
  const [name, setName] = useState('daily-policy')
  const [schedule, setSchedule] = useState('daily')
  const [retention, setRetention] = useState(7)

  const { data: policies = [], isLoading } = useQuery({
    queryKey: ['snapshot-policies'],
    queryFn: api.snapshotPolicies,
    refetchInterval: 10000,
  })

  async function handleCreate() {
    try {
      await api.createSnapshotPolicy({
        name,
        schedule,
        retention_count: retention,
        enabled: true,
      })
      await qc.invalidateQueries({ queryKey: ['snapshot-policies'] })
      toast.success('Protection policy created')
    } catch {
      toast.error('Failed to create policy')
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Protection Policies</h2>
        <p className="text-sm text-muted">Scheduled snapshots with retention</p>
      </div>

      <div className="glass rounded-xl p-4 space-y-3 max-w-lg">
        <h3 className="font-semibold flex items-center gap-2">
          <Shield className="h-4 w-4" /> New Policy
        </h3>
        <input
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Policy name"
        />
        <select
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
          value={schedule}
          onChange={(e) => setSchedule(e.target.value)}
        >
          <option value="hourly">Hourly</option>
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
        </select>
        <input
          type="number"
          min={1}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
          value={retention}
          onChange={(e) => setRetention(Number(e.target.value))}
          placeholder="Retention count"
        />
        <Button onClick={handleCreate}>Create Policy</Button>
      </div>

      {isLoading ? (
        <p className="text-muted">Loading policies…</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Schedule</TableHead>
              <TableHead>Retention</TableHead>
              <TableHead>Enabled</TableHead>
              <TableHead>Last Run</TableHead>
              <TableHead>Next Run</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {policies.map((p) => (
              <TableRow key={p.policy_id}>
                <TableCell className="font-medium">{p.name}</TableCell>
                <TableCell>
                  <Badge variant="info">
                    <Calendar className="mr-1 inline h-3 w-3" />
                    {p.schedule}
                  </Badge>
                </TableCell>
                <TableCell>Keep {p.retention_count}</TableCell>
                <TableCell>
                  <Badge variant={p.enabled ? 'success' : 'warning'}>
                    {p.enabled ? 'Yes' : 'No'}
                  </Badge>
                </TableCell>
                <TableCell className="text-xs text-muted">
                  {p.last_run_at ? formatRelative(p.last_run_at) : 'Never'}
                </TableCell>
                <TableCell className="text-xs text-muted">
                  {p.next_run_at ? formatRelative(p.next_run_at) : '—'}
                </TableCell>
              </TableRow>
            ))}
            {policies.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted">
                  No policies configured
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
