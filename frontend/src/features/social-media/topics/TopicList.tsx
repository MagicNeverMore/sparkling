import { useEffect, useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, Filter, Plus, Search } from 'lucide-react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { api } from '../../../lib/api'
import type { Topic, TopicListResponse, TopicStatus } from './types'
import PerformanceBadge from './PerformanceBadge'
import TopicCalendar from './TopicCalendar'
import { filterTopicsByDay, readTopicPageSize, rememberTopicPreference, topicPublicationTime, type TopicDateFilter } from './publicationCalendar'
import { performanceLabels, type PerformanceRating } from './types'

const statusLabel: Record<TopicStatus, string> = { not_started: '未开始', working: '工作中', published: '已发布' }
const statusBadgeClass: Record<TopicStatus, string> = {
  not_started: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  working: 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
  published: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
}
const platformLabel: Record<string, string> = { youtube: 'YouTube', bilibili: '哔哩哔哩', douyin: '抖音', xiaohongshu: '小红书', wechat_channels: '视频号' }
const localDateTime = (value: string | null) => value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'
type SortKey = 'title' | 'status' | 'publishedAt' | 'platform' | 'performance'
type SortDirection = 'asc' | 'desc'

const sortValue = (topic: Topic, key: SortKey) => {
  if (key === 'publishedAt') return topicPublicationTime(topic) || ''
  if (key === 'platform') return topic.publications.map((item) => item.platform).join('、')
  if (key === 'status') return statusLabel[topic.status]
  return topic.title
}

export default function TopicList() {
  const navigate = useNavigate()
  const [data, setData] = useState<TopicListResponse>({ items: [], categories: [], series: [] })
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<TopicStatus | ''>('')
  const [performance, setPerformance] = useState<PerformanceRating | 'unrated' | ''>('')
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const [series, setSeries] = useState('')
  const [loading, setLoading] = useState(true)
  const [selectedDay, setSelectedDay] = useState<TopicDateFilter>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(readTopicPageSize)
  const selectDay = (day: TopicDateFilter) => { setSelectedDay(day); setPage(1); setCoverPreview(null) }
  const [sortKey, setSortKey] = useState<SortKey>('publishedAt')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const [coverPreview, setCoverPreview] = useState<{ url: string; x: number; y: number } | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
    try {
      const params = new URLSearchParams()
      if (query.trim()) params.set('query', query.trim())
      if (status) params.set('status', status)
      if (performance) params.set('performance', performance)
      if (series) params.set('series', series)
      const result = await api.get<TopicListResponse>(`/api/social-media/topic${params.size ? `?${params}` : ''}`)
      if (!cancelled) { setData(result); setError('') }
    } catch (error) {
      if (!cancelled) setError(error instanceof Error ? error.message : String(error))
    } finally { if (!cancelled) setLoading(false) }
    }
    void load()
    return () => { cancelled = true }
  }, [performance, query, series, status, retry])
  const sortedItems = useMemo(() => filterTopicsByDay(data.items, selectedDay).slice().sort((left, right) => {
    if (sortKey === 'performance') {
      const rank = { excellent: 0, good: 1, average: 2, poor: 3 }
      const a = left.status === 'published' ? left.performance_rating : null
      const b = right.status === 'published' ? right.performance_rating : null
      if (!a || !b) return !a && !b ? 0 : !a ? 1 : -1
      return (rank[a] - rank[b]) * (sortDirection === 'asc' ? 1 : -1)
    }
    const result = sortValue(left, sortKey).localeCompare(sortValue(right, sortKey), 'zh')
    return sortDirection === 'asc' ? result : -result
  }), [data.items, selectedDay, sortDirection, sortKey])
  const pageCount = Math.max(1, Math.ceil(sortedItems.length / pageSize))
  const currentPage = Math.min(page, pageCount)
  const pageItems = sortedItems.slice((currentPage - 1) * pageSize, currentPage * pageSize)
  const toggleSort = (key: SortKey) => {
    setPage(1)
    setCoverPreview(null)
    if (key === sortKey) setSortDirection((value) => value === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDirection('asc') }
  }
  const sortableHeader = (label: string, key: SortKey) => <th aria-sort={sortKey === key ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'} className="px-4 py-3"><button type="button" onClick={() => toggleSort(key)} className="inline-flex items-center gap-1 font-medium hover:text-slate-900 dark:hover:text-slate-100">{label}{sortKey !== key ? <ArrowUpDown size={14} /> : sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />}</button></th>

  return <div className="mx-auto max-w-[1500px] space-y-5 px-4 py-6 md:px-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h1 className="text-xl font-semibold text-slate-950 dark:text-slate-100">选题库</h1><p className="mt-1 text-sm text-slate-500">管理内容创作与发布计划</p></div>
      <button type="button" onClick={() => navigate('/social-media/topics/new')} className="inline-flex items-center gap-2 rounded-md bg-violet-500 px-4 py-2 text-sm font-medium text-white hover:bg-violet-400"><Plus size={16} />新建选题</button>
    </div>
    <div className="flex flex-wrap gap-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <label className="flex min-w-[240px] flex-1 items-center gap-2 rounded-md border border-slate-200 px-3 py-2 dark:border-slate-700"><Search size={16} className="text-slate-400" /><input value={query} onChange={(event) => { setPage(1); setCoverPreview(null); setLoading(true); setQuery(event.target.value) }} placeholder="搜索标题或详情" className="min-w-0 flex-1 bg-transparent text-sm outline-none" /></label>
      <label className="inline-flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><Filter size={16} /><select value={status} onChange={(event) => { setPage(1); setCoverPreview(null); setLoading(true); setStatus(event.target.value as TopicStatus | '') }} className="rounded-md border border-slate-200 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950"><option value="">全部状态</option>{Object.entries(statusLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <select aria-label="表现筛选" value={performance} onChange={event => { setPage(1); setCoverPreview(null); setLoading(true); setPerformance(event.target.value as PerformanceRating | 'unrated' | '') }} className="rounded-md border border-slate-200 bg-white px-2 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"><option value="">全部表现</option>{Object.entries(performanceLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}<option value="unrated">待评价（已发布）</option></select>
      <select value={series} onChange={(event) => { setPage(1); setCoverPreview(null); setLoading(true); setSeries(event.target.value) }} className="rounded-md border border-slate-200 bg-white px-2 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"><option value="">全部系列</option>{data.series.map((value) => <option key={value} value={value}>{value}</option>)}</select>
    </div>
    {error && <p role="alert" className="text-sm text-rose-500">{error} <button type="button" onClick={() => { setLoading(true); setRetry(value => value + 1) }} className="underline">重试</button></p>}
    <TopicCalendar topics={data.items} selectedDay={selectedDay} unavailable={loading || !!error} onSelectDay={selectDay} onOpenTopic={topic => navigate(`/social-media/topics/${topic.id}`)} />
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">选题清单</h2>
        <span className="text-xs text-slate-500">{loading || error ? '—' : `共 ${sortedItems.length} 条`}</span>
        {selectedDay ? <button type="button" onClick={() => selectDay(null)} aria-label="清除日期筛选" className="rounded-full bg-violet-50 px-3 py-1 text-xs text-violet-700 dark:bg-violet-950 dark:text-violet-200">{selectedDay === 'unscheduled' ? '未排期' : selectedDay} ×</button> : <span className="text-xs text-slate-500">全部日期</span>}
      </div>
      <label className="flex items-center gap-2 text-xs text-slate-500">每页显示
        <select value={pageSize} onChange={event => {
          const size = Number(event.target.value)
          if (![10, 20, 30].includes(size)) return
          setPageSize(size); setPage(1); setCoverPreview(null)
          rememberTopicPreference('sparkling-topic-page-size', String(size))
        }} className="rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950">
          {[10, 20, 30].map(size => <option key={size} value={size}>{size} 条</option>)}
        </select>
      </label>
    </div>
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <table className="w-full min-w-[1100px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500 dark:bg-slate-950"><tr><th className="px-4 py-3">封面</th>{sortableHeader('标题', 'title')}<th className="px-4 py-3">系列</th><th className="px-4 py-3">详情</th>{sortableHeader('状态', 'status')}{sortableHeader('表现', 'performance')}{sortableHeader('发布时间', 'publishedAt')}{sortableHeader('发布平台', 'platform')}</tr></thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">{loading ? <tr><td colSpan={8} className="p-10 text-center text-slate-500">加载中…</td></tr> : error ? <tr><td colSpan={8} className="p-10 text-center text-rose-500">加载失败，请重试</td></tr> : sortedItems.length === 0 ? <tr><td colSpan={8} className="p-10 text-center text-slate-500">暂无选题</td></tr> : pageItems.map((topic: Topic) => <tr key={topic.id} onClick={() => navigate(`/social-media/topics/${topic.id}`)} className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-950/50"><td className="px-4 py-3">{topic.cover_url ? <img src={topic.cover_url} alt="" className="h-10 w-16 rounded object-cover" onMouseEnter={(event) => { const rect = event.currentTarget.getBoundingClientRect(); setCoverPreview({ url: topic.cover_url!, x: Math.min(rect.right + 12, window.innerWidth - 550), y: Math.min(rect.top, window.innerHeight - 370) }) }} onMouseLeave={() => setCoverPreview(null)} /> : <span className="text-slate-400">—</span>}</td><td className="max-w-[240px] px-4 py-3 font-medium text-slate-900 dark:text-slate-100">{topic.title}</td><td className="max-w-[160px] truncate px-4 py-3 text-slate-500">{topic.series || '—'}</td><td className="max-w-[300px] truncate px-4 py-3 text-slate-500">{topic.description || '—'}</td><td className="px-4 py-3"><span className={`rounded-full px-2 py-1 text-xs ${statusBadgeClass[topic.status]}`}>{statusLabel[topic.status]}</span></td><td className="whitespace-nowrap px-4 py-3">{topic.status === 'published' ? <PerformanceBadge rating={topic.performance_rating} /> : <span className="text-slate-400">—</span>}</td><td className="whitespace-nowrap px-4 py-3 text-slate-500">{localDateTime(topicPublicationTime(topic))}</td><td className="px-4 py-3"><div className="flex flex-wrap gap-1">{topic.publications.length ? topic.publications.map((item) => <span key={item.id} className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">{platformLabel[item.platform] || item.platform}</span>) : <span className="text-slate-500">—</span>}</div></td></tr>)}</tbody>
      </table>
    </div>
    <nav aria-label="选题清单分页" className="flex flex-wrap items-center justify-between gap-3 text-sm">
      <p aria-live="polite" className="text-xs text-slate-500">{loading ? '加载中…' : error ? '等待重试' : sortedItems.length ? `显示 ${(currentPage - 1) * pageSize + 1}–${Math.min(currentPage * pageSize, sortedItems.length)} 条，共 ${sortedItems.length} 条` : '暂无符合条件的选题'}</p>
      <div className="flex items-center gap-3">
        <button type="button" disabled={loading || !!error || currentPage <= 1} onClick={() => { setPage(currentPage - 1); setCoverPreview(null) }} className="rounded-lg border border-slate-200 px-3 py-2 text-xs disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700">上一页</button>
        <span className="text-xs text-slate-500">第 {currentPage} / {pageCount} 页</span>
        <button type="button" disabled={loading || !!error || currentPage >= pageCount} onClick={() => { setPage(currentPage + 1); setCoverPreview(null) }} className="rounded-lg border border-slate-200 px-3 py-2 text-xs disabled:cursor-not-allowed disabled:opacity-40 dark:border-slate-700">下一页</button>
      </div>
    </nav>
    {coverPreview && createPortal(<div className="pointer-events-none fixed z-50 rounded-md border border-slate-200 bg-white p-1 shadow-2xl dark:border-slate-700 dark:bg-slate-900" style={{ left: coverPreview.x, top: coverPreview.y }}><img src={coverPreview.url} alt="封面预览" className="h-[22rem] w-[33rem] rounded object-cover" /></div>, document.body)}
  </div>
}
