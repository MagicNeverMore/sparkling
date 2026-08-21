import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, Filter, Plus, Search } from 'lucide-react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { api } from '../../../lib/api'
import type { Topic, TopicListResponse, TopicStatus } from './types'

const statusLabel: Record<TopicStatus, string> = { not_started: '未开始', working: '工作中', published: '已发布' }
const platformLabel: Record<string, string> = { youtube: 'YouTube', bilibili: '哔哩哔哩', douyin: '抖音', xiaohongshu: '小红书', wechat_channels: '视频号' }
const localDateTime = (value: string | null) => value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'
type SortKey = 'title' | 'status' | 'publishedAt' | 'platform'
type SortDirection = 'asc' | 'desc'

const sortValue = (topic: Topic, key: SortKey) => {
  if (key === 'publishedAt') return topic.status === 'published' ? topic.published_at || '' : topic.scheduled_at || ''
  if (key === 'platform') return topic.publications.map((item) => item.platform).join('、')
  if (key === 'status') return statusLabel[topic.status]
  return topic.title
}

export default function TopicList() {
  const navigate = useNavigate()
  const [data, setData] = useState<TopicListResponse>({ items: [], categories: [] })
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<TopicStatus | ''>('')
  const [category, setCategory] = useState('')
  const [loading, setLoading] = useState(true)
  const [sortKey, setSortKey] = useState<SortKey>('publishedAt')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const [coverPreview, setCoverPreview] = useState<{ url: string; x: number; y: number } | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (query.trim()) params.set('query', query.trim())
      if (status) params.set('status', status)
      if (category) params.set('category', category)
      setData(await api.get<TopicListResponse>(`/api/social-media/topic${params.size ? `?${params}` : ''}`))
    } finally { setLoading(false) }
  }, [category, query, status])

  useEffect(() => { void load() }, [load])
  const sortedItems = useMemo(() => [...data.items].sort((left, right) => {
    const result = sortValue(left, sortKey).localeCompare(sortValue(right, sortKey), 'zh')
    return sortDirection === 'asc' ? result : -result
  }), [data.items, sortDirection, sortKey])
  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setSortDirection((value) => value === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDirection('asc') }
  }
  const sortableHeader = (label: string, key: SortKey) => <th className="px-4 py-3"><button type="button" onClick={() => toggleSort(key)} className="inline-flex items-center gap-1 font-medium hover:text-slate-900 dark:hover:text-slate-100">{label}{sortKey !== key ? <ArrowUpDown size={14} /> : sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />}</button></th>

  return <div className="mx-auto max-w-[1500px] space-y-5 px-4 py-6 md:px-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h1 className="text-xl font-semibold text-slate-950 dark:text-slate-100">选题库</h1><p className="mt-1 text-sm text-slate-500">管理内容创作与发布计划</p></div>
      <button type="button" onClick={() => navigate('/social-media/topics/new')} className="inline-flex items-center gap-2 rounded-md bg-violet-500 px-4 py-2 text-sm font-medium text-white hover:bg-violet-400"><Plus size={16} />新建选题</button>
    </div>
    <div className="flex flex-wrap gap-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <label className="flex min-w-[240px] flex-1 items-center gap-2 rounded-md border border-slate-200 px-3 py-2 dark:border-slate-700"><Search size={16} className="text-slate-400" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标题或详情" className="min-w-0 flex-1 bg-transparent text-sm outline-none" /></label>
      <label className="inline-flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><Filter size={16} /><select value={status} onChange={(event) => setStatus(event.target.value as TopicStatus | '')} className="rounded-md border border-slate-200 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950"><option value="">全部状态</option>{Object.entries(statusLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <select value={category} onChange={(event) => setCategory(event.target.value)} className="rounded-md border border-slate-200 bg-white px-2 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"><option value="">全部分类</option>{data.categories.map((value) => <option key={value} value={value}>{value}</option>)}</select>
    </div>
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <table className="w-full min-w-[1000px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500 dark:bg-slate-950"><tr><th className="px-4 py-3">封面</th>{sortableHeader('标题', 'title')}<th className="px-4 py-3">详情</th>{sortableHeader('状态', 'status')}{sortableHeader('发布时间', 'publishedAt')}{sortableHeader('发布平台', 'platform')}</tr></thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">{loading ? <tr><td colSpan={6} className="p-10 text-center text-slate-500">加载中…</td></tr> : sortedItems.length === 0 ? <tr><td colSpan={6} className="p-10 text-center text-slate-500">暂无选题</td></tr> : sortedItems.map((topic: Topic) => <tr key={topic.id} onClick={() => navigate(`/social-media/topics/${topic.id}`)} className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-950/50"><td className="px-4 py-3">{topic.cover_url ? <img src={topic.cover_url} alt="" className="h-10 w-16 rounded object-cover" onMouseEnter={(event) => { const rect = event.currentTarget.getBoundingClientRect(); setCoverPreview({ url: topic.cover_url!, x: Math.min(rect.right + 12, window.innerWidth - 550), y: Math.min(rect.top, window.innerHeight - 370) }) }} onMouseLeave={() => setCoverPreview(null)} /> : <span className="text-slate-400">—</span>}</td><td className="max-w-[240px] px-4 py-3 font-medium text-slate-900 dark:text-slate-100">{topic.title}</td><td className="max-w-[300px] truncate px-4 py-3 text-slate-500">{topic.description || '—'}</td><td className="px-4 py-3"><span className="rounded-full bg-violet-50 px-2 py-1 text-xs text-violet-700 dark:bg-violet-950 dark:text-violet-300">{statusLabel[topic.status]}</span></td><td className="whitespace-nowrap px-4 py-3 text-slate-500">{localDateTime(topic.status === 'published' ? topic.published_at : topic.scheduled_at)}</td><td className="px-4 py-3"><div className="flex flex-wrap gap-1">{topic.publications.length ? topic.publications.map((item) => <span key={item.id} className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">{platformLabel[item.platform] || item.platform}</span>) : <span className="text-slate-500">—</span>}</div></td></tr>)}</tbody>
      </table>
    </div>
    {coverPreview && createPortal(<div className="pointer-events-none fixed z-50 rounded-md border border-slate-200 bg-white p-1 shadow-2xl dark:border-slate-700 dark:bg-slate-900" style={{ left: coverPreview.x, top: coverPreview.y }}><img src={coverPreview.url} alt="封面预览" className="h-[22rem] w-[33rem] rounded object-cover" /></div>, document.body)}
  </div>
}
