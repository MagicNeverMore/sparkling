import { useMemo, useState } from 'react'
import { addDays, addMonths, eachDayOfInterval, endOfMonth, endOfWeek, format, parseISO, startOfMonth, startOfWeek } from 'date-fns'
import { Check, ChevronLeft, ChevronRight, Flag } from 'lucide-react'
import type { Task } from '../../lib/taskStore'
import { useI18n } from '../../lib/I18nProvider'
import { dayTone, localDate, taskTimeline } from './taskTimeline'

interface Props {
  tasks: Task[]
  today: string
  selectedDate: string | null
  onDateClick: (date: string) => void
  onEdit: (task: Task) => void
}
const tones = {
  normal: 'bg-violet-100 dark:bg-violet-900',
  completed: 'bg-emerald-100 dark:bg-emerald-900',
  overdue: 'bg-orange-200 dark:bg-orange-900',
  planned: 'bg-slate-100 dark:bg-slate-800',
}

export default function TaskCalendar({ tasks, today, selectedDate, onDateClick, onEdit }: Props) {
  const { lang } = useI18n()
  const zh = lang === 'zh'
  const [month, setMonth] = useState(() => startOfMonth(parseISO(today)))
  const weeks = useMemo(() => {
    const first = startOfWeek(startOfMonth(month), { weekStartsOn: 1 })
    const last = endOfWeek(endOfMonth(month), { weekStartsOn: 1 })
    const intervals = tasks.flatMap(task => {
      const interval = taskTimeline(task, today)
      return interval ? [{ task, ...interval }] : []
    }).sort((a, b) => a.start.localeCompare(b.start) || b.end.localeCompare(a.end) || a.task.id.localeCompare(b.task.id))
    // 先按完整区间排泳道，再裁剪周段；分色不会拆散同一个任务。
    const laneEnds: string[] = []
    const bars = intervals.filter(item => item.start <= localDate(last) && item.end >= localDate(first)).map(item => {
      let lane = laneEnds.findIndex(end => end < item.start)
      if (lane < 0) lane = laneEnds.length
      laneEnds[lane] = item.end
      return { ...item, lane }
    })
    const result = []
    for (let date = first; date <= last; date = addDays(date, 7)) {
      const days = eachDayOfInterval({ start: date, end: addDays(date, 6) }).map(day => localDate(day))
      result.push({ days, bars: bars.filter(bar => bar.start <= days[6] && bar.end >= days[0]) })
    }
    return result
  }, [month, tasks, today])

  return (
    <section aria-label={zh ? '任务日历' : 'Task calendar'} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 p-4 dark:border-slate-800">
        <h2 className="text-lg font-semibold text-slate-950 dark:text-slate-100">{format(month, zh ? 'yyyy 年 M 月' : 'MMMM yyyy')}</h2>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => { setMonth(startOfMonth(parseISO(today))); onDateClick(today) }} className="rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800">{zh ? '回到今天' : 'Today'}</button>
          <button type="button" aria-label={zh ? '上个月' : 'Previous month'} onClick={() => setMonth(value => addMonths(value, -1))} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"><ChevronLeft size={18} /></button>
          <button type="button" aria-label={zh ? '下个月' : 'Next month'} onClick={() => setMonth(value => addMonths(value, 1))} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"><ChevronRight size={18} /></button>
        </div>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-2 px-4 py-3 text-xs text-slate-600 dark:text-slate-400">
        {([['normal', zh ? '计划中' : 'Planned'], ['completed', zh ? '已完成周期' : 'Completed'], ['overdue', zh ? '延期' : 'Overdue'], ['planned', zh ? '提前完成后的计划' : 'Remaining plan']] as const).map(([tone, label]) => <span key={tone} className="flex items-center gap-1.5"><span className={`h-2.5 w-2.5 rounded-sm ${tones[tone]}`} />{label}</span>)}
        <span className="flex items-center gap-1"><Flag size={12} />{zh ? '截止' : 'Due'}</span>
        <span className="flex items-center gap-1"><Check size={12} />{zh ? '实际完成' : 'Finished'}</span>
      </div>
      <div className="overflow-x-auto">
        <div className="min-w-[560px]">
          <div className="grid grid-cols-7 border-y border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950/30">
            {(zh ? ['一', '二', '三', '四', '五', '六', '日'] : ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']).map(day => <span key={day} className="py-2 text-center text-xs text-slate-500">{day}</span>)}
          </div>
          {weeks.map(({ days, bars }) => (
            <div key={days[0]} className="min-h-28 border-b border-slate-200 pb-3 last:border-0 dark:border-slate-800">
              <div className="grid grid-cols-7">
                {days.map(day => <button key={day} type="button" aria-label={day} aria-pressed={selectedDate === day} onClick={() => onDateClick(day)} className={`m-1 rounded-lg py-2 text-xs hover:bg-violet-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-500 dark:hover:bg-violet-950 ${selectedDate === day ? 'bg-violet-100 font-bold text-violet-800 dark:bg-violet-950 dark:text-violet-200' : day === today ? 'font-bold text-violet-600 dark:text-violet-300' : day.slice(0, 7) !== format(month, 'yyyy-MM') ? 'text-slate-400 dark:text-slate-600' : 'text-slate-700 dark:text-slate-300'}`}>{parseISO(day).getDate()}</button>)}
              </div>
              <div className="grid grid-cols-7 gap-y-1 px-1" style={{ gridAutoRows: '34px' }}>
                {bars.map(bar => {
                  const visible = days.filter(day => day >= bar.start && day <= bar.end)
                  const label = [bar.task.title, bar.task.dueDate && `${zh ? '截止' : 'Due'} ${bar.task.dueDate}`, bar.actual && `${zh ? '实际完成' : 'Finished'} ${bar.actual}`, bar.overdueDays > 0 && (zh ? `延期 ${bar.overdueDays} 天` : `${bar.overdueDays} days overdue`), !bar.task.completed && bar.overdueDays > 0 && (zh ? '仍未完成' : 'Still open')].filter(Boolean).join(' · ')
                  return <button key={bar.task.id} type="button" title={label} aria-label={label} onClick={() => onEdit(bar.task)} style={{ gridColumn: `${days.indexOf(visible[0]) + 1} / span ${visible.length}`, gridRow: bar.lane + 1 }} className={`relative mx-px flex overflow-hidden text-left text-xs ring-inset hover:ring-2 hover:ring-violet-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-500 ${bar.start >= days[0] ? 'rounded-l-md' : ''} ${bar.end <= days[6] ? 'rounded-r-md' : ''}`}>
                    {visible.map(day => <span key={day} className={`relative h-full min-w-0 flex-1 ${tones[dayTone(bar.task, day, today)]}`}>
                      <span className="absolute right-0.5 top-0.5 flex gap-0.5 text-slate-700 dark:text-slate-200">
                        {day === bar.task.dueDate && <Flag size={10} />}
                        {day === bar.actual && <Check size={11} strokeWidth={3} />}
                      </span>
                    </span>)}
                    <span className="pointer-events-none absolute inset-x-1 bottom-1 truncate font-medium text-slate-950 dark:text-white">{bar.task.title}{bar.overdueDays > 0 ? ` · ${zh ? `延期 ${bar.overdueDays} 天` : `${bar.overdueDays}d overdue`}` : ''}{!bar.task.completed && bar.overdueDays > 0 && visible.at(-1) === bar.activeEnd ? (zh ? ' · 仍未完成' : ' · Still open') : ''}</span>
                  </button>
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
      <p className="px-4 py-3 text-xs text-slate-500">{zh ? '点击日期查看当日任务，点击任务条编辑。窄屏可横向滑动日历。' : 'Select a day to filter tasks. Select a bar to edit. Scroll horizontally on small screens.'}</p>
    </section>
  )
}
