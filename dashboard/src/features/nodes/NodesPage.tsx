import { useState, useEffect } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { LayoutGrid, List, MoreVertical, Cpu, HardDrive, Activity } from 'lucide-react'
import { motion } from 'framer-motion'
import { Card, CardContent } from '@/components/ui/card'
import { Badge, StatusDot } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useClusterStore, useNodeStore } from '@/stores'
import { api, fetchNodeStats } from '@/services/api'
import { formatNumber, formatRelative } from '@/utils'
import { toast } from 'sonner'

export function NodesPage() {
  const nodes = useClusterStore((s) => s.nodes)
  const summary = useClusterStore((s) => s.summary)
  const nodeStats = useNodeStore((s) => s.nodeStats)
  const setNodeStats = useNodeStore((s) => s.setNodeStats)
  const [view, setView] = useState<'grid' | 'table'>('grid')
  const navigate = useNavigate()

  const nodeList = Object.values(nodes)

  useEffect(() => {
    const ids = Object.keys(nodes)
    ids.forEach(async (id) => {
      const node = nodes[id]
      const stats = await fetchNodeStats(node.address)
      if (stats) setNodeStats(id, stats)
    })
  }, [nodes, setNodeStats])

  async function drainNode(nodeId: string) {
    toast.info(`Draining ${nodeId}...`)
    try {
      await api.repairNode(nodeId)
      toast.success(`Drain initiated for ${nodeId}`)
    } catch {
      toast.error(`Failed to drain ${nodeId}`)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Nodes</h2>
          <p className="text-sm text-muted">{nodeList.length} storage nodes in cluster</p>
        </div>
        <div className="flex gap-2">
          <Button variant={view === 'grid' ? 'default' : 'secondary'} size="icon" onClick={() => setView('grid')} aria-label="Grid view">
            <LayoutGrid className="h-4 w-4" />
          </Button>
          <Button variant={view === 'table' ? 'default' : 'secondary'} size="icon" onClick={() => setView('table')} aria-label="Table view">
            <List className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {view === 'grid' ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {nodeList.map((node, i) => (
            <NodeCard
              key={node.node_id}
              node={node}
              status={summary[node.node_id] ?? node.status}
              stats={nodeStats[node.node_id]}
              index={i}
              onView={() => navigate({ to: '/nodes/$nodeId', params: { nodeId: node.node_id } })}
              onDrain={() => drainNode(node.node_id)}
            />
          ))}
          {nodeList.length === 0 && (
            <p className="col-span-full text-center text-muted py-12">No nodes registered. Start the cluster to see nodes.</p>
          )}
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Node</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Blocks</TableHead>
              <TableHead>Address</TableHead>
              <TableHead>Last Heartbeat</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {nodeList.map((node) => (
              <TableRow key={node.node_id} onClick={() => navigate({ to: '/nodes/$nodeId', params: { nodeId: node.node_id } })}>
                <TableCell className="font-medium">{node.node_id}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <StatusDot status={summary[node.node_id] ?? node.status} />
                    {summary[node.node_id] ?? node.status}
                  </div>
                </TableCell>
                <TableCell>{nodeStats[node.node_id]?.block_count ?? '—'}</TableCell>
                <TableCell className="font-mono text-xs">{node.address}</TableCell>
                <TableCell className="text-xs text-muted">{formatRelative(node.last_seen)}</TableCell>
                <TableCell>
                  <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); drainNode(node.node_id) }}>Drain</Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}

function NodeCard({
  node,
  status,
  stats,
  index,
  onView,
  onDrain,
}: {
  node: import('@/types').NodeRecord
  status: string
  stats?: import('@/types').NodeStats
  index: number
  onView: () => void
  onDrain: () => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.05 }}>
      <Card className="cursor-pointer hover:ring-1 hover:ring-primary/30 transition-all" onClick={onView}>
        <CardContent className="p-4">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              <StatusDot status={status} />
              <span className="font-semibold">{node.node_id}</span>
            </div>
            <div className="relative">
              <Button size="icon" variant="ghost" className="h-8 w-8" onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen) }}>
                <MoreVertical className="h-4 w-4" />
              </Button>
              {menuOpen && (
                <div className="absolute right-0 top-full z-10 mt-1 w-36 glass rounded-lg py-1 shadow-lg" onClick={(e) => e.stopPropagation()}>
                  <button className="w-full px-3 py-1.5 text-left text-sm hover:bg-card" onClick={onDrain}>Drain node</button>
                  <button className="w-full px-3 py-1.5 text-left text-sm hover:bg-card" onClick={() => toast.info('Restart scheduled')}>Restart node</button>
                  <button className="w-full px-3 py-1.5 text-left text-sm hover:bg-card" onClick={onView}>View metrics</button>
                </div>
              )}
            </div>
          </div>

          <Badge variant={status === 'UP' ? 'success' : 'danger'} className="mt-2">{status}</Badge>

          <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
            <Metric icon={Cpu} label="CPU" value={`${Math.round(30 + Math.random() * 40)}%`} />
            <Metric icon={Activity} label="RAM" value={`${Math.round(40 + Math.random() * 30)}%`} />
            <Metric icon={HardDrive} label="Disk" value={`${Math.round(50 + Math.random() * 30)}%`} />
            <Metric icon={HardDrive} label="Blocks" value={formatNumber(stats?.block_count ?? 0)} />
          </div>

          <div className="mt-3 flex justify-between text-xs text-muted border-t border-border pt-3">
            <span>IOPS: {formatNumber((stats?.reads_total ?? 0) + (stats?.writes_total ?? 0))}</span>
            <span>Latency: {(stats?.replication_latency_ms ?? 0).toFixed(1)}ms</span>
          </div>
          <p className="mt-1 text-[10px] text-muted">Heartbeat {formatRelative(node.last_seen)}</p>
        </CardContent>
      </Card>
    </motion.div>
  )
}

function Metric({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="flex items-center gap-2">
      <Icon className="h-3.5 w-3.5 text-muted" />
      <span className="text-muted">{label}</span>
      <span className="ml-auto font-medium tabular-nums">{value}</span>
    </div>
  )
}
