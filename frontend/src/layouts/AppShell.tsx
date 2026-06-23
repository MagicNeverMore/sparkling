import type { ReactNode } from 'react'
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

  return (
    <div className="flex h-full bg-slate-950 text-slate-100">
      <SideNav atoms={atoms} wsStatus={wsStatus} />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 items-center justify-between border-b border-slate-800 px-4 md:hidden">
          <span className="text-sm font-semibold">✨ Sparkling</span>
          <ConnectionDot status={wsStatus} />
        </header>
        <main className="min-h-0 flex-1 overflow-auto pb-20 md:pb-0">{children}</main>
      </div>
      <BottomTabBar />
    </div>
  )
}
