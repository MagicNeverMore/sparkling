import { useState, type ReactNode } from 'react'
import BottomTabBar from '../components/BottomTabBar'
import ConnectionDot from '../components/ConnectionDot'
import SideNav from '../components/SideNav'
import { useSparklingStore } from '../lib/store'

interface Props {
  children: ReactNode
}

export default function AppShell({ children }: Props) {
  const atoms = useSparklingStore((state) => state.atoms)
  const wsStatus = useSparklingStore((state) => state.wsStatus)

  const [navCollapsed, setNavCollapsed] = useState(() => {
    return localStorage.getItem('sparkling-nav-collapsed') === 'true'
  })

  const toggleNav = () => {
    setNavCollapsed((prev) => {
      const next = !prev
      localStorage.setItem('sparkling-nav-collapsed', String(next))
      return next
    })
  }

  return (
    <div className="flex h-full bg-slate-950 text-slate-100">
      <SideNav atoms={atoms} wsStatus={wsStatus} collapsed={navCollapsed} onToggle={toggleNav} />
      <div className="flex min-w-0 flex-1 flex-col">
        {/* 移动端顶部 header */}
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-slate-800 px-4 md:hidden">
          <span className="text-sm font-semibold">✨ Sparkling</span>
          <ConnectionDot status={wsStatus} />
        </header>
        <main className="min-h-0 flex-1 overflow-auto pb-20 md:pb-0">{children}</main>
      </div>
      <BottomTabBar />
    </div>
  )
}
