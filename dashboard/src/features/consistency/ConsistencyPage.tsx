import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useClusterStore } from '@/stores'
import { fetchNodeConsistency, fetchNodeQuorum, fetchNodeHints } from '@/services/api'

export function ConsistencyPage() {
  const nodes = useClusterStore((s) => s.nodes)
  const health = useClusterStore((s) => s.health)
  const [consistency, setConsistency] = useState('QUORUM')
  const [quorum, setQuorum] = useState<Record<string, unknown> | null>(null)
  const [hints, setHints] = useState<unknown[]>([])

  useEffect(() => {
    const first = Object.values(nodes)[0]
    if (!first) return
    fetchNodeConsistency(first.address).then((c) => c && setConsistency(c.level))
    fetchNodeQuorum(first.address).then(setQuorum)
    fetchNodeHints(first.address).then(setHints)
  }, [nodes])

  const readRepairs = health?.under_replicated?.length ?? 0

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Consistency</h2>
        <p className="text-sm text-muted">Quorum settings, consistency level, and repair counters</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader><CardTitle>Consistency Level</CardTitle></CardHeader>
          <CardContent><p className="text-3xl font-bold text-primary">{consistency}</p></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Quorum Required</CardTitle></CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">
              {(quorum?.last_write_quorum as { required?: number })?.required ?? 2}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Read Repair Count</CardTitle></CardHeader>
          <CardContent><p className="text-3xl font-bold text-success">{readRepairs}</p></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Hinted Handoff</CardTitle></CardHeader>
          <CardContent><p className="text-3xl font-bold text-warning">{hints.length}</p></CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Quorum Status</CardTitle></CardHeader>
        <CardContent className="font-mono text-sm text-muted">
          <pre>{JSON.stringify(quorum, null, 2)}</pre>
        </CardContent>
      </Card>

      {hints.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Pending Hints</CardTitle></CardHeader>
          <CardContent className="font-mono text-xs space-y-1">
            {hints.map((h, i) => (
              <p key={i}>{JSON.stringify(h)}</p>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
