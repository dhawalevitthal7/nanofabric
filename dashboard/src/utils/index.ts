import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { format, formatDistanceToNow } from 'date-fns'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatBytes(bytes: number, decimals = 1): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(decimals))} ${sizes[i]}`
}

export function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toString()
}

export function formatTimestamp(ts: number): string {
  return format(new Date(ts), 'MMM d, HH:mm:ss')
}

export function formatRelative(ts: number): string {
  return formatDistanceToNow(new Date(ts), { addSuffix: true })
}

export function healthFromSummary(summary: Record<string, string>): 'healthy' | 'degraded' | 'critical' {
  const values = Object.values(summary)
  if (values.length === 0) return 'degraded'
  const down = values.filter((s) => s === 'DOWN').length
  if (down === 0) return 'healthy'
  if (down < values.length) return 'degraded'
  return 'critical'
}

export function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

export type TimeRange = '15m' | '1h' | '24h' | '7d' | '30d'

export function timeRangeToMs(range: TimeRange): number {
  const map: Record<TimeRange, number> = {
    '15m': 15 * 60 * 1000,
    '1h': 60 * 60 * 1000,
    '24h': 24 * 60 * 60 * 1000,
    '7d': 7 * 24 * 60 * 60 * 1000,
    '30d': 30 * 24 * 60 * 60 * 1000,
  }
  return map[range]
}

export function generateTimeSeries(
  name: string,
  baseValue: number,
  range: TimeRange,
  points = 60,
  variance = 0.2,
): { name: string; points: { timestamp: number; value: number }[] } {
  const now = Date.now()
  const span = timeRangeToMs(range)
  const interval = span / points
  const result = []
  let value = baseValue
  for (let i = points - 1; i >= 0; i--) {
    value = Math.max(0, value + (Math.random() - 0.5) * baseValue * variance)
    result.push({ timestamp: now - i * interval, value: Math.round(value) })
  }
  return { name, points: result }
}
