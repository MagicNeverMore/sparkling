import { useId, useMemo, useState } from 'react'
import { addMonths, eachDayOfInterval, endOfMonth, endOfWeek, format, startOfMonth, startOfWeek } from 'date-fns'
import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from 'lucide-react'
import type { Topic } from './types'
import { rememberTopicPreference, topicPublicationDay, topicPublicationTime, type TopicDateFilter } from './publicationCalendar'

interface Props {
  topics: Topic[]
  selectedDay: TopicDateFilter
  unavailable: boolean
  onSelectDay: (day: TopicDateFilter) => void
  onOpenTopic: (topic: Topic) => void
}

const buttonStyle = 'rounded-lg px-3 py-2 text-xs text-slate-600 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-500 disabled:opacity-40 dark:text-slate-300 dark:hover:bg-slate-800'
const eventStyle = {
  published: 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
  planned: 'bg-blue-50 text-blue-800 dark:bg-blue-950 dark:text-blue-200',
}

export default function TopicCalendar({ topics, selectedDay, unavailable, onSelectDay, onOpenTopic }: Props) {
  const contentId = useId()
  const [month, setMonth] = useState(() => startOfMonth(new Date()))
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem('sparkling-topic-calendar-collapsed') === 'true' } catch { return false }
  })
  const today = format(new Date(), 'yyyy-MM-dd')
  const { byDay, unscheduled } = useMemo(() => {
    const byDay = new Map<string, Topic[]>()
    let unscheduled = 0
    for (const topic of topics) {
      const day = topicPublicationDay(topic)
      if (!day) { unscheduled++; continue }
      const items = byDay.get(day) ?? []
      items.push(topic)
      byDay.set(day, items)
    }
    for (const items of byDay.values()) items.sort((a, b) => new Date(topicPublicationTime(a)!).getTime() - new Date(topicPublicationTime(b)!).getTime() || a.id.localeCompare(b.id))
    return { byDay, unscheduled }
  }, [topics])
  const days = useMemo(() => eachDayOfInterval({
    start: startOfWeek(startOfMonth(month), { weekStartsOn: 1 }),
    end: endOfWeek(endOfMonth(month), { weekStartsOn: 1 }),
  }), [month])
  const timeFormat = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', hour12: false })

  return <section aria-label="选题发布日历" className="overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
    <header className="flex flex-wrap items-center justify-between gap-2 p-3 md:p-4">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100"><CalendarDays size={17} />发布日历</h2>
      <div className="flex flex-wrap items-center gap-1">
        {!collapsed && <>
          <button type="button" aria-label="上个月" onClick={() => setMonth(value => addMonths(value, -1))} className={buttonStyle}><ChevronLeft size={16} /></button>
          <span aria-live="polite" className="min-w-24 text-center text-sm font-medium">{format(month, 'yyyy 年 M 月')}</span>
          <button type="button" aria-label="下个月" onClick={() => setMonth(value => addMonths(value, 1))} className={buttonStyle}><ChevronRight size={16} /></button>
          <button type="button" disabled={unavailable} onClick={() => { setMonth(startOfMonth(new Date())); onSelectDay(format(new Date(), 'yyyy-MM-dd')) }} className={buttonStyle}>今天</button>
        </>}
        <button type="button" aria-controls={contentId} aria-expanded={!collapsed} onClick={() => {
          setCollapsed(!collapsed)
          rememberTopicPreference('sparkling-topic-calendar-collapsed', String(!collapsed))
        }} className={`${buttonStyle} inline-flex items-center gap-1`}>{collapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}{collapsed ? '展开' : '收起'}</button>
      </div>
    </header>
    <div id={contentId} hidden={collapsed}>
      <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 px-4 py-2 text-xs dark:border-slate-800">
        <span className="flex items-center gap-1 text-emerald-700 dark:text-emerald-300"><span className="h-2 w-2 rounded-full bg-emerald-500" />已发布</span>
        <span className="flex items-center gap-1 text-blue-700 dark:text-blue-300"><span className="h-2 w-2 rounded-full bg-blue-500" />待发布</span>
        <span className="hidden text-slate-500 md:inline">优先显示实际发布时间，没有则显示预计发布时间</span>
        <button type="button" disabled={unavailable} aria-pressed={selectedDay === 'unscheduled'} onClick={() => onSelectDay('unscheduled')} className={`${buttonStyle} ml-auto ${selectedDay === 'unscheduled' ? 'bg-violet-50 dark:bg-violet-950' : ''}`}>未排期 {unavailable ? '—' : unscheduled}</button>
      </div>
      {unavailable ? <p role="status" className="py-12 text-center text-sm text-slate-500">正在加载或等待重试，日历暂不可用。</p> : <>
        <div className="grid grid-cols-7 border-y border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950">
          {['一', '二', '三', '四', '五', '六', '日'].map(day => <span key={day} className="py-2 text-center text-xs text-slate-500">{day}</span>)}
        </div>
        <div className="grid grid-cols-7">
          {days.map(date => {
            const day = format(date, 'yyyy-MM-dd')
            const items = byDay.get(day) ?? []
            const published = items.filter(topic => topic.status === 'published').length
            const currentMonth = date.getMonth() === month.getMonth()
            return <div key={day} className={`min-w-0 border-b border-r border-slate-100 p-0.5 md:min-h-32 md:p-1.5 dark:border-slate-800 ${selectedDay === day ? 'bg-violet-50 ring-1 ring-inset ring-violet-400 dark:bg-violet-950/40' : currentMonth ? '' : 'bg-slate-50 dark:bg-slate-950/40'}`}>
              <button type="button" aria-label={`${day}，${items.length} 个选题，已发布 ${published}，待发布 ${items.length - published}`} aria-pressed={selectedDay === day} aria-current={today === day ? 'date' : undefined} onClick={() => onSelectDay(day)} className={`w-full rounded-md py-2 text-center text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-500 ${today === day ? 'font-bold text-violet-600 dark:text-violet-300' : currentMonth ? 'text-slate-700 dark:text-slate-200' : 'text-slate-400'}`}>
                {date.getDate()}
                <span className="mt-1 flex min-h-5 flex-wrap justify-center gap-0.5 md:hidden">
                  {published > 0 && <span className="rounded bg-emerald-100 px-1 text-[10px] text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">{published} 已发</span>}
                  {items.length > published && <span className="rounded bg-blue-100 px-1 text-[10px] text-blue-800 dark:bg-blue-950 dark:text-blue-200">{items.length - published} 待发</span>}
                </span>
              </button>
              <div className="hidden space-y-1 md:block">
                {items.slice(0, 3).map(topic => {
                  const published = topic.status === 'published'
                  const time = timeFormat.format(new Date(topicPublicationTime(topic)!))
                  const label = `${published ? '已发布' : '待发布'} · ${topic.published_at ? '实际' : '预计'} ${time} · ${topic.title}`
                  return <button key={topic.id} type="button" title={label} aria-label={label} onClick={() => onOpenTopic(topic)} className={`block w-full truncate rounded px-1.5 py-1 text-left text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-500 ${published ? eventStyle.published : eventStyle.planned}`}><span className="mr-1 opacity-80">{topic.published_at ? '' : '预计 '}{time}</span>{topic.title}</button>
                })}
                {items.length > 3 && <button type="button" onClick={() => onSelectDay(day)} className="w-full rounded py-1 text-left text-xs text-violet-600 dark:text-violet-300">还有 {items.length - 3} 条</button>}
              </div>
            </div>
          })}
        </div>
        <p className="px-4 py-3 text-xs text-slate-500">点击日期在下方清单查看；日历展示全部筛选结果，不受清单分页影响。</p>
      </>}
    </div>
  </section>
}
