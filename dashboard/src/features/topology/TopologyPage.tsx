import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Input } from '@/components/ui/input'
import { ClusterTopology } from '@/components/ClusterTopology'
import { Search } from 'lucide-react'

export function TopologyPage() {
  const [search, setSearch] = useState('')
  const navigate = useNavigate()

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Cluster Topology</h2>
          <p className="text-sm text-muted">Interactive cluster graph — zoom, pan, inspect nodes</p>
        </div>
        <div className="relative w-64">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <Input
            placeholder="Search nodes..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>
      <ClusterTopology
        highlightDegraded
        onNodeClick={(id) => {
          if (!search || id.toLowerCase().includes(search.toLowerCase()))
            navigate({ to: '/nodes/$nodeId', params: { nodeId: id } })
        }}
      />
    </div>
  )
}
