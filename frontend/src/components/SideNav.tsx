import { NavLink } from 'react-router-dom'
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

const navLinkClass = (isActive: boolean, iconOnly = false) =>
  `group relative flex items-center gap-3 border-l-2 px-3 py-2 text-sm transition ${
    iconOnly ? 'justify-center' : ''
  } ${
    isActive
      ? 'border-violet-400 bg-slate-900 text-slate-100 dark:border-violet-400 dark:bg-slate-900 dark:text-slate-100'
      : 'border-transparent text-slate-400 hover:bg-slate-900 hover:text-slate-100 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100'
  }`

const themeIcons: Record<string, string> = { dark: '🌙', light: '☀️', system: '💻' }

export default function SideNav({ atoms, wsStatus, collapsed, onToggle }: Props) {
  const { lang, setLang, t } = useI18n()
  const { theme, setTheme } = useTheme()

  const cycleTheme = () => {
    const order: Array<'system' | 'dark' | 'light'> = ['system', 'dark', 'light']
    const idx = order.indexOf(theme)
    setTheme(order[(idx + 1) % order.length])
  }

  return (
    <aside
      className={`hidden shrink-0 flex-col border-r border-slate-800 bg-slate-950 transition-all duration-200 md:flex dark:border-slate-800 dark:bg-slate-950 ${
        collapsed ? 'w-14' : 'w-60'
      }`}
    >
      {/* 顶部 header */}
      <div
        className={`flex h-16 shrink-0 items-center border-b border-slate-800 dark:border-slate-800 ${
          collapsed ? 'justify-center px-2' : 'justify-between px-4'
        }`}
      >
        {!collapsed && (
          <span className="font-semibold tracking-wide text-slate-100 dark:text-slate-100">✨ Sparkling</span>
        )}
        <div className={`flex items-center gap-2 ${collapsed ? 'flex-col gap-1.5' : ''}`}>
          {!collapsed && <ConnectionDot status={wsStatus} />}
          <button
            type="button"
            onClick={onToggle}
            title={collapsed ? '展开导航' : '收起导航'}
            className="rounded-md p-1.5 text-base text-slate-500 transition hover:bg-slate-900 hover:text-slate-200 dark:text-slate-500 dark:hover:bg-slate-900 dark:hover:text-slate-200"
          >
            {collapsed ? '›' : '‹'}
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
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => navLinkClass(isActive, collapsed)}
            >
              <span className="w-5 text-center text-lg">{item.icon}</span>
              {!collapsed && <span>{translated}</span>}
              {collapsed && (
                <span className="pointer-events-none absolute left-14 z-40 hidden whitespace-nowrap rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-xs text-slate-200 shadow-xl group-hover:block dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200">
                  {translated}
                </span>
              )}
            </NavLink>
          )
        })}
      </nav>

      {/* 月度热力图 — 仅展开时显示 */}
      {!collapsed && (
        <div className="mt-2 border-t border-slate-800 dark:border-slate-800">
          <div className="mb-1 px-4 pt-3 text-xs uppercase tracking-wide text-slate-500 dark:text-slate-500">
            {t('heatmap.title')}
          </div>
          <HeatmapGrid atoms={atoms} />
        </div>
      )}

      {/* 底部：主题 + 语言切换 */}
      <div className={`mt-auto border-t border-slate-800 p-2 dark:border-slate-800 ${collapsed ? 'flex flex-col items-center gap-2' : 'flex items-center justify-between px-3'}`}>
        <button
          type="button"
          onClick={cycleTheme}
          title={`${t('theme.system')} / ${t('theme.dark')} / ${t('theme.light')}`}
          className="rounded-md px-2 py-1.5 text-sm text-slate-400 transition hover:bg-slate-800 hover:text-slate-200 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
        >
          {collapsed ? themeIcons[theme] : `${themeIcons[theme]} ${t(`theme.${theme}`)}`}
        </button>
        <button
          type="button"
          onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
          className="rounded-md px-2 py-1.5 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-slate-200 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
        >
          {t('lang.switch')}
        </button>
      </div>
    </aside>
  )
}
