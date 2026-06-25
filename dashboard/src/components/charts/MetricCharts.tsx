import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
} from 'recharts'
import { format } from 'date-fns'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { TimeRange } from '@/utils'
import { Button } from '@/components/ui/button'
import { cn } from '@/utils'
import { useChartTheme } from '@/hooks/useChartTheme'

const COLORS = {
  primary: '#2563EB',
  success: '#22C55E',
  warning: '#F59E0B',
  danger: '#EF4444',
  muted: '#64748B',
}

interface ChartCardProps {
  title: string
  children: React.ReactNode
  className?: string
  action?: React.ReactNode
}

export function ChartCard({ title, children, className, action }: ChartCardProps) {
  return (
    <Card className={cn('flex flex-col', className)}>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle>{title}</CardTitle>
        {action}
      </CardHeader>
      <CardContent className="flex-1 min-h-[200px]">{children}</CardContent>
    </Card>
  )
}

export function TimeRangeSelector({
  value,
  onChange,
}: {
  value: TimeRange
  onChange: (r: TimeRange) => void
}) {
  const ranges: TimeRange[] = ['15m', '1h', '24h', '7d', '30d']
  return (
    <div className="flex gap-1">
      {ranges.map((r) => (
        <Button
          key={r}
          size="sm"
          variant={value === r ? 'default' : 'ghost'}
          onClick={() => onChange(r)}
          className="h-7 px-2 text-xs"
        >
          {r}
        </Button>
      ))}
    </div>
  )
}

interface AreaChartProps {
  data: { timestamp: number; value: number }[]
  color?: string
  unit?: string
  height?: number
}

export function MetricAreaChart({ data, color = COLORS.primary, unit = '', height = 200 }: AreaChartProps) {
  const chart = useChartTheme()
  const formatted = data.map((d) => ({
    ...d,
    time: format(new Date(d.timestamp), 'HH:mm'),
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={formatted} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id={`grad-${color}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.35} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} opacity={0.4} />
        <XAxis dataKey="time" tick={{ fill: chart.tick, fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: chart.tick, fontSize: 11 }} axisLine={false} tickLine={false} />
        <Tooltip
          contentStyle={{ background: chart.tooltip.background, border: `1px solid ${chart.tooltip.border}`, borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: chart.tooltip.text }}
          formatter={(v) => [`${v}${unit}`, '']}
        />
        <Area type="monotone" dataKey="value" stroke={color} fill={`url(#grad-${color})`} strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function MetricLineChart({
  series,
  height = 200,
}: {
  series: { name: string; data: { timestamp: number; value: number }[]; color: string }[]
  height?: number
}) {
  const chart = useChartTheme()
  const merged = series[0]?.data.map((_, i) => {
    const point: Record<string, number | string> = {
      time: format(new Date(series[0].data[i].timestamp), 'HH:mm'),
    }
    series.forEach((s) => {
      point[s.name] = s.data[i]?.value ?? 0
    })
    return point
  }) ?? []

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={merged} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} opacity={0.4} />
        <XAxis dataKey="time" tick={{ fill: chart.tick, fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: chart.tick, fontSize: 11 }} axisLine={false} tickLine={false} />
        <Tooltip contentStyle={{ background: chart.tooltip.background, border: `1px solid ${chart.tooltip.border}`, borderRadius: 8, fontSize: 12 }} />
        {series.map((s) => (
          <Line key={s.name} type="monotone" dataKey={s.name} stroke={s.color} strokeWidth={2} dot={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

export function DonutChart({
  data,
  height = 200,
}: {
  data: { name: string; value: number; color: string }[]
  height?: number
}) {
  const chart = useChartTheme()
  const total = data.reduce((s, d) => s + d.value, 0)
  return (
    <div className="flex items-center gap-4">
      <ResponsiveContainer width="50%" height={height}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={55}
            outerRadius={75}
            paddingAngle={3}
            dataKey="value"
          >
            {data.map((entry, i) => (
              <Cell key={i} fill={entry.color} stroke="transparent" />
            ))}
          </Pie>
          <Tooltip contentStyle={{ background: chart.tooltip.background, border: `1px solid ${chart.tooltip.border}`, borderRadius: 8 }} />
        </PieChart>
      </ResponsiveContainer>
      <div className="flex flex-col gap-2 text-sm">
        {data.map((d) => (
          <div key={d.name} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: d.color }} />
            <span className="text-muted">{d.name}</span>
            <span className="ml-auto font-medium tabular-nums">
              {d.value} ({total > 0 ? Math.round((d.value / total) * 100) : 0}%)
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export { COLORS }
