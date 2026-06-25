import { ChartCard, MetricLineChart, COLORS } from '@/components/charts/MetricCharts'
import { useMetricsStore } from '@/stores'
import { generateTimeSeries } from '@/utils'

export function PerformancePage() {
  const history = useMetricsStore((s) => s.history)
  const readIops = history.readIops ?? generateTimeSeries('read', 900, '1h').points
  const writeIops = history.writeIops ?? generateTimeSeries('write', 450, '1h').points
  const latency = history.latency ?? generateTimeSeries('lat', 5, '1h').points
  const throughput = history.throughput ?? generateTimeSeries('tp', 60, '1h').points

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Performance</h2>
        <p className="text-sm text-muted">Real-time IOPS, latency, and throughput</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Read / Write IOPS">
          <MetricLineChart series={[
            { name: 'Read', data: readIops, color: COLORS.primary },
            { name: 'Write', data: writeIops, color: COLORS.success },
          ]} />
        </ChartCard>
        <ChartCard title="Latency & Throughput">
          <MetricLineChart series={[
            { name: 'Latency (ms)', data: latency, color: COLORS.warning },
            { name: 'Throughput', data: throughput, color: COLORS.success },
          ]} />
        </ChartCard>
      </div>
    </div>
  )
}
