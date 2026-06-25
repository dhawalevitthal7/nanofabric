import { Bell } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useAlertStore } from '@/stores'
import { formatRelative } from '@/utils'
import { Link } from '@tanstack/react-router'

export function AlertCenter() {
  const [open, setOpen] = useState(false)
  const alerts = useAlertStore((s) => s.alerts)
  const unread = useAlertStore((s) => s.unreadCount)
  const acknowledge = useAlertStore((s) => s.acknowledge)
  const active = alerts.filter((a) => a.status === 'active').slice(0, 5)

  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="icon"
        onClick={() => setOpen(!open)}
        aria-label={`Alerts${unread > 0 ? `, ${unread} unread` : ''}`}
        className="relative"
      >
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-danger text-[10px] font-bold text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </Button>

      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              className="absolute right-0 top-full z-50 mt-2 w-80 glass rounded-xl shadow-xl"
            >
              <div className="flex items-center justify-between border-b border-border p-3">
                <span className="text-sm font-semibold">Alert Center</span>
                <Link to="/alerts" onClick={() => setOpen(false)} className="text-xs text-primary hover:underline">
                  View all
                </Link>
              </div>
              <div className="max-h-72 overflow-auto">
                {active.length === 0 ? (
                  <p className="p-4 text-center text-sm text-muted">No active alerts</p>
                ) : (
                  active.map((a) => (
                    <div key={a.id} className="border-b border-border/50 p-3 last:border-0">
                      <div className="flex items-center gap-2">
                        <Badge
                          variant={
                            a.severity === 'CRITICAL' ? 'danger' : a.severity === 'WARNING' ? 'warning' : 'info'
                          }
                        >
                          {a.severity}
                        </Badge>
                        <span className="text-xs text-muted">{a.node}</span>
                      </div>
                      <p className="mt-1 text-sm">{a.description}</p>
                      <div className="mt-2 flex items-center justify-between">
                        <span className="text-xs text-muted">{formatRelative(a.time)}</span>
                        <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => acknowledge(a.id)}>
                          Acknowledge
                        </Button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}
