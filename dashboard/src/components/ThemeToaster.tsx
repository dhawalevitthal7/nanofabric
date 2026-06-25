import { Toaster } from 'sonner'
import { useUiStore } from '@/stores'

export function ThemeToaster() {
  const theme = useUiStore((s) => s.theme)
  const isDark = theme === 'dark'

  return (
    <Toaster
      theme={theme}
      position="top-right"
      toastOptions={{
        style: isDark
          ? { background: '#1E293B', border: '1px solid #334155', color: '#E2E8F0' }
          : { background: '#ffffff', border: '1px solid #e2e8f0', color: '#0f172a' },
      }}
    />
  )
}
