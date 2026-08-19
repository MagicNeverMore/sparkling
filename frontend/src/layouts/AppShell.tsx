import { useState, type ReactNode } from 'react'
import { Menu } from 'lucide-react'
import BottomTabBar from '../components/BottomTabBar'
import ConnectionDot from '../components/ConnectionDot'
import MobileNavDrawer from '../components/MobileNavDrawer'
import SideNav from '../components/SideNav'
import { useSparklingStore } from '../lib/store'

interface Props {
  children: ReactNode
}

export default function AppShell({ children }: Props) {
  const atoms = useSparklingStore((state) => state.atoms)
  const wsStatus = useSparklingStore((state) => state.wsStatus)
  const errorMessage = useSparklingStore((state) => state.errorMessage)

  const [navCollapsed, setNavCollapsed] = useState(() => {
    return localStorage.getItem('sparkling-nav-collapsed') === 'true'
  })
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  const toggleNav = () => {
    setNavCollapsed((prev) => {
      const next = !prev
      localStorage.setItem('sparkling-nav-collapsed', String(next))
      return next
    })
  }

  return (
    <div className="flex h-full bg-slate-50 text-slate-950 dark:bg-slate-950 dark:text-slate-100">
      <SideNav atoms={atoms} wsStatus={wsStatus} collapsed={navCollapsed} onToggle={toggleNav} />
      <div className="flex min-w-0 flex-1 flex-col">
        {/* 移动端顶部 header */}
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-3 md:hidden dark:border-slate-800 dark:bg-slate-950">
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => setMobileNavOpen(true)} className="rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-900" aria-label="Open navigation">
              <Menu size={20} />
            </button>
            <span className="text-sm font-semibold">✨ Sparkling</span>
          </div>
          <ConnectionDot status={wsStatus} />
        </header>
        <main className="min-h-0 flex-1 overflow-auto pb-20 md:pb-0">
          {errorMessage && (
            <div className="border-b border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 md:px-6 dark:border-rose-900/60 dark:bg-rose-950/60 dark:text-rose-100">
              <div className="mx-auto flex max-w-5xl items-start gap-3">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-rose-400 text-xs font-semibold text-rose-500 dark:text-rose-200">
                  !
                </span>
                <p className="min-w-0 break-words">{errorMessage}</p>
              </div>
            </div>
          )}
          {children}
        </main>
      </div>
      <BottomTabBar />
      <MobileNavDrawer open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />
    </div>
  )
}
