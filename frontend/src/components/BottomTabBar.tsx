import { NavLink } from 'react-router-dom'
import { Inbox, Network, Search, CheckSquare, Settings, type LucideIcon } from 'lucide-react'
import { navItems } from '../lib/navigation'
import { useI18n } from '../lib/I18nProvider'

const navIconMap: Record<string, LucideIcon> = {
  Inbox, Network, Search, CheckSquare, Settings,
}

export default function BottomTabBar() {
  const { t } = useI18n()

  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 grid h-16 grid-cols-5 border-t border-slate-800 bg-slate-950/95 backdrop-blur md:hidden">
      {navItems.map((item) => {
        const Icon = navIconMap[item.icon]
        const translated = t(item.labelKey)
        return (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `relative flex flex-col items-center justify-center gap-1 text-xs transition ${
                isActive ? 'bg-slate-900 text-slate-100 before:absolute before:top-0 before:h-0.5 before:w-full before:bg-violet-400' : 'text-slate-500'
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
