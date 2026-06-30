import { useMemo, useState } from 'react'

interface Atom {
  createdAt: string
}

function getMonthKey(year: number, month: number) {
  return `${year}-${String(month + 1).padStart(2, '0')}`
}

function countByDate(atoms: Atom[]) {
  const map = new Map<string, number>()
  for (const atom of atoms) {
    // createdAt is ISO string, extract date part
    const date = atom.createdAt.slice(0, 10)
    map.set(date, (map.get(date) ?? 0) + 1)
  }
  return map
}

function getCellColor(count: number): string {
  if (count === 0) return 'bg-slate-800'
  if (count <= 2) return 'bg-violet-400/70'
  if (count <= 4) return 'bg-violet-500/80'
  if (count <= 7) return 'bg-violet-700/80'
  return 'bg-violet-900'
}

const DAY_LABELS = ['日', '一', '二', '三', '四', '五', '六']

interface Props {
  atoms: Atom[]
}

export default function HeatmapGrid({ atoms }: Props) {
  const today = new Date()
  const [year, setYear] = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth())

  const dateCounts = useMemo(() => countByDate(atoms), [atoms])

  const { firstDayOfWeek, daysInMonth, prevMonthDays } = useMemo(() => {
    const first = new Date(year, month, 1)
    const last = new Date(year, month + 1, 0)
    // 0 = Sunday
    const startDow = first.getDay()
    const total = last.getDate()
    // Show days from previous month to fill the first row
    const prevLast = new Date(year, month, 0).getDate()
    const leading = startDow === 0 ? 6 : startDow - 1 // start from Monday
    const prevDays: number[] = []
    for (let i = leading - 1; i >= 0; i--) {
      prevDays.push(prevLast - i)
    }
    return { firstDayOfWeek: startDow, daysInMonth: total, prevMonthDays: prevDays, leading }
  }, [year, month])

  const cells: { label: string; count: number; isCurrentMonth: boolean }[] = []

  // Previous month filler
  const prevMonth = month === 0 ? 11 : month - 1
  const prevYear = month === 0 ? year - 1 : year
  for (const d of prevMonthDays) {
    const key = `${prevYear}-${String(prevMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    cells.push({ label: String(d), count: dateCounts.get(key) ?? 0, isCurrentMonth: false })
  }

  // Current month
  for (let d = 1; d <= daysInMonth; d++) {
    const key = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    cells.push({ label: String(d), count: dateCounts.get(key) ?? 0, isCurrentMonth: true })
  }

  const canGoPrev = !(year === 2024 && month === 0) // reasonable lower bound

  return (
    <div className="px-4 py-3">
      {/* Month nav */}
      <div className="mb-2 flex items-center justify-between">
        <button
          type="button"
          disabled={!canGoPrev}
          onClick={() => {
            if (month === 0) { setMonth(11); setYear(year - 1) }
            else setMonth(month - 1)
          }}
          className="rounded px-1 text-xs text-slate-500 transition hover:text-slate-300 disabled:opacity-30"
        >
          ‹
        </button>
        <span className="text-xs font-medium text-slate-400">
          {year} 年 {month + 1} 月
        </span>
        <button
          type="button"
          onClick={() => {
            if (month === 11) { setMonth(0); setYear(year + 1) }
            else setMonth(month + 1)
          }}
          className="rounded px-1 text-xs text-slate-500 transition hover:text-slate-300"
        >
          ›
        </button>
      </div>

      {/* Day labels */}
      <div className="mb-1 grid grid-cols-7 text-center text-[10px] text-slate-600">
        {DAY_LABELS.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>

      {/* Grid */}
      <div className="grid grid-cols-7 gap-[2px]">
        {cells.map((cell, i) => (
          <div
            key={i}
            title={`${cell.count} 条想法`}
            className={`aspect-square rounded-[2px] transition-colors ${
              cell.isCurrentMonth
                ? getCellColor(cell.count)
                : 'bg-slate-800/30'
            }`}
          />
        ))}
      </div>

      {/* Legend */}
      <div className="mt-2 flex items-center justify-end gap-1 text-[10px] text-slate-600">
        <span>少</span>
        <div className="h-2.5 w-2.5 rounded-sm bg-slate-800" />
        <div className="h-2.5 w-2.5 rounded-sm bg-violet-400/70" />
        <div className="h-2.5 w-2.5 rounded-sm bg-violet-500/80" />
        <div className="h-2.5 w-2.5 rounded-sm bg-violet-700/80" />
        <div className="h-2.5 w-2.5 rounded-sm bg-violet-900" />
        <span>多</span>
      </div>
    </div>
  )
}
