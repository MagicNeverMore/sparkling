import { NavLink, Link } from 'react-router-dom'
import ConnectionDot from './ConnectionDot'
import { navItems } from '../lib/navigation'
import type { AtomMock } from '../lib/mock'

interface Props {
  atoms: AtomMock[]
  wsStatus: 'online' | 'reconnecting' | 'offline'
}

const navClass = (isActive: boolean, iconOnly = false) =>
  `group relative flex items-center gap-3 border-l-2 px-3 py-2 text-sm transition ${
    iconOnly ? 'justify-center' : ''
  } ${
    isActive
      ? 'border-violet-400 bg-slate-900 text-slate-100'
      : 'border-transparent text-slate-400 hover:bg-slate-900 hover:text-slate-100'
  }`

export default function SideNav({ atoms, wsStatus }: Props) {
  const recent = atoms.slice(0, 5)
  return (
    <>
      <aside className="hidden w-16 shrink-0 flex-col border-r border-slate-800 bg-slate-950 md:flex lg:hidden">
        <div className="flex h-14 items-center justify-center border-b border-slate-800 text-lg">✨</div>
        <div className="flex justify-center py-4">
          <ConnectionDot status={wsStatus} compact />
        </div>
        <nav className="space-y-1">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => navClass(isActive, true)}>
              <span className="text-lg">{item.icon}</span>
              <span className="pointer-events-none absolute left-14 z-40 hidden rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-xs text-slate-200 shadow-xl group-hover:block">
                {item.label}
              </span>
            </NavLink>
          ))}
        </nav>
      </aside>

      <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-800 bg-slate-950 lg:flex">
        <div className="flex h-16 items-center justify-between border-b border-slate-800 px-4">
          <span className="font-semibold tracking-wide text-slate-100">✨ Sparkling</span>
          <ConnectionDot status={wsStatus} />
        </div>
        <nav className="space-y-1 p-3">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => navClass(isActive)}>
              <span className="w-5 text-center text-base">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
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
      </aside>
    </>
  )
}
