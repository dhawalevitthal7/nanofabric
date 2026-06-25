import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { useAlertStore } from '@/stores'
import { useClusterStore } from '@/stores'
import { formatRelative } from '@/utils'
import { useMemo } from 'react'

export function AlertsPage() {
  const alerts = useAlertStore((s) => s.alerts)
  const acknowledge = useAlertStore((s) => s.acknowledge)
  const resolve = useAlertStore((s) => s.resolve)
  const health = useClusterStore((s) => s.health)
  const summary = useClusterStore((s) => s.summary)

  const allAlerts = useMemo(() => {
    const items = [...alerts]
    Object.entries(summary).forEach(([node, status]) => {
      if (status === 'DOWN') {
        items.push({
          id: `down-${node}`,
          severity: 'CRITICAL' as const,
          node,
          description: `Node ${node} is DOWN`,
          time: Date.now(),
          status: 'active' as const,
        })
      }
    })
    health?.under_replicated?.forEach((b) => {
      items.push({
        id: `ur-${b.block_id}`,
        severity: 'WARNING' as const,
        node: b.missing_nodes[0] ?? 'cluster',
        description: `Under-replicated: ${b.block_id}`,
        time: Date.now(),
        status: 'active' as const,
      })
    })
    return items
  }, [alerts, summary, health])

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Alerts</h2>
        <p className="text-sm text-muted">Cluster alerting and incident management</p>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Severity</TableHead>
            <TableHead>Node</TableHead>
            <TableHead>Description</TableHead>
            <TableHead>Time</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {allAlerts.length === 0 ? (
            <TableRow><TableCell colSpan={6} className="text-center text-muted">No alerts</TableCell></TableRow>
          ) : (
            allAlerts.map((a) => (
              <TableRow key={a.id}>
                <TableCell>
                  <Badge variant={a.severity === 'CRITICAL' ? 'danger' : a.severity === 'WARNING' ? 'warning' : 'info'}>
                    {a.severity}
                  </Badge>
                </TableCell>
                <TableCell>{a.node}</TableCell>
                <TableCell>{a.description}</TableCell>
                <TableCell className="text-xs text-muted">{formatRelative(a.time)}</TableCell>
                <TableCell><Badge variant="outline">{a.status}</Badge></TableCell>
                <TableCell className="flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => acknowledge(a.id)}>Ack</Button>
                  <Button size="sm" variant="ghost" onClick={() => resolve(a.id)}>Resolve</Button>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}
