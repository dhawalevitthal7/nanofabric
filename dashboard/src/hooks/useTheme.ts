import { useEffect } from 'react'
import { useUiStore, type Theme } from '@/stores'

export function initTheme() {
  const stored = localStorage.getItem('nanofabric-ui') 
  let theme: Theme = 'dark'
  if (stored) {
    try {
      const parsed = JSON.parse(stored)
      if (parsed?.state?.theme === 'light' || parsed?.state?.theme === 'dark') {
        theme = parsed.state.theme
      }
    } catch {
      /* ignore */
    }
  }
  applyTheme(theme)
  return theme
}

export function applyTheme(theme: Theme) {
  const root = document.documentElement
  root.classList.remove('light', 'dark')
  root.classList.add(theme)
}

export function useThemeEffect() {
  const theme = useUiStore((s) => s.theme)
  useEffect(() => {
    applyTheme(theme)
  }, [theme])
}
