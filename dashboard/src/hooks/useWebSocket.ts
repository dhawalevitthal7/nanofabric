import { useEffect, useRef, useCallback } from 'react'
import { getWsUrl } from '@/services/api'
import type { WsMessage } from '@/types'
import {
  useClusterStore,
  useMetricsStore,
  useAlertStore,
  useRepairStore,
  useLogStore,
} from '@/stores'
import type { Alert, LogEntry } from '@/types'
import { toast } from 'sonner'

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const setConnected = useClusterStore((s) => s.setConnected)
  const setSummary = useClusterStore((s) => s.setSummary)
  const setNodes = useClusterStore((s) => s.setNodes)
  const setOverview = useClusterStore((s) => s.setOverview)
  const setHealth = useClusterStore((s) => s.setHealth)
  const setLive = useMetricsStore((s) => s.setLive)
  const appendHistory = useMetricsStore((s) => s.appendHistory)
  const addAlert = useAlertStore((s) => s.addAlert)
  const setAlerts = useAlertStore((s) => s.setAlerts)
  const setJobs = useRepairStore((s) => s.setJobs)
  const addLog = useLogStore((s) => s.addLog)

  const handleMessage = useCallback(
    (msg: WsMessage) => {
      switch (msg.type) {
        case 'cluster': {
          const p = msg.payload as {
            summary?: Record<string, string>
            nodes?: Record<string, unknown>
            overview?: import('@/types').ClusterOverview
            health?: import('@/types').ClusterHealth
          }
          if (p.summary) setSummary(p.summary)
          if (p.nodes) setNodes(p.nodes as Parameters<typeof setNodes>[0])
          if (p.overview) setOverview(p.overview)
          if (p.health) setHealth(p.health)
          break
        }
        case 'metrics': {
          const p = msg.payload as {
            readIops?: number
            writeIops?: number
            latency?: number
            throughput?: number
            cpu?: number
            memory?: number
            disk?: number
          }
          setLive(p)
          const ts = msg.timestamp
          if (p.readIops != null) appendHistory('readIops', { timestamp: ts, value: p.readIops })
          if (p.writeIops != null) appendHistory('writeIops', { timestamp: ts, value: p.writeIops })
          if (p.latency != null) appendHistory('latency', { timestamp: ts, value: p.latency })
          if (p.throughput != null) appendHistory('throughput', { timestamp: ts, value: p.throughput })
          break
        }
        case 'alerts': {
          const p = msg.payload as { alerts?: Alert[]; alert?: Alert }
          if (p.alerts) setAlerts(p.alerts)
          if (p.alert) {
            addAlert(p.alert)
            const sev = p.alert.severity
            if (sev === 'CRITICAL') toast.error(p.alert.description, { description: p.alert.node })
            else if (sev === 'WARNING') toast.warning(p.alert.description, { description: p.alert.node })
            else toast.info(p.alert.description, { description: p.alert.node })
          }
          break
        }
        case 'repairs':
          setJobs(msg.payload as import('@/types').RepairJob[])
          break
        case 'logs':
          addLog(msg.payload as LogEntry)
          break
      }
    },
    [
      setSummary,
      setNodes,
      setOverview,
      setHealth,
      setLive,
      appendHistory,
      addAlert,
      setAlerts,
      setJobs,
      addLog,
    ],
  )

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    try {
      const ws = new WebSocket(getWsUrl())
      wsRef.current = ws
      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        reconnectRef.current = setTimeout(connect, 3000)
      }
      ws.onerror = () => ws.close()
      ws.onmessage = (ev) => {
        try {
          handleMessage(JSON.parse(ev.data) as WsMessage)
        } catch {
          /* ignore malformed */
        }
      }
    } catch {
      setConnected(false)
      reconnectRef.current = setTimeout(connect, 5000)
    }
  }, [handleMessage, setConnected])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectRef.current)
      wsRef.current?.close()
    }
  }, [connect])
}

export function useClusterPolling(enabled = true) {
  const setSummary = useClusterStore((s) => s.setSummary)
  const setNodes = useClusterStore((s) => s.setNodes)
  const setOverview = useClusterStore((s) => s.setOverview)
  const setHealth = useClusterStore((s) => s.setHealth)
  const setJobs = useRepairStore((s) => s.setJobs)

  useEffect(() => {
    if (!enabled) return
    let active = true

    async function poll() {
      try {
        const { api } = await import('@/services/api')
        const [summary, nodes, stats, health, repairs] = await Promise.all([
          api.clusterSummary(),
          api.nodes(),
          api.metadataStats(),
          api.clusterHealth().catch(() => null),
          api.repairs().catch(() => []),
        ])
        if (!active) return
        setSummary(summary)
        setNodes(nodes)
        if (health) setHealth(health)
        setJobs(repairs)

        const up = Object.values(summary).filter((s) => s === 'UP').length
        const total = Object.keys(summary).length
        const underRep = health?.under_replicated?.length ?? 0
        const diverged = health?.diverged?.length ?? 0

        setOverview({
          health: up === total && total > 0 ? (underRep > 0 ? 'degraded' : 'healthy') : up === 0 ? 'critical' : 'degraded',
          totalCapacity: total * 100 * 1024 * 1024 * 1024,
          usedCapacity: stats.total_placements * 4 * 1024 * 1024,
          totalBlocks: stats.total_blocks,
          replicationFactor: 3,
          activeNodes: up,
          totalNodes: total,
          alertCount: underRep + diverged + (total - up),
          replicationHealth: {
            healthy: Math.max(0, stats.total_placements - underRep - diverged),
            degraded: underRep,
            failed: diverged,
          },
        })
      } catch {
        /* backend offline */
      }
    }

    poll()
    const id = setInterval(poll, 5000)
    return () => {
      active = false
      clearInterval(id)
    }
  }, [enabled, setSummary, setNodes, setOverview, setHealth, setJobs])
}

export function useKeyboardShortcut(key: string, handler: () => void, meta = true) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (meta && (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === key.toLowerCase()) {
        e.preventDefault()
        handler()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [key, handler, meta])
}

export function useSimulatedMetrics() {
  const setLive = useMetricsStore((s) => s.setLive)
  const appendHistory = useMetricsStore((s) => s.appendHistory)

  useEffect(() => {
    const id = setInterval(() => {
      const ts = Date.now()
      const readIops = Math.round(800 + Math.random() * 400)
      const writeIops = Math.round(400 + Math.random() * 300)
      const latency = Math.round(2 + Math.random() * 8)
      const throughput = Math.round(50 + Math.random() * 40)
      setLive({ readIops, writeIops, latency, throughput, cpu: 35 + Math.random() * 30, memory: 45 + Math.random() * 25, disk: 55 + Math.random() * 20 })
      appendHistory('readIops', { timestamp: ts, value: readIops })
      appendHistory('writeIops', { timestamp: ts, value: writeIops })
      appendHistory('latency', { timestamp: ts, value: latency })
      appendHistory('throughput', { timestamp: ts, value: throughput })
    }, 2000)
    return () => clearInterval(id)
  }, [setLive, appendHistory])
}
