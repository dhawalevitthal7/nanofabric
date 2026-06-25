import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ClusterOverview, NodeRecord, ClusterHealth, Alert, LogEntry } from '@/types'

interface ClusterState {
  summary: Record<string, string>
  nodes: Record<string, NodeRecord>
  overview: ClusterOverview | null
  health: ClusterHealth | null
  connected: boolean
  setSummary: (s: Record<string, string>) => void
  setNodes: (n: Record<string, NodeRecord>) => void
  setOverview: (o: ClusterOverview) => void
  setHealth: (h: ClusterHealth) => void
  setConnected: (c: boolean) => void
}

export const useClusterStore = create<ClusterState>((set) => ({
  summary: {},
  nodes: {},
  overview: null,
  health: null,
  connected: false,
  setSummary: (summary) => set({ summary }),
  setNodes: (nodes) => set({ nodes }),
  setOverview: (overview) => set({ overview }),
  setHealth: (health) => set({ health }),
  setConnected: (connected) => set({ connected }),
}))

interface NodeDetailState {
  selectedNodeId: string | null
  nodeStats: Record<string, import('@/types').NodeStats>
  setSelectedNode: (id: string | null) => void
  setNodeStats: (nodeId: string, stats: import('@/types').NodeStats) => void
}

export const useNodeStore = create<NodeDetailState>((set) => ({
  selectedNodeId: null,
  nodeStats: {},
  setSelectedNode: (selectedNodeId) => set({ selectedNodeId }),
  setNodeStats: (nodeId, stats) =>
    set((s) => ({ nodeStats: { ...s.nodeStats, [nodeId]: stats } })),
}))

interface MetricsState {
  readIops: number
  writeIops: number
  latency: number
  throughput: number
  cpu: number
  memory: number
  disk: number
  history: Record<string, { timestamp: number; value: number }[]>
  setLive: (m: Partial<Pick<MetricsState, 'readIops' | 'writeIops' | 'latency' | 'throughput' | 'cpu' | 'memory' | 'disk'>>) => void
  appendHistory: (key: string, point: { timestamp: number; value: number }) => void
}

export const useMetricsStore = create<MetricsState>((set) => ({
  readIops: 0,
  writeIops: 0,
  latency: 0,
  throughput: 0,
  cpu: 0,
  memory: 0,
  disk: 0,
  history: {},
  setLive: (m) => set(m),
  appendHistory: (key, point) =>
    set((s) => {
      const existing = s.history[key] ?? []
      const next = [...existing.slice(-119), point]
      return { history: { ...s.history, [key]: next } }
    }),
}))

interface AlertState {
  alerts: Alert[]
  unreadCount: number
  addAlert: (a: Alert) => void
  acknowledge: (id: string) => void
  resolve: (id: string) => void
  setAlerts: (alerts: Alert[]) => void
}

export const useAlertStore = create<AlertState>((set) => ({
  alerts: [],
  unreadCount: 0,
  addAlert: (alert) =>
    set((s) => ({
      alerts: [alert, ...s.alerts].slice(0, 200),
      unreadCount: s.unreadCount + 1,
    })),
  acknowledge: (id) =>
    set((s) => ({
      alerts: s.alerts.map((a) => (a.id === id ? { ...a, status: 'acknowledged' as const } : a)),
    })),
  resolve: (id) =>
    set((s) => ({
      alerts: s.alerts.map((a) => (a.id === id ? { ...a, status: 'resolved' as const } : a)),
    })),
  setAlerts: (alerts) => set({ alerts, unreadCount: alerts.filter((a) => a.status === 'active').length }),
}))

interface RepairState {
  jobs: import('@/types').RepairJob[]
  setJobs: (jobs: import('@/types').RepairJob[]) => void
}

export const useRepairStore = create<RepairState>((set) => ({
  jobs: [],
  setJobs: (jobs) => set({ jobs }),
}))

interface LogState {
  logs: LogEntry[]
  addLog: (log: LogEntry) => void
  setLogs: (logs: LogEntry[]) => void
  clear: () => void
}

export const useLogStore = create<LogState>((set) => ({
  logs: [],
  addLog: (log) => set((s) => ({ logs: [...s.logs.slice(-499), log] })),
  setLogs: (logs) => set({ logs }),
  clear: () => set({ logs: [] }),
}))

export type Theme = 'dark' | 'light'

interface UiState {
  sidebarCollapsed: boolean
  toggleSidebar: () => void
  searchOpen: boolean
  setSearchOpen: (open: boolean) => void
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      searchOpen: false,
      setSearchOpen: (searchOpen) => set({ searchOpen }),
      theme: 'dark',
      setTheme: (theme) => set({ theme }),
      toggleTheme: () => set((s) => ({ theme: s.theme === 'dark' ? 'light' : 'dark' })),
    }),
    { name: 'nanofabric-ui' },
  ),
)
