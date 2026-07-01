import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

type Theme = 'system' | 'dark' | 'light'

interface ThemeCtx {
  theme: Theme
  setTheme: (t: Theme) => void
  resolved: 'dark' | 'light'
}

const ThemeContext = createContext<ThemeCtx>({
  theme: 'system',
  setTheme: () => {},
  resolved: 'dark',
})

const STORAGE_KEY = 'sparkling-theme'

function getStoredTheme(): Theme {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'dark' || v === 'light' || v === 'system') return v
  } catch { /* noop */ }
  return 'system'
}

function resolveTheme(theme: Theme): 'dark' | 'light' {
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return theme
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(getStoredTheme)
  const [resolved, setResolved] = useState<'dark' | 'light'>(() => resolveTheme(getStoredTheme()))

  const setTheme = (t: Theme) => {
    setThemeState(t)
    try { localStorage.setItem(STORAGE_KEY, t) } catch { /* noop */ }
  }

  useEffect(() => {
    const r = resolveTheme(theme)
    setResolved(r)
    const root = document.documentElement
    root.style.colorScheme = r
    if (r === 'dark') {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
  }, [theme])

  // Listen for system preference changes when in 'system' mode
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => {
      if (theme === 'system') {
        const r = resolveTheme('system')
        setResolved(r)
        const root = document.documentElement
        root.style.colorScheme = r
        if (r === 'dark') root.classList.add('dark')
        else root.classList.remove('dark')
      }
    }
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [theme])

  return (
    <ThemeContext.Provider value={{ theme, setTheme, resolved }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  return useContext(ThemeContext)
}
