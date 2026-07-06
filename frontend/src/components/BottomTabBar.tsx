import { NavLink } from 'react-router-dom'
import { Inbox, Network, Search, CheckSquare, Settings, User, TrendingUp, type LucideIcon } from 'lucide-react'
import { navItems } from '../lib/navigation'
import { useI18n } from '../lib/I18nProvider'

const navIconMap: Record<string, LucideIcon> = {
  Inbox, Network, Search, TrendingUp, CheckSquare, Settings, User,
}

export default function BottomTabBar() {
  const { t } = useI18n()

  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 grid h-16 grid-cols-7 border-t border-slate-200 bg-white/95 backdrop-blur md:hidden dark:border-slate-800 dark:bg-slate-950/95">
      {navItems.map((item) => {
        const Icon = navIconMap[item.icon]
        const translated = t(item.labelKey)
        return (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `relative flex flex-col items-center justify-center gap-1 text-xs transition ${
                isActive ? 'bg-violet-50 text-slate-950 before:absolute before:top-0 before:h-0.5 before:w-full before:bg-violet-400 dark:bg-slate-900 dark:text-slate-100' : 'text-slate-500'
              }`
            }
          >
            {Icon ? <Icon size={20} /> : <span className="text-lg leading-none">{item.icon}</span>}
            <span>{translated}</span>
          </NavLink>
        )
      })}
    </nav>
  )
}
