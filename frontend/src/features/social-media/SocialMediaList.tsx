import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, ExternalLink, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../../lib/api'
import { useI18n } from '../../lib/I18nProvider'
import { useToast } from '../../components/useToast'
import type {
  SocialMediaListResponse,
  SocialMediaMetricDateListResponse,
  SocialMediaMetricListResponse,
  SocialMediaRun,
  SocialMediaSyncRequest,
  SocialMediaVideo,
  SocialMediaVideoListResponse,
} from './types'

const formatDuration = (seconds: number | null) => {
  if (seconds === null) return '—'
  const total = Math.max(0, Math.round(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const rest = total % 60
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
    : `${minutes}:${String(rest).padStart(2, '0')}`
}

const formatPercent = (value: number | null) => value === null ? '—' : `${value.toFixed(2)}%`
const formatNet = (value: number) => value > 0 ? `+${value.toLocaleString()}` : value.toLocaleString()
const fetchAllVideos = async (): Promise<SocialMediaVideoListResponse> => {
  const limit = 200
  const first = await api.get<SocialMediaVideoListResponse>(`/api/social-media/list/videos?limit=${limit}`)
  const items = [...first.items]
  for (let offset = items.length; offset < first.total; offset += limit) {
    const page = await api.get<SocialMediaVideoListResponse>(`/api/social-media/list/videos?limit=${limit}&offset=${offset}`)
    items.push(...page.items)
  }
  return { total: first.total, items }
}

type PageData = {
  list: SocialMediaListResponse
  metricDates: string[]
  run: SocialMediaRun | null
}

const fetchPageData = async (dataDate?: string): Promise<PageData> => {
  const metricUrl = dataDate
    ? `/api/social-media/list/video-metrics?data_date=${encodeURIComponent(dataDate)}`
    : '/api/social-media/list/video-metrics'
  const [videos, metrics, metricDates, latestRun] = await Promise.all([
    fetchAllVideos(),
    api.get<SocialMediaMetricListResponse>(metricUrl),
    api.get<SocialMediaMetricDateListResponse>('/api/social-media/list/video-metric-dates'),
    api.get<SocialMediaRun | null>('/api/social-media/list/runs/latest'),
  ])
  const metricByVideoId = new Map(metrics.items.map((item) => [item.video_id, item]))
  return {
    list: {
      data_date: metrics.data_date,
      updated_at: metrics.updated_at,
      total: videos.total,
      items: videos.items.map((video) => {
        const metric = metricByVideoId.get(video.id)
        return {
          ...video,
          ctr: metric?.ctr ?? null,
          average_view_duration_seconds: metric?.average_view_duration_seconds ?? null,
          average_view_percentage: metric?.average_view_percentage ?? null,
          views: metric?.views ?? 0,
          subscribers_gained: metric?.subscribers_gained ?? 0,
          subscribers_lost: metric?.subscribers_lost ?? 0,
          net_subscribers: metric?.net_subscribers ?? 0,
        }
      }),
    },
    metricDates: metricDates.items,
    run: latestRun,
  }
}

type SortKey = keyof Pick<SocialMediaVideo,
  'title' | 'published_at' | 'platform' | 'ctr' | 'average_view_duration_seconds'
  | 'average_view_percentage' | 'duration_seconds' | 'views' | 'net_subscribers'
>
type SortDirection = 'asc' | 'desc'

const compareValues = (left: string | number | null, right: string | number | null) => {
  if (left === null) return right === null ? 0 : 1
  if (right === null) return -1
  if (typeof left === 'number' && typeof right === 'number') return left - right
  return String(left).localeCompare(String(right))
}

export default function SocialMediaList() {
  const { t } = useI18n()
  const { show } = useToast()
  const [data, setData] = useState<SocialMediaListResponse | null>(null)
  const [run, setRun] = useState<SocialMediaRun | null>(null)
  const [loading, setLoading] = useState(true)
  const [platformFilter, setPlatformFilter] = useState('')
  const [selectedDataDate, setSelectedDataDate] = useState<string | null>(null)
  const [metricDates, setMetricDates] = useState<string[]>([])
  const [sortKey, setSortKey] = useState<SortKey>('published_at')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const syncing = run?.status === 'running'

  const platforms = useMemo(
    () => Array.from(new Set(data?.items.map((item) => item.platform) ?? [])).sort((a, b) => a.localeCompare(b)),
    [data?.items],
  )
  const visibleItems = useMemo(() => {
    const filtered = data?.items.filter((item) => !platformFilter || item.platform === platformFilter) ?? []
    return filtered
      .map((item, index) => ({ item, index }))
      .sort((left, right) => {
        const result = compareValues(left.item[sortKey], right.item[sortKey])
        return result === 0 ? left.index - right.index : sortDirection === 'asc' ? result : -result
      })
      .map(({ item }) => item)
  }, [data?.items, platformFilter, sortDirection, sortKey])
  const statistics = useMemo(() => visibleItems.reduce(
    (total, item) => ({
      videoCount: total.videoCount + 1,
      views: total.views + item.views,
      netSubscribers: total.netSubscribers + item.net_subscribers,
    }),
    { videoCount: 0, views: 0, netSubscribers: 0 },
  ), [visibleItems])

  const toggleSort = (nextKey: SortKey) => {
    if (nextKey === sortKey) {
      setSortDirection((current) => current === 'asc' ? 'desc' : 'asc')
      return
    }
    setSortKey(nextKey)
    setSortDirection('desc')
  }

  const load = useCallback(async () => {
    try {
      const page = await fetchPageData(selectedDataDate ?? undefined)
      setData(page.list)
      setMetricDates(page.metricDates)
      setSelectedDataDate((current) => current && page.metricDates.includes(current) ? current : page.list.data_date)
      setRun(page.run)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      show(t('socialMedia.loadFailed', { message }), 'error')
    } finally {
      setLoading(false)
    }
  }, [selectedDataDate, show, t])

  useEffect(() => {
    let active = true
    void fetchPageData(selectedDataDate ?? undefined)
      .then((page) => {
        if (!active) return
        setData(page.list)
        setMetricDates(page.metricDates)
        setSelectedDataDate((current) => current && page.metricDates.includes(current) ? current : page.list.data_date)
        setRun(page.run)
      })
      .catch((error) => {
        if (!active) return
        const message = error instanceof Error ? error.message : String(error)
        show(t('socialMedia.loadFailed', { message }), 'error')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [selectedDataDate, show, t])
  useEffect(() => {
    const timer = window.setInterval(() => void load(), 5000)
    return () => window.clearInterval(timer)
  }, [load])

  const syncNow = async () => {
    try {
      await api.post<SocialMediaSyncRequest>('/api/social-media/list/sync')
      show(t('socialMedia.syncStarted'), 'success')
      await load()
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(message, 'error')
    }
  }

  const localDateTime = (value: string | null) => value
    ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
    : '—'

  const sortIcon = (key: SortKey) => {
    if (sortKey !== key) return <ArrowUpDown size={14} aria-hidden="true" />
    return sortDirection === 'asc'
      ? <ArrowUp size={14} aria-hidden="true" />
      : <ArrowDown size={14} aria-hidden="true" />
  }

  const sortableHeader = (label: string, key: SortKey, align = 'left') => (
    <th className={`px-4 py-3 ${align === 'right' ? 'text-right' : ''}`} aria-sort={sortKey === key ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button type="button" onClick={() => toggleSort(key)} className={`inline-flex items-center gap-1 font-medium transition hover:text-slate-900 dark:hover:text-slate-100 ${align === 'right' ? 'justify-end' : ''}`}>
        {label}{sortIcon(key)}
      </button>
    </th>
  )

  return (
    <div className="mx-auto max-w-[1500px] space-y-5 px-4 py-6 md:px-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-950 dark:text-slate-100">{t('socialMedia.title')}</h1>
          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-slate-500 dark:text-slate-400">
            <label className="flex items-center gap-2">
              <span>{t('socialMedia.metricDate')}:</span>
              <select value={selectedDataDate ?? data?.data_date ?? ''} onChange={(event) => setSelectedDataDate(event.target.value || null)} disabled={!metricDates.length} className="rounded-md border border-slate-200 bg-white px-2 py-1 text-sm text-slate-900 outline-none focus:border-violet-400 disabled:cursor-not-allowed disabled:bg-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:disabled:bg-slate-800">
                {!data?.data_date && <option value="">—</option>}
                {metricDates.map((date) => <option key={date} value={date}>{date}</option>)}
              </select>
            </label>
            <span>{t('socialMedia.updatedAt')}: {localDateTime(data?.updated_at ?? null)}</span>
          </div>
        </div>
        <button type="button" onClick={() => void syncNow()} disabled={syncing} className="flex items-center gap-2 rounded-md bg-violet-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-violet-400 disabled:cursor-not-allowed disabled:bg-slate-300 dark:disabled:bg-slate-800">
          <RefreshCw size={16} className={syncing ? 'animate-spin' : ''} />
          {syncing ? t('socialMedia.syncing') : t('socialMedia.syncNow')}
        </button>
      </div>

      {run?.status === 'failed' && run.error && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/50 dark:text-rose-200">
          {run.error}
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
        {loading ? (
          <div className="p-10 text-center text-sm text-slate-500">{t('common.loading')}</div>
        ) : !data?.items.length ? (
          <div className="p-10 text-center">
            <p className="text-sm text-slate-500">{t('socialMedia.empty')}</p>
            <Link to="/settings?section=social-media" className="mt-3 inline-block text-sm text-violet-500 hover:text-violet-400">{t('socialMedia.openSettings')}</Link>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
              <label className="flex w-full max-w-[220px] items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
                <span>{t('socialMedia.platformFilter')}</span>
                <select value={platformFilter} onChange={(event) => setPlatformFilter(event.target.value)} className="min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm text-slate-900 outline-none focus:border-violet-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100">
                  <option value="">{t('socialMedia.allPlatforms')}</option>
                  {platforms.map((platform) => <option key={platform} value={platform}>{platform}</option>)}
                </select>
              </label>
              <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-slate-600 dark:text-slate-300">
                <span>{t('socialMedia.totalVideos')}: <strong className="tabular-nums text-slate-900 dark:text-slate-100">{statistics.videoCount.toLocaleString()}</strong></span>
                <span>{t('socialMedia.totalViews')}: <strong className="tabular-nums text-slate-900 dark:text-slate-100">{statistics.views.toLocaleString()}</strong></span>
                <span>{t('socialMedia.totalSubscriberGrowth')}: <strong className="tabular-nums text-slate-900 dark:text-slate-100">{formatNet(statistics.netSubscribers)}</strong></span>
              </div>
            </div>
            <div className="overflow-x-auto">
            <table className="w-full min-w-[1400px] table-fixed text-left text-sm">
              <colgroup>
                <col className="w-[320px]" />
                <col className="w-[180px]" />
                <col className="w-[100px]" />
                <col className="w-[80px]" />
                <col className="w-[90px]" />
                <col className="w-[80px]" />
                <col className="w-[90px]" />
                <col className="w-[100px]" />
                <col className="w-[120px]" />
                <col className="w-[120px]" />
                <col className="w-[180px]" />
              </colgroup>
              <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-400">
                <tr>
                  {sortableHeader(t('socialMedia.videoName'), 'title')}
                  {sortableHeader(t('socialMedia.publishedAt'), 'published_at')}
                  {sortableHeader(t('socialMedia.platform'), 'platform')}
                  {sortableHeader('CTR', 'ctr', 'right')}
                  {sortableHeader('AVD', 'average_view_duration_seconds', 'right')}
                  {sortableHeader('AVP', 'average_view_percentage', 'right')}
                  {sortableHeader(t('socialMedia.duration'), 'duration_seconds', 'right')}
                  {sortableHeader(t('socialMedia.views'), 'views', 'right')}
                  {sortableHeader(t('socialMedia.subscriberGrowth'), 'net_subscribers', 'right')}
                  <th className="px-4 py-3">{t('socialMedia.metricDate')}</th>
                  <th className="px-4 py-3">{t('socialMedia.updatedAt')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {visibleItems.map((video) => (
                  <tr key={video.id} className="hover:bg-slate-50/70 dark:hover:bg-slate-950/40">
                    <td className="px-4 py-3 font-medium text-slate-900 dark:text-slate-100">
                      <a href={`https://www.youtube.com/watch?v=${video.external_video_id}`} target="_blank" rel="noreferrer" title={video.title} className="flex min-w-0 items-center gap-1.5 hover:text-violet-500">
                        <span className="min-w-0 flex-1 truncate">{video.title}</span><ExternalLink size={13} className="shrink-0" />
                      </a>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-500">{localDateTime(video.published_at)}</td>
                    <td className="px-4 py-3"><span className="inline-flex rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700 dark:bg-red-950/50 dark:text-red-300">{video.platform}</span></td>
                    <td className="px-4 py-3 text-right tabular-nums">{formatPercent(video.ctr)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{formatDuration(video.average_view_duration_seconds)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{formatPercent(video.average_view_percentage)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{formatDuration(video.duration_seconds)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{video.views.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right tabular-nums" title={`${t('socialMedia.gained')} ${video.subscribers_gained} / ${t('socialMedia.lost')} ${video.subscribers_lost}`}>{formatNet(video.net_subscribers)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-500">{data.data_date}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-500">{localDateTime(data.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          </>
        )}
      </div>
      {data && data.total > 0 && <div className="text-sm text-slate-500">{t('socialMedia.total', { count: visibleItems.length })}</div>}
    </div>
  )
}
