import { NavLink } from 'react-router-dom'
import { Inbox, Network, Search, CheckSquare, Settings, Moon, Sun, Monitor, ChevronLeft, ChevronRight, type LucideIcon } from 'lucide-react'
import ConnectionDot from './ConnectionDot'
import HeatmapGrid from './HeatmapGrid'
import { navItems } from '../lib/navigation'
import { useI18n } from '../lib/I18nProvider'
import { useTheme } from '../lib/ThemeProvider'
import type { AtomMock } from '../lib/mock'

interface Props {
  atoms: AtomMock[]
  wsStatus: 'online' | 'reconnecting' | 'offline'
  collapsed: boolean
  onToggle: () => void
}

const navIconMap: Record<string, LucideIcon> = {
  Inbox, Network, Search, CheckSquare, Settings,
}

const themeIcons: Record<string, LucideIcon> = {
  dark: Moon,
  light: Sun,
  system: Monitor,
}

const navLinkClass = (isActive: boolean, iconOnly = false) =>
  `group relative flex items-center gap-3 border-l-2 px-3 py-2 text-sm transition ${
    iconOnly ? 'justify-center' : ''
  } ${
    isActive
      ? 'border-violet-500 bg-violet-50 text-slate-950 dark:border-violet-400 dark:bg-slate-900 dark:text-slate-100'
      : 'border-transparent text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100'
  }`

export default function SideNav({ atoms, wsStatus, collapsed, onToggle }: Props) {
  const { lang, setLang, t } = useI18n()
  const { theme, setTheme, resolved } = useTheme()

  const cycleTheme = () => {
    if (theme === 'system') {
      setTheme(resolved === 'dark' ? 'light' : 'dark')
      return
    }
    setTheme(theme === 'dark' ? 'light' : 'system')
  }

  const ThemeIcon = themeIcons[theme]

  return (
    <aside
      className={`hidden shrink-0 flex-col border-r border-slate-200 bg-white transition-all duration-200 md:flex dark:border-slate-800 dark:bg-slate-950 ${
        collapsed ? 'w-14' : 'w-60'
      }`}
    >
      {/* 顶部 header */}
      <div
        className={`flex h-16 shrink-0 items-center border-b border-slate-200 dark:border-slate-800 ${
          collapsed ? 'justify-center px-2' : 'justify-between px-4'
        }`}
      >
        {!collapsed && (
          <span className="font-semibold tracking-wide text-slate-950 dark:text-slate-100">✨ Sparkling</span>
        )}
        <div className={`flex items-center gap-2 ${collapsed ? 'flex-col gap-1.5' : ''}`}>
          {!collapsed && <ConnectionDot status={wsStatus} />}
          <button
            type="button"
            onClick={onToggle}
            title={collapsed ? t('nav.expand') : t('nav.collapse')}
            className="rounded-md p-1.5 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-500 dark:hover:bg-slate-900 dark:hover:text-slate-200"
          >
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>
      </div>

      {/* 折叠时单独显示连接状态 */}
      {collapsed && (
        <div className="flex justify-center py-2">
          <ConnectionDot status={wsStatus} compact />
        </div>
      )}

      {/* 导航项 */}
      <nav className="space-y-1 p-2">
        {navItems.map((item) => {
          const translated = t(item.labelKey)
          const Icon = navIconMap[item.icon]
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => navLinkClass(isActive, collapsed)}
            >
              {Icon ? <Icon size={collapsed ? 20 : 18} className="shrink-0" /> : <span className="w-5 text-center text-lg">{item.icon}</span>}
              {!collapsed && <span>{translated}</span>}
              {collapsed && (
                <span className="pointer-events-none absolute left-14 z-40 hidden whitespace-nowrap rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 shadow-xl group-hover:block dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200">
                  {translated}
                </span>
              )}
            </NavLink>
          )
        })}
      </nav>

      {/* 月度热力图 — 仅展开时显示 */}
      {!collapsed && (
        <div className="mt-2 border-t border-slate-200 dark:border-slate-800">
          <div className="mb-1 px-4 pt-3 text-xs uppercase tracking-wide text-slate-500 dark:text-slate-500">
            {t('heatmap.title')}
          </div>
          <HeatmapGrid atoms={atoms} />
        </div>
      )}

      {/* 底部：主题 + 语言切换 */}
      <div className={`mt-auto border-t border-slate-200 p-2 dark:border-slate-800 ${collapsed ? 'flex flex-col items-center gap-2' : 'flex items-center justify-between px-3'}`}>
        <button
          type="button"
          onClick={cycleTheme}
          title={`${t('theme.system')} / ${t('theme.dark')} / ${t('theme.light')}`}
          className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
        >
          <ThemeIcon size={collapsed ? 18 : 14} />
          {!collapsed && <span>{t(`theme.${theme}`)}</span>}
        </button>
        <button
          type="button"
          onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
          className="rounded-md px-2 py-1.5 text-xs text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
        >
          {t('lang.switch')}
        </button>
      </div>
    </aside>
  )
}
