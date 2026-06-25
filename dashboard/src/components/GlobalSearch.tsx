import { useState, useEffect, useMemo } from 'react'
import { Search, X } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { Input } from '@/components/ui/input'
import { useClusterStore, useRepairStore, useAlertStore, useUiStore } from '@/stores'
import { useKeyboardShortcut } from '@/hooks/useWebSocket'
import { useNavigate } from '@tanstack/react-router'
import type { SearchResult } from '@/types'

export function GlobalSearch() {
  const open = useUiStore((s) => s.searchOpen)
  const setOpen = useUiStore((s) => s.setSearchOpen)
  const [query, setQuery] = useState('')
  const navigate = useNavigate()
  const nodes = useClusterStore((s) => s.nodes)
  const jobs = useRepairStore((s) => s.jobs)
  const alerts = useAlertStore((s) => s.alerts)

  useKeyboardShortcut('k', () => setOpen(true))

  useEffect(() => {
    if (!open) setQuery('')
  }, [open])

  const results = useMemo(() => {
    if (!query.trim()) return []
    const q = query.toLowerCase()
    const items: SearchResult[] = []

    Object.keys(nodes).forEach((id) => {
      if (id.toLowerCase().includes(q))
        items.push({ type: 'node', id, label: id, path: `/nodes/${id}` })
    })

    jobs.forEach((j) => {
      if (j.job_id.toLowerCase().includes(q) || j.block_id.toLowerCase().includes(q))
        items.push({ type: 'repair', id: j.job_id, label: `${j.repair_type} — ${j.block_id}`, path: '/repairs' })
    })

    alerts.forEach((a) => {
      if (a.description.toLowerCase().includes(q) || a.node.toLowerCase().includes(q))
        items.push({ type: 'alert', id: a.id, label: a.description, path: '/alerts' })
    })

    return items.slice(0, 8)
  }, [query, nodes, jobs, alerts])

  function select(result: SearchResult) {
    setOpen(false)
    navigate({ to: result.path })
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-lg border border-border bg-card/50 px-3 py-1.5 text-sm text-muted hover:border-primary/40 hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
        aria-label="Open search"
      >
        <Search className="h-4 w-4" />
        <span className="hidden md:inline">Search cluster...</span>
        <kbd className="hidden md:inline rounded border border-border bg-background px-1.5 text-xs">⌘K</kbd>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 backdrop-blur-sm pt-[15vh]"
            onClick={() => setOpen(false)}
          >
            <motion.div
              initial={{ scale: 0.96, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.96, opacity: 0 }}
              className="glass w-full max-w-lg rounded-xl shadow-2xl"
              onClick={(e) => e.stopPropagation()}
              role="dialog"
              aria-label="Global search"
            >
              <div className="flex items-center gap-2 border-b border-border p-3">
                <Search className="h-4 w-4 text-muted" />
                <Input
                  autoFocus
                  placeholder="Search nodes, blocks, repairs, alerts..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="border-0 bg-transparent focus-visible:ring-0"
                />
                <button onClick={() => setOpen(false)} aria-label="Close search">
                  <X className="h-4 w-4 text-muted" />
                </button>
              </div>
              {results.length > 0 && (
                <ul className="max-h-64 overflow-auto p-2">
                  {results.map((r) => (
                    <li key={`${r.type}-${r.id}`}>
                      <button
                        className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm hover:bg-card/80"
                        onClick={() => select(r)}
                      >
                        <span className="rounded bg-primary/15 px-1.5 py-0.5 text-xs text-primary uppercase">{r.type}</span>
                        <span>{r.label}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {query && results.length === 0 && (
                <p className="p-4 text-center text-sm text-muted">No results for &quot;{query}&quot;</p>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
