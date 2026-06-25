import { useUiStore } from '@/stores'

export function useChartTheme() {
  const theme = useUiStore((s) => s.theme)
  const isDark = theme === 'dark'

  return {
    grid: isDark ? '#334155' : '#e2e8f0',
    tick: '#64748b',
    tooltip: {
      background: isDark ? '#1E293B' : '#ffffff',
      border: isDark ? '#334155' : '#e2e8f0',
      text: isDark ? '#E2E8F0' : '#0f172a',
    },
    flowBg: isDark ? '#334155' : '#e2e8f0',
  }
}
