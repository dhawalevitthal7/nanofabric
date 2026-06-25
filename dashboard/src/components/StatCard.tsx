import { motion } from 'framer-motion'
import { type LucideIcon } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/utils'

interface StatCardProps {
  title: string
  value: string | number
  subtitle?: string
  icon: LucideIcon
  trend?: 'up' | 'down' | 'neutral'
  status?: 'healthy' | 'degraded' | 'critical' | 'default'
  index?: number
}

const statusColors = {
  healthy: 'text-success',
  degraded: 'text-warning',
  critical: 'text-danger',
  default: 'text-primary',
}

export function StatCard({ title, value, subtitle, icon: Icon, status = 'default', index = 0 }: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3 }}
    >
      <Card className="overflow-hidden">
        <CardContent className="p-4">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <p className="text-xs font-medium uppercase tracking-wider text-muted">{title}</p>
              <motion.p
                key={String(value)}
                initial={{ scale: 0.95, opacity: 0.6 }}
                animate={{ scale: 1, opacity: 1 }}
                className="text-2xl font-bold tabular-nums"
              >
                {value}
              </motion.p>
              {subtitle && <p className="text-xs text-muted">{subtitle}</p>}
            </div>
            <div className={cn('rounded-lg bg-card p-2.5 ring-1 ring-border/50', statusColors[status])}>
              <Icon className="h-5 w-5" />
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  )
}
