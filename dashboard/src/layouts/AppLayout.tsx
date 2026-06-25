import { Outlet } from '@tanstack/react-router'
import { motion } from 'framer-motion'
import { Sidebar } from './Sidebar'
import { TopNav } from './TopNav'
import { useWebSocket, useClusterPolling, useSimulatedMetrics } from '@/hooks/useWebSocket'
import { useThemeEffect } from '@/hooks/useTheme'

export function AppLayout() {
  useThemeEffect()
  useWebSocket()
  useClusterPolling()
  useSimulatedMetrics()

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopNav />
        <main className="flex-1 overflow-auto">
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="p-4 lg:p-6"
          >
            <Outlet />
          </motion.div>
        </main>
      </div>
    </div>
  )
}
