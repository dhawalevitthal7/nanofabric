const API_BASE = import.meta.env.VITE_API_URL ?? '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText)
    throw new Error(detail || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string; nodes_total: number; nodes_up: number; nodes_down: number }>('/health'),
  clusterSummary: () => request<Record<string, string>>('/cluster-summary'),
  nodes: () => request<Record<string, import('@/types').NodeRecord>>('/nodes'),
  metadataStats: () => request<import('@/types').MetadataStats>('/metadata/stats'),
  placements: () => request<Record<string, string[]>>('/placements'),
  clusterHealth: () => request<import('@/types').ClusterHealth>('/cluster/health'),
  clusterIntegrity: () => request<import('@/types').ClusterHealth>('/cluster/integrity'),
  repairs: () => request<import('@/types').RepairJob[]>('/repairs'),
  pendingRepairs: () => request<import('@/types').RepairJob[]>('/repairs/pending'),
  failedRepairs: () => request<import('@/types').RepairJob[]>('/repairs/failed'),
  runRepairs: () => request<unknown>('/repairs/run', { method: 'POST' }),
  rebuildBlock: (blockId: string) =>
    request<unknown>('/repairs/rebuild', { method: 'POST', body: JSON.stringify({ block_id: blockId }) }),
  repairNode: (nodeId: string) =>
    request<unknown>('/repairs/node', { method: 'POST', body: JSON.stringify({ node_id: nodeId }) }),
  nodeBlocks: (nodeId: string) => request<{ node_id: string; blocks: string[] }>(`/nodes/${nodeId}/blocks`),
  blockLocations: (blockId: string) => request<{ locations: string[] }>(`/blocks/${blockId}`),
}

export async function fetchNodeStats(address: string): Promise<import('@/types').NodeStats | null> {
  try {
    const url = address.startsWith('http') ? address : `http://${address}`
    const res = await fetch(`${url}/stats`)
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

export async function fetchNodeReplicationStats(address: string): Promise<import('@/types').ReplicationStats | null> {
  try {
    const url = address.startsWith('http') ? address : `http://${address}`
    const res = await fetch(`${url}/replication/stats`)
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

export async function fetchNodeConsistency(address: string) {
  try {
    const url = address.startsWith('http') ? address : `http://${address}`
    const res = await fetch(`${url}/consistency`)
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

export async function fetchNodeQuorum(address: string) {
  try {
    const url = address.startsWith('http') ? address : `http://${address}`
    const res = await fetch(`${url}/quorum/status`)
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

export async function fetchReplicationJobs(address: string) {
  try {
    const url = address.startsWith('http') ? address : `http://${address}`
    const res = await fetch(`${url}/replication/jobs`)
    if (!res.ok) return []
    return res.json()
  } catch {
    return []
  }
}

export async function fetchNodeHints(address: string) {
  try {
    const url = address.startsWith('http') ? address : `http://${address}`
    const res = await fetch(`${url}/hints/pending`)
    if (!res.ok) return []
    return res.json()
  } catch {
    return []
  }
}

export function getWsUrl(): string {
  const env = import.meta.env.VITE_WS_URL
  if (env) return env
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/ws/cluster`
}

export function getSseUrl(): string {
  const env = import.meta.env.VITE_SSE_URL
  if (env) return env
  return '/api/events/stream'
}
