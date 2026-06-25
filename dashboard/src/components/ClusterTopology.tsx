import { useMemo, useCallback } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  MarkerType,
  Handle,
  Position,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Server, Database } from 'lucide-react'
import { cn } from '@/utils'
import { useClusterStore } from '@/stores'
import { useChartTheme } from '@/hooks/useChartTheme'

function MetadataNode({ data }: { data: { label: string } }) {
  return (
    <div className="rounded-xl border-2 border-primary bg-card px-4 py-3 shadow-lg shadow-primary/10 min-w-[140px]">
      <Handle type="target" position={Position.Top} className="!bg-primary" />
      <div className="flex items-center gap-2">
        <Database className="h-4 w-4 text-primary" />
        <span className="text-sm font-semibold">{data.label}</span>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-primary" />
    </div>
  )
}

function StorageNode({ data }: { data: { label: string; status: string } }) {
  const statusColor =
    data.status === 'UP' ? 'border-success text-success' : data.status === 'DOWN' ? 'border-danger text-danger' : 'border-warning text-warning'
  return (
    <div className={cn('rounded-xl border-2 bg-card px-4 py-3 shadow-lg min-w-[120px]', statusColor)}>
      <Handle type="target" position={Position.Top} className="!bg-border" />
      <div className="flex items-center gap-2">
        <Server className="h-4 w-4" />
        <span className="text-sm font-medium">{data.label}</span>
      </div>
      <p className="mt-1 text-xs text-muted">{data.status}</p>
      <Handle type="source" position={Position.Bottom} className="!bg-border" />
    </div>
  )
}

const nodeTypes = { metadata: MetadataNode, storage: StorageNode }

interface ClusterTopologyProps {
  compact?: boolean
  onNodeClick?: (nodeId: string) => void
  highlightDegraded?: boolean
}

export function ClusterTopology({ compact = false, onNodeClick, highlightDegraded = false }: ClusterTopologyProps) {
  const summary = useClusterStore((s) => s.summary)
  const chart = useChartTheme()

  const { flowNodes, flowEdges } = useMemo(() => {
    const nodeIds = Object.keys(summary).length > 0 ? Object.keys(summary) : ['node1', 'node2', 'node3', 'node4']
    const statuses = Object.keys(summary).length > 0 ? summary : Object.fromEntries(nodeIds.map((id) => [id, 'UP']))

    const flowNodes: Node[] = [
      {
        id: 'metadata',
        type: 'metadata',
        position: { x: 250, y: 0 },
        data: { label: 'Metadata Service' },
      },
      ...nodeIds.map((id, i) => ({
        id,
        type: 'storage' as const,
        position: { x: i * 180 - ((nodeIds.length - 1) * 90), y: compact ? 120 : 160 },
        data: { label: id, status: statuses[id] ?? 'UP' },
      })),
    ]

    const flowEdges: Edge[] = []
    nodeIds.forEach((id) => {
      const isDown = statuses[id] === 'DOWN'
      flowEdges.push({
        id: `hb-${id}`,
        source: 'metadata',
        target: id,
        type: 'smoothstep',
        animated: !isDown,
        style: {
          stroke: isDown && highlightDegraded ? '#EF4444' : isDown ? '#F59E0B' : '#22C55E',
          strokeWidth: 2,
        },
        label: 'heartbeat',
        labelStyle: { fill: '#64748B', fontSize: 10 },
        markerEnd: { type: MarkerType.ArrowClosed, color: isDown ? '#F59E0B' : '#22C55E' },
      })
    })

    for (let i = 0; i < nodeIds.length; i++) {
      for (let j = i + 1; j < nodeIds.length; j++) {
        const degraded = statuses[nodeIds[i]] === 'DOWN' || statuses[nodeIds[j]] === 'DOWN'
        flowEdges.push({
          id: `rep-${nodeIds[i]}-${nodeIds[j]}`,
          source: nodeIds[i],
          target: nodeIds[j],
          type: 'smoothstep',
          animated: !degraded,
          style: {
            stroke: degraded && highlightDegraded ? '#EF4444' : '#2563EB',
            strokeWidth: 1.5,
            strokeDasharray: '5 5',
            opacity: 0.6,
          },
          label: i === 0 && j === 1 ? 'replication' : undefined,
          labelStyle: { fill: '#64748B', fontSize: 10 },
        })
      }
    }

    return { flowNodes, flowEdges }
  }, [summary, compact, highlightDegraded])

  const onNodeClickHandler = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (node.id !== 'metadata' && onNodeClick) onNodeClick(node.id)
    },
    [onNodeClick],
  )

  return (
    <div className={cn('w-full rounded-xl border border-border bg-background/30', compact ? 'h-[280px]' : 'h-[420px]')}>
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClickHandler}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={!compact}
        nodesConnectable={false}
        panOnScroll
        zoomOnScroll
      >
        <Background color={chart.flowBg} gap={20} size={1} />
        {!compact && <Controls className="!bg-card !border-border !shadow-lg [&>button]:!bg-card [&>button]:!border-border [&>button]:!text-foreground" />}
        {!compact && <MiniMap className="!bg-card !border-border" nodeColor={(n) => (n.id === 'metadata' ? '#2563EB' : '#22C55E')} />}
      </ReactFlow>
    </div>
  )
}
