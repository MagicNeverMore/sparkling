import { useState, useMemo } from 'react'
import {
  startOfMonth, endOfMonth,
  startOfWeek, endOfWeek,
  eachDayOfInterval, eachWeekOfInterval,
  addDays, addMonths, subMonths,
  isSameMonth, isSameDay, isToday,
  parseISO, isAfter, isBefore,
  format, max, min,
} from 'date-fns'
import type { Task } from '../../lib/taskStore'

interface Props {
  tasks: Task[]
  onDateClick: (date: Date) => void
}

interface Bar {
  task: Task
  startCol: number       // 0–6
  endCol: number         // 0–6
  continuesLeft: boolean  // 从上一周延续
  continuesRight: boolean // 延续到下一周
  lane: number
}

function getTaskInterval(task: Task): { start: Date; end: Date } | null {
  const s = task.startDate ? parseISO(task.startDate) : task.dueDate ? parseISO(task.dueDate) : null
  const e = task.dueDate ? parseISO(task.dueDate) : task.startDate ? parseISO(task.startDate) : null
  if (!s || !e) return null
  return isAfter(s, e) ? { start: e, end: s } : { start: s, end: e }
}

// 贪心算法：为一周内的任务条分配泳道，避免视觉重叠
function computeLanes(tasks: Task[], weekDays: Date[]): Bar[][] {
  const weekStart = weekDays[0]
  const weekEnd = weekDays[6]

  const raw: Omit<Bar, 'lane'>[] = tasks
    .flatMap((t) => {
      const iv = getTaskInterval(t)
      if (!iv) return []
      const { start, end } = iv
      if (isAfter(start, weekEnd) || isBefore(end, weekStart)) return []

      const barStart = max([start, weekStart])
      const barEnd = min([end, weekEnd])
      const sc = weekDays.findIndex((d) => isSameDay(d, barStart))
      const ec = weekDays.findIndex((d) => isSameDay(d, barEnd))

      return [{
        task: t,
        startCol: sc >= 0 ? sc : 0,
        endCol: ec >= 0 ? ec : 6,
        continuesLeft: isBefore(start, weekStart),
        continuesRight: isAfter(end, weekEnd),
      }]
    })
    // 较长的任务优先排，使泳道利用率更高
    .sort((a, b) => (b.endCol - b.startCol) - (a.endCol - a.startCol))

  const occupied: Omit<Bar, 'lane'>[][] = []
  const result: Bar[] = []

  for (const bar of raw) {
    let placed = false
    for (let i = 0; i < occupied.length; i++) {
      const clash = occupied[i].some(
        (b) => b.startCol <= bar.endCol && b.endCol >= bar.startCol,
      )
      if (!clash) {
        occupied[i].push(bar)
        result.push({ ...bar, lane: i })
        placed = true
        break
      }
    }
    if (!placed) {
      occupied.push([bar])
      result.push({ ...bar, lane: occupied.length - 1 })
    }
  }

  const maxLane = result.reduce((m, b) => Math.max(m, b.lane), -1)
  return Array.from({ length: maxLane + 1 }, (_, i) => result.filter((b) => b.lane === i))
}

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

export default function TaskCalendar({ tasks, onDateClick }: Props) {
  const [currentMonth, setCurrentMonth] = useState(new Date())

  const weeks = useMemo(() => {
    const monthStart = startOfMonth(currentMonth)
    const monthEnd = endOfMonth(currentMonth)
    const firstWeekStart = startOfWeek(monthStart, { weekStartsOn: 1 })
    const lastWeekEnd = endOfWeek(monthEnd, { weekStartsOn: 1 })

    return eachWeekOfInterval(
      { start: firstWeekStart, end: lastWeekEnd },
      { weekStartsOn: 1 },
    ).map((weekStart) => {
      const weekDays = eachDayOfInterval({ start: weekStart, end: addDays(weekStart, 6) })
      return { weekStart, weekDays, lanes: computeLanes(tasks, weekDays) }
    })
  }, [currentMonth, tasks])

  return (
    <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900">
      {/* 月份导航 */}
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
        <button
          type="button"
          onClick={() => setCurrentMonth((m) => subMonths(m, 1))}
          className="rounded-md px-2 py-1 text-slate-400 transition hover:bg-slate-800 hover:text-slate-200"
        >
          ‹
        </button>
        <span className="text-sm font-medium text-slate-200">
          {format(currentMonth, 'yyyy 年 M 月')}
        </span>
        <button
          type="button"
          onClick={() => setCurrentMonth((m) => addMonths(m, 1))}
          className="rounded-md px-2 py-1 text-slate-400 transition hover:bg-slate-800 hover:text-slate-200"
        >
          ›
        </button>
      </div>

      {/* 星期表头 */}
      <div className="grid grid-cols-7 border-b border-slate-800">
        {WEEKDAYS.map((d) => (
          <div key={d} className="py-2 text-center text-xs text-slate-600">{d}</div>
        ))}
      </div>

      {/* 周行 */}
      {weeks.map(({ weekStart, weekDays, lanes }) => (
        <div key={weekStart.toISOString()} className="border-b border-slate-800 last:border-b-0">
          {/* 日期数字 */}
          <div className="grid grid-cols-7">
            {weekDays.map((day) => (
              <button
                key={day.toISOString()}
                type="button"
                onClick={() => onDateClick(day)}
                className={`py-1.5 text-center text-xs transition hover:bg-slate-800 ${
                  !isSameMonth(day, currentMonth)
                    ? 'text-slate-700'
                    : isToday(day)
                      ? 'font-bold text-violet-400'
                      : 'text-slate-400'
                }`}
              >
                {day.getDate()}
              </button>
            ))}
          </div>

          {/* 甘特条：每条一个泳道，用 CSS grid 跨列 */}
          {lanes.map((laneBars, laneIdx) => (
            <div key={laneIdx} className="grid grid-cols-7 pb-0.5 pl-px pr-px">
              {laneBars.map((bar) => (
                <div
                  key={bar.task.id}
                  style={{ gridColumn: `${bar.startCol + 1} / ${bar.endCol + 2}` }}
                  title={bar.task.title}
                  className={[
                    'flex h-5 cursor-pointer items-center overflow-hidden text-xs transition',
                    bar.continuesLeft ? 'pl-1' : 'ml-0.5 rounded-l-full pl-2',
                    bar.continuesRight ? 'pr-0' : 'mr-0.5 rounded-r-full',
                    bar.task.completed
                      ? 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
                      : 'bg-violet-500/25 text-violet-300 hover:bg-violet-500/40',
                  ].join(' ')}
                >
                  {/* 从左侧开始的段才显示标题，避免截断段显示错误标题 */}
                  {!bar.continuesLeft && (
                    <span className="truncate leading-none">{bar.task.title}</span>
                  )}
                </div>
              ))}
            </div>
          ))}

          {/* 无任务时保留最小高度 */}
          {lanes.length === 0 && <div className="h-5" />}
        </div>
      ))}
    </div>
  )
}
