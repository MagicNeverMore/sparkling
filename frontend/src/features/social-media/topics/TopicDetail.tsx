import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, Pencil, Plus, Search, Trash2, Upload } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../../lib/api'
import { useToast } from '../../../components/useToast'
import type { SocialVideo, Topic, TopicStatus } from './types'

type PublicationDraft = { platform: string; social_media_video_id: string | null }

const labels: Record<TopicStatus, string> = { not_started: '未开始', working: '工作中', published: '已发布' }
const platforms = [
  { value: 'youtube', label: 'YouTube' },
  { value: 'bilibili', label: '哔哩哔哩' },
  { value: 'douyin', label: '抖音' },
  { value: 'xiaohongshu', label: '小红书' },
  { value: 'wechat_channels', label: '视频号' },
]
const emptyPublication = (): PublicationDraft => ({ platform: 'youtube', social_media_video_id: null })
const toIso = (value: string) => value ? new Date(value).toISOString() : null
const toLocalInput = (value: string | null) => {
  if (!value) return ''
  const date = new Date(value)
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export default function TopicDetail() {
  const { id = 'new' } = useParams()
  const isNew = id === 'new'
  const navigate = useNavigate()
  const { show } = useToast()
  const [topic, setTopic] = useState<Topic | null>(null)
  const [editing, setEditing] = useState(isNew)
  const [videos, setVideos] = useState<SocialVideo[]>([])
  const [videoQuery, setVideoQuery] = useState('')
  const [coverFile, setCoverFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('')
  const [status, setStatus] = useState<TopicStatus>('not_started')
  const [scheduledAt, setScheduledAt] = useState('')
  const [publishedAt, setPublishedAt] = useState('')
  const [publications, setPublications] = useState<PublicationDraft[]>([])
  const [saving, setSaving] = useState(false)
  const hasYouTube = publications.some((publication) => publication.platform === 'youtube')

  useEffect(() => {
    if (!hasYouTube) { setVideos([]); return }
    const params = new URLSearchParams({ platform: 'youtube' })
    if (videoQuery.trim()) params.set('query', videoQuery.trim())
    void api.get<SocialVideo[]>(`/api/social-media/topic/videos?${params}`).then(setVideos).catch((error) => show(error instanceof Error ? error.message : String(error), 'error'))
  }, [hasYouTube, show, videoQuery])

  useEffect(() => {
    if (isNew) return
    void api.get<Topic>(`/api/social-media/topic/${id}`).then((value) => {
      setTopic(value); setTitle(value.title); setDescription(value.description || ''); setCategory(value.category || '')
      setStatus(value.status); setScheduledAt(toLocalInput(value.scheduled_at)); setPublishedAt(toLocalInput(value.published_at))
      setPublications(value.publications.map((item) => ({ platform: item.platform, social_media_video_id: item.social_media_video_id })))
    }).catch((error) => show(error instanceof Error ? error.message : String(error), 'error'))
  }, [id, isNew, show])

  const payload = useMemo(() => ({
    title: title.trim(), description: description.trim() || null, category: category.trim() || null, status,
    scheduled_at: toIso(scheduledAt), published_at: toIso(publishedAt),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, publications,
  }), [category, description, publications, publishedAt, scheduledAt, status, title])

  const uploadCover = async (target: Topic, file: File) => {
    const form = new FormData(); form.append('file', file)
    const response = await fetch(`/api/social-media/topic/${target.id}/cover`, { method: 'POST', credentials: 'include', body: form })
    if (!response.ok) throw new Error(await response.text())
    return response.json() as Promise<Topic>
  }

  const save = async () => {
    if (!title.trim()) return
    setSaving(true)
    try {
      let saved = isNew ? await api.post<Topic>('/api/social-media/topic', payload) : await api.patch<Topic>(`/api/social-media/topic/${id}`, payload)
      if (coverFile) saved = await uploadCover(saved, coverFile)
      setTopic(saved); setCoverFile(null); setEditing(false)
      show(isNew ? '选题已创建' : '选题已保存', 'success')
      if (isNew) navigate(`/social-media/topics/${saved.id}`, { replace: true })
    } catch (error) { show(error instanceof Error ? error.message : String(error), 'error') } finally { setSaving(false) }
  }

  const removeCover = async () => {
    if (!topic) return
    try { setTopic(await api.del<Topic>(`/api/social-media/topic/${topic.id}/cover`)); show('封面已移除', 'success') } catch (error) { show(error instanceof Error ? error.message : String(error), 'error') }
  }
  const deleteTopic = async () => {
    if (!topic || !window.confirm(`确认删除选题「${topic.title}」？`)) return
    try { await api.del(`/api/social-media/topic/${topic.id}`); show('选题已删除', 'success'); navigate('/social-media/topics', { replace: true }) } catch (error) { show(error instanceof Error ? error.message : String(error), 'error') }
  }
  const updatePublication = (index: number, update: Partial<PublicationDraft>) => setPublications((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, ...update } : item))
  const selectVideo = (index: number, videoId: string) => {
    const video = videos.find((item) => item.id === videoId)
    updatePublication(index, { social_media_video_id: videoId || null, platform: video?.platform || 'youtube' })
  }

  return <div className="mx-auto max-w-3xl space-y-5 px-4 py-6 md:px-6">
    <Link to="/social-media/topics" className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-violet-500"><ArrowLeft size={16} />返回选题库</Link>
    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-5 flex items-center justify-between gap-3"><h1 className="text-xl font-semibold">{isNew ? '新建选题' : '选题详情'}</h1><div className="flex items-center gap-3">{topic?.task_id && <Link to="/tasks" className="text-sm text-violet-500">关联任务{topic.task_completed ? '（已完成）' : ''}</Link>}{!isNew && !editing && <button type="button" onClick={() => setEditing(true)} className="inline-flex items-center gap-2 rounded-md bg-violet-500 px-3 py-2 text-sm font-medium text-white"><Pencil size={16} />编辑</button>}{!isNew && <button type="button" onClick={() => void deleteTopic()} className="text-sm text-rose-500">删除</button>}</div></div>
      <div className="space-y-4">
        <label className="block text-sm">标题<input disabled={!editing} value={title} onChange={(event) => setTitle(event.target.value)} className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 disabled:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:disabled:bg-slate-800" /></label>
        <label className="block text-sm">详情<textarea disabled={!editing} value={description} onChange={(event) => setDescription(event.target.value)} rows={5} className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 disabled:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:disabled:bg-slate-800" /></label>
        <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">分类<input disabled={!editing} value={category} onChange={(event) => setCategory(event.target.value)} className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 disabled:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:disabled:bg-slate-800" /></label><label className="text-sm">状态<select disabled={!editing} value={status} onChange={(event) => setStatus(event.target.value as TopicStatus)} className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 disabled:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:disabled:bg-slate-800">{Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="text-sm">预计发布时间<input disabled={!editing} type="datetime-local" value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 disabled:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:disabled:bg-slate-800" /></label><label className="text-sm">实际发布时间<input disabled={!editing} type="datetime-local" value={publishedAt} onChange={(event) => setPublishedAt(event.target.value)} className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 disabled:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:disabled:bg-slate-800" /></label></div>
        <div className="rounded-md border border-slate-200 p-3 dark:border-slate-700">{topic?.cover_url ? <img src={topic.cover_url} alt="选题封面" className="mb-3 max-h-52 rounded object-cover" /> : null}{coverFile && <p className="mb-2 text-sm text-slate-500">待上传：{coverFile.name}</p>}{editing && <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-violet-500"><Upload size={16} />{topic?.cover_url ? '替换封面' : '选择封面'}<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden" onChange={(event) => setCoverFile(event.target.files?.[0] || null)} /></label>}{editing && topic?.cover_url && <button type="button" onClick={() => void removeCover()} className="ml-4 text-sm text-rose-500">移除封面</button>}</div>
        <div><div className="mb-2 flex items-center justify-between"><span className="text-sm font-medium">发布平台</span>{editing && <button type="button" onClick={() => setPublications((items) => [...items, emptyPublication()])} className="inline-flex items-center gap-1 text-sm text-violet-500"><Plus size={15} />添加</button>}</div>{publications.length === 0 && <p className="text-sm text-slate-500">尚未添加发布平台</p>}{publications.map((item, index) => <div key={index} className="mb-3 rounded-md border border-slate-200 p-3 dark:border-slate-700"><div className="flex gap-2"><select disabled={!editing} value={item.platform} onChange={(event) => updatePublication(index, { platform: event.target.value, social_media_video_id: null })} className="w-36 rounded-md border border-slate-200 px-2 py-1.5 text-sm disabled:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:disabled:bg-slate-800">{platforms.map((platform) => <option key={platform.value} value={platform.value}>{platform.label}</option>)}</select>{editing && <button type="button" onClick={() => setPublications((items) => items.filter((_, itemIndex) => itemIndex !== index))} className="ml-auto text-rose-500"><Trash2 size={16} /></button>}</div>{item.platform === 'youtube' && <div className="mt-2 space-y-2"><label className="flex items-center gap-2 rounded-md border border-slate-200 px-2 py-1.5 text-sm dark:border-slate-700"><Search size={15} className="text-slate-400" /><input disabled={!editing} value={videoQuery} onChange={(event) => setVideoQuery(event.target.value)} placeholder="搜索 YouTube 视频标题" className="min-w-0 flex-1 bg-transparent outline-none" /></label><select disabled={!editing} value={item.social_media_video_id || ''} onChange={(event) => selectVideo(index, event.target.value)} className="w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm disabled:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:disabled:bg-slate-800"><option value="">不关联视频</option>{videos.map((video) => <option key={video.id} value={video.id}>{video.title}</option>)}</select></div>}</div>)}</div>
        {editing && <div className="flex gap-3"><button type="button" disabled={saving || !title.trim()} onClick={() => void save()} className="rounded-md bg-violet-500 px-4 py-2 text-sm font-medium text-white disabled:bg-slate-400">{saving ? '保存中…' : '保存'}</button>{!isNew && <button type="button" disabled={saving} onClick={() => setEditing(false)} className="rounded-md border border-slate-200 px-4 py-2 text-sm dark:border-slate-700">取消</button>}</div>}
      </div>
    </div>
  </div>
}
