import { NavLink, Link } from 'react-router-dom'
import ConnectionDot from './ConnectionDot'
import { navItems } from '../lib/navigation'
import type { AtomMock } from '../lib/mock'

interface Props {
  atoms: AtomMock[]
  wsStatus: 'online' | 'reconnecting' | 'offline'
  collapsed: boolean
  onToggle: () => void
}

const navClass = (isActive: boolean, iconOnly = false) =>
  `group relative flex items-center gap-3 border-l-2 px-3 py-2 text-sm transition ${
    iconOnly ? 'justify-center' : ''
  } ${
    isActive
      ? 'border-violet-400 bg-slate-900 text-slate-100'
      : 'border-transparent text-slate-400 hover:bg-slate-900 hover:text-slate-100'
  }`

export default function SideNav({ atoms, wsStatus, collapsed, onToggle }: Props) {
  const recent = atoms.slice(0, 5)

  return (
    <aside
      className={`hidden shrink-0 flex-col border-r border-slate-800 bg-slate-950 transition-all duration-200 md:flex ${
        collapsed ? 'w-14' : 'w-60'
      }`}
    >
      {/* 顶部 header */}
      <div
        className={`flex h-16 shrink-0 items-center border-b border-slate-800 ${
          collapsed ? 'justify-center px-2' : 'justify-between px-4'
        }`}
      >
        {!collapsed && (
          <span className="font-semibold tracking-wide text-slate-100">✨ Sparkling</span>
        )}
        <div className={`flex items-center gap-2 ${collapsed ? 'flex-col gap-1.5' : ''}`}>
          {!collapsed && <ConnectionDot status={wsStatus} />}
          <button
            type="button"
            onClick={onToggle}
            title={collapsed ? '展开导航' : '收起导航'}
            className="rounded-md p-1.5 text-base text-slate-500 transition hover:bg-slate-900 hover:text-slate-200"
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
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => navClass(isActive, collapsed)}
          >
            <span className="w-5 text-center text-lg">{item.icon}</span>
            {!collapsed && <span>{item.label}</span>}
            {/* 折叠状态下的 tooltip */}
            {collapsed && (
              <span className="pointer-events-none absolute left-14 z-40 hidden whitespace-nowrap rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-xs text-slate-200 shadow-xl group-hover:block">
                {item.label}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* 最近访问 — 仅展开时显示 */}
      {!collapsed && (
        <div className="mt-2 border-t border-slate-800 px-4 py-4">
          <div className="mb-3 text-xs uppercase tracking-wide text-slate-500">最近</div>
          <div className="space-y-2">
            {recent.map((atom) => (
              <Link
                key={atom.id}
                to={`/atoms/${atom.id}`}
                className="block truncate rounded-md px-2 py-2 text-sm text-slate-400 transition hover:bg-slate-900 hover:text-slate-100"
              >
                {atom.content}
              </Link>
            ))}
          </div>
        </div>
      )}
    </aside>
  )
}
