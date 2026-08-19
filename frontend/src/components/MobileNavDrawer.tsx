import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { BarChart3, CheckSquare, ChevronDown, Inbox, Network, Search, Settings, TrendingUp, User, X, type LucideIcon } from 'lucide-react'
import { navItems } from '../lib/navigation'
import { useI18n } from '../lib/I18nProvider'

interface Props {
  open: boolean
  onClose: () => void
}

const icons: Record<string, LucideIcon> = {
  Inbox, Network, Search, TrendingUp, BarChart3, CheckSquare, User, Settings,
}

export default function MobileNavDrawer({ open, onClose }: Props) {
  const { t } = useI18n()
  const location = useLocation()
  const [socialOpen, setSocialOpen] = useState(() => location.pathname.startsWith('/social-media'))

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 md:hidden">
      <button type="button" aria-label={t('nav.closeMenu')} onClick={onClose} className="absolute inset-0 bg-slate-950/50" />
      <aside className="absolute inset-y-0 left-0 w-72 overflow-y-auto border-r border-slate-200 bg-white p-3 shadow-2xl dark:border-slate-800 dark:bg-slate-950">
        <div className="mb-3 flex h-10 items-center justify-between px-2">
          <span className="font-semibold">✨ Sparkling</span>
          <button type="button" onClick={onClose} className="rounded-md p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-900" aria-label={t('nav.closeMenu')}>
            <X size={20} />
          </button>
        </div>
        <nav className="space-y-1">
          {navItems.map((item) => {
            const Icon = icons[item.icon]
            if (item.children) {
              const active = item.children.some((child) => location.pathname.startsWith(child.to))
              const expanded = socialOpen || active
              return (
                <div key={item.labelKey}>
                  <button
                    type="button"
                    onClick={() => setSocialOpen((value) => !value)}
                    className={`flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm ${active ? 'bg-violet-50 text-slate-950 dark:bg-slate-900 dark:text-slate-100' : 'text-slate-500 dark:text-slate-400'}`}
                    aria-expanded={expanded}
                  >
                    {Icon && <Icon size={18} />}
                    <span className="flex-1 text-left">{t(item.labelKey)}</span>
                    <ChevronDown size={16} className={`transition ${expanded ? 'rotate-180' : ''}`} />
                  </button>
                  {expanded && (
                    <div className="ml-6 border-l border-slate-200 pl-2 dark:border-slate-800">
                      {item.children.map((child) => (
                        <NavLink key={child.to} to={child.to} onClick={onClose} className="block rounded-md px-3 py-2 text-sm text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-900">
                          {t(child.labelKey)}
                        </NavLink>
                      ))}
                    </div>
                  )}
                </div>
              )
            }
            return (
              <NavLink key={item.to} to={item.to!} onClick={onClose} className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-900">
                {Icon && <Icon size={18} />}
                {t(item.labelKey)}
              </NavLink>
            )
          })}
        </nav>
      </aside>
    </div>
  )
}
