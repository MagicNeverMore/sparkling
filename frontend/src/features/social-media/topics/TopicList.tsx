import { useCallback, useEffect, useState } from 'react'
import { Filter, Plus, Search } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../../lib/api'
import type { Topic, TopicListResponse, TopicStatus } from './types'

const statusLabel: Record<TopicStatus, string> = { not_started: '未开始', working: '工作中', published: '已发布' }
const localDateTime = (value: string | null) => value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'

export default function TopicList() {
  const navigate = useNavigate()
  const [data, setData] = useState<TopicListResponse>({ items: [], categories: [] })
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<TopicStatus | ''>('')
  const [category, setCategory] = useState('')
  const [loading, setLoading] = useState(true)

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
      <table className="w-full min-w-[1000px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500 dark:bg-slate-950"><tr><th className="px-4 py-3">封面</th><th className="px-4 py-3">标题</th><th className="px-4 py-3">详情</th><th className="px-4 py-3">状态</th><th className="px-4 py-3">发布时间</th><th className="px-4 py-3">发布平台</th></tr></thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">{loading ? <tr><td colSpan={6} className="p-10 text-center text-slate-500">加载中…</td></tr> : data.items.length === 0 ? <tr><td colSpan={6} className="p-10 text-center text-slate-500">暂无选题</td></tr> : data.items.map((topic: Topic) => <tr key={topic.id} onClick={() => navigate(`/social-media/topics/${topic.id}`)} className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-950/50"><td className="px-4 py-3">{topic.cover_url ? <img src={topic.cover_url} alt="" className="h-10 w-16 rounded object-cover" /> : <span className="text-slate-400">—</span>}</td><td className="max-w-[240px] px-4 py-3 font-medium text-slate-900 dark:text-slate-100">{topic.title}</td><td className="max-w-[300px] truncate px-4 py-3 text-slate-500">{topic.description || '—'}</td><td className="px-4 py-3"><span className="rounded-full bg-violet-50 px-2 py-1 text-xs text-violet-700 dark:bg-violet-950 dark:text-violet-300">{statusLabel[topic.status]}</span></td><td className="whitespace-nowrap px-4 py-3 text-slate-500">{localDateTime(topic.status === 'published' ? topic.published_at : topic.scheduled_at)}</td><td className="px-4 py-3 text-slate-500">{topic.publications.map((item) => item.platform).join('、') || '—'}</td></tr>)}</tbody>
      </table>
    </div>
  </div>
}
