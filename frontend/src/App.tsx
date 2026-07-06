import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './layouts/AppShell'
import Inbox from './features/memory/Inbox'
import Graph from './features/graph/Graph'
import Search from './features/memory/Search'
import Settings from './features/settings/Settings'
import Tasks from './features/tasks/Tasks'
import TrendPage from './features/trend/TrendPage'
import AtomDetail from './features/memory/AtomDetail'
import AuthPage from './features/auth/Auth'
import UserProfile from './features/auth/UserProfile'
import { ToastProvider } from './components/useToast'
import { useWs } from './lib/useWs'
import { useSparklingStore } from './lib/store'
import { useAuthStore } from './lib/authStore'

function AppRoutes() {
  const loadInitial = useSparklingStore((state) => state.loadInitial)
  useWs()
  useEffect(() => {
    void loadInitial()
  }, [loadInitial])
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/inbox" replace />} />
        <Route path="/inbox" element={<Inbox />} />
        <Route path="/graph" element={<Graph />} />
        <Route path="/search" element={<Search />} />
        <Route path="/trends" element={<TrendPage />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/user" element={<UserProfile />} />
        <Route path="/atoms/:id" element={<AtomDetail />} />
      </Routes>
    </AppShell>
  )
}

function AuthGate() {
  const loadStatus = useAuthStore((state) => state.loadStatus)
  const statusLoaded = useAuthStore((state) => state.statusLoaded)
  const loading = useAuthStore((state) => state.loading)
  const authenticated = useAuthStore((state) => state.authenticated)
  const markLoggedOut = useAuthStore((state) => state.markLoggedOut)

  useEffect(() => {
    void loadStatus()
  }, [loadStatus])

  useEffect(() => {
    const handleUnauthorized = () => markLoggedOut()
    window.addEventListener('sparkling:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('sparkling:unauthorized', handleUnauthorized)
  }, [markLoggedOut])

  if (!statusLoaded || loading) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-50 text-sm text-slate-500 dark:bg-slate-950 dark:text-slate-400">
        Loading…
      </div>
    )
  }

  if (!authenticated) return <AuthPage />
  return <AppRoutes />
}

export default function App() {
  return (
    <ToastProvider>
      <AuthGate />
    </ToastProvider>
  )
}
