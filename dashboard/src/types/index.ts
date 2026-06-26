export type NodeStatus = 'UP' | 'DOWN'

export interface NodeRecord {
  node_id: string
  status: NodeStatus
  address: string
  last_seen: number
  registered_at: number
  failed_at?: number | null
  recovered_at?: number | null
}

export interface ClusterSummary {
  [nodeId: string]: NodeStatus
}

export interface MetadataStats {
  total_blocks: number
  total_placements: number
}

export interface ClusterHealth {
  under_replicated: UnderReplicatedBlock[]
  over_replicated: OverReplicatedBlock[]
  diverged: DivergedBlock[]
  orphans: OrphanBlock[]
}

export interface UnderReplicatedBlock {
  block_id: string
  version: number
  desired_nodes: string[]
  present_nodes: string[]
  missing_nodes: string[]
}

export interface OverReplicatedBlock {
  block_id: string
  version: number
  desired_nodes: string[]
  extra_nodes: string[]
}

export interface DivergedBlock {
  block_id: string
  node_hashes: Record<string, string>
}

export interface OrphanBlock {
  block_id: string
  orphan_type: string
  node_id?: string | null
}

export interface Placement {
  block_id: string
  nodes: string[]
  rf: number
  version?: number
  state?: 'healthy' | 'degraded' | 'under-replicated'
}

export interface RepairJob {
  job_id: string
  block_id: string
  source_node: string
  target_node: string
  version: number
  repair_type: string
  status: string
  attempt_count: number
  last_error: string | null
  created_at: number
  updated_at: number
  completed_at?: number | null
}

export interface RaftStatus {
  node_id: string
  leader: string | null
  term: number
  role: 'FOLLOWER' | 'CANDIDATE' | 'LEADER'
  commit_index: number
  last_applied: number
  log_length: number
  peers: string[]
  replication_lag: number
}

export interface RaftLeader {
  leader: string | null
  term: number
  role: string
  leader_url: string | null
}

export interface RaftMetrics {
  raft_current_term: number
  raft_leader_changes: number
  raft_log_entries: number
  raft_commit_index: number
  raft_append_latency_ms: number
  raft_election_count: number
  raft_replication_lag: number
  election_history: Array<{
    term: number
    winner: string | null
    timestamp: number
    reason: string
  }>
}

export interface NodeStats {
  node_id: string
  block_count: number
  used_bytes?: number
  writes_total?: number
  reads_total?: number
  successful_replications?: number
  failed_replications?: number
  replication_latency_ms?: number
  read_repairs?: number
  hint_deliveries?: number
  cache_hits?: number
  cache_misses?: number
}

export interface ReplicationStats {
  successful_replications: number
  failed_replications: number
  retry_count: number
  replication_latency_ms: number
  degraded_replications: number
  write_quorum_failures: number
  read_quorum_failures: number
  read_repairs: number
  hint_deliveries: number
  hint_failures: number
  quorum_latency_ms: number
}

export type AlertSeverity = 'INFO' | 'WARNING' | 'CRITICAL'

export interface Alert {
  id: string
  severity: AlertSeverity
  node: string
  description: string
  time: number
  status: 'active' | 'acknowledged' | 'resolved'
}

export interface LogEntry {
  id: string
  timestamp: number
  level: 'DEBUG' | 'INFO' | 'WARN' | 'ERROR'
  node: string
  message: string
  source?: string
}

export interface MetricPoint {
  timestamp: number
  value: number
}

export interface TimeSeries {
  name: string
  points: MetricPoint[]
}

export interface ClusterOverview {
  health: 'healthy' | 'degraded' | 'critical'
  totalCapacity: number
  usedCapacity: number
  totalBlocks: number
  replicationFactor: number
  activeNodes: number
  totalNodes: number
  alertCount: number
  replicationHealth: {
    healthy: number
    degraded: number
    failed: number
  }
}

export interface WsMessage {
  type: 'cluster' | 'metrics' | 'alerts' | 'topology' | 'repairs' | 'logs'
  payload: unknown
  timestamp: number
}

export interface SearchResult {
  type: 'node' | 'block' | 'repair' | 'job' | 'alert'
  id: string
  label: string
  path: string
}
