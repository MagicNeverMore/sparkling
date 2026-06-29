import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './layouts/AppShell'
import Inbox from './pages/Inbox'
import Graph from './pages/Graph'
import Search from './pages/Search'
import Settings from './pages/Settings'
import Tasks from './pages/Tasks'
import AtomDetail from './pages/AtomDetail'
import { ToastProvider } from './components/useToast'
import { useWs } from './lib/useWs'
import { useSparklingStore } from './lib/store'

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
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/atoms/:id" element={<AtomDetail />} />
      </Routes>
    </AppShell>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <AppRoutes />
    </ToastProvider>
  )
}
