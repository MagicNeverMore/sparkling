import { NavLink, Route, Routes, Navigate } from 'react-router-dom'
import Inbox from './pages/Inbox'
import Graph from './pages/Graph'
import Search from './pages/Search'
import Settings from './pages/Settings'
import AtomDetail from './pages/AtomDetail'

function Nav() {
  const linkCls = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-2 rounded-md text-sm transition ${
      isActive ? 'bg-slate-800 text-slate-50' : 'text-slate-400 hover:text-slate-100'
    }`
  return (
    <nav className="flex items-center gap-1 px-4 py-3 border-b border-slate-800">
      <span className="mr-4 text-slate-300 font-semibold tracking-wide">✨ Sparkling</span>
      <NavLink to="/inbox" className={linkCls}>收件箱</NavLink>
      <NavLink to="/graph" className={linkCls}>网状图</NavLink>
      <NavLink to="/search" className={linkCls}>搜索</NavLink>
      <NavLink to="/settings" className={linkCls + ''}>设置</NavLink>
    </nav>
  )
}

export default function App() {
  return (
    <div className="h-full flex flex-col">
      <Nav />
      <main className="flex-1 overflow-auto">
        <Routes>
          <Route path="/" element={<Navigate to="/inbox" replace />} />
          <Route path="/inbox" element={<Inbox />} />
          <Route path="/graph" element={<Graph />} />
          <Route path="/search" element={<Search />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/atoms/:id" element={<AtomDetail />} />
        </Routes>
      </main>
    </div>
  )
}
