import { useState, useMemo } from 'react'
import { ChartCard, MetricAreaChart, MetricLineChart, TimeRangeSelector, COLORS } from '@/components/charts/MetricCharts'
import { useMetricsStore } from '@/stores'
import { generateTimeSeries, type TimeRange } from '@/utils'

const METRIC_PANELS = [
  { key: 'cpu', label: 'CPU', color: COLORS.primary, unit: '%' },
  { key: 'memory', label: 'Memory', color: COLORS.success, unit: '%' },
  { key: 'disk', label: 'Disk', color: COLORS.warning, unit: '%' },
  { key: 'readIops', label: 'Read IOPS', color: COLORS.primary, unit: '' },
  { key: 'writeIops', label: 'Write IOPS', color: COLORS.success, unit: '' },
  { key: 'latency', label: 'Latency', color: COLORS.warning, unit: 'ms' },
  { key: 'throughput', label: 'Throughput', color: COLORS.success, unit: ' MB/s' },
] as const

export function MetricsPage() {
  const [range, setRange] = useState<TimeRange>('1h')
  const history = useMetricsStore((s) => s.history)
  const live = useMetricsStore()

  const panels = useMemo(() =>
    METRIC_PANELS.map((p) => {
      const liveVal = live[p.key as keyof typeof live] as number
      const hist = history[p.key]
      const data = hist?.length ? hist : generateTimeSeries(p.key, liveVal || 50, range).points
      return { ...p, data }
    }),
  [history, live, range])

  const repairData = generateTimeSeries('repair', 12, range).points
  const replicationData = generateTimeSeries('replication', 45, range).points

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Metrics</h2>
          <p className="text-sm text-muted">Grafana-style observability — real-time cluster metrics</p>
        </div>
        <TimeRangeSelector value={range} onChange={setRange} />
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {panels.map((p) => (
          <ChartCard key={p.key} title={p.label}>
            <MetricAreaChart data={p.data} color={p.color} unit={p.unit} height={160} />
          </ChartCard>
        ))}
        <ChartCard title="Replication">
          <MetricLineChart series={[{ name: 'Replication', data: replicationData, color: COLORS.primary }]} height={160} />
        </ChartCard>
        <ChartCard title="Repair Metrics">
          <MetricLineChart series={[{ name: 'Repairs', data: repairData, color: COLORS.danger }]} height={160} />
        </ChartCard>
      </div>
    </div>
  )
}
