import { useState, useEffect, useMemo } from 'react'
import { Select } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { api } from '@/services/api'
import { useClusterStore } from '@/stores'

type Filter = 'all' | 'healthy' | 'degraded' | 'under-replicated'

export function PlacementPage() {
  const [placements, setPlacements] = useState<Record<string, string[]>>({})
  const health = useClusterStore((s) => s.health)
  const [filter, setFilter] = useState<Filter>('all')

  useEffect(() => {
    api.placements().then(setPlacements).catch(() => setPlacements({}))
  }, [])

  const rows = useMemo(() => {
    const underRepIds = new Set(health?.under_replicated?.map((b) => b.block_id) ?? [])
    return Object.entries(placements).map(([blockId, nodes]) => {
      const state: 'healthy' | 'degraded' | 'under-replicated' =
        underRepIds.has(blockId) ? 'under-replicated' : nodes.length < 3 ? 'degraded' : 'healthy'
      return {
        block_id: blockId,
        replicas: nodes,
        primary: nodes[0] ?? '—',
        rf: nodes.length,
        version: 1,
        state,
      }
    })
  }, [placements, health])

  const filtered = rows.filter((r) => filter === 'all' || r.state === filter)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Placement</h2>
          <p className="text-sm text-muted">Block placement and replica distribution</p>
        </div>
        <Select value={filter} onChange={(e) => setFilter(e.target.value as Filter)}>
          <option value="all">All</option>
          <option value="healthy">Healthy</option>
          <option value="degraded">Degraded</option>
          <option value="under-replicated">Under-replicated</option>
        </Select>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Block ID</TableHead>
            <TableHead>Replicas</TableHead>
            <TableHead>Primary Node</TableHead>
            <TableHead>RF</TableHead>
            <TableHead>Version</TableHead>
            <TableHead>State</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filtered.length === 0 ? (
            <TableRow><TableCell colSpan={6} className="text-center text-muted">No placements found</TableCell></TableRow>
          ) : (
            filtered.map((r) => (
              <TableRow key={r.block_id}>
                <TableCell className="font-mono text-xs">{r.block_id}</TableCell>
                <TableCell className="text-xs">{r.replicas.join(', ')}</TableCell>
                <TableCell>{r.primary}</TableCell>
                <TableCell>{r.rf}</TableCell>
                <TableCell>{r.version}</TableCell>
                <TableCell>
                  <Badge variant={r.state === 'healthy' ? 'success' : r.state === 'degraded' ? 'warning' : 'danger'}>
                    {r.state}
                  </Badge>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}
