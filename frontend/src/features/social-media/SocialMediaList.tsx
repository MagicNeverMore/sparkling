import { useCallback, useEffect, useState } from 'react'
import { ExternalLink, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../../lib/api'
import { useI18n } from '../../lib/I18nProvider'
import { useToast } from '../../components/useToast'
import type { SocialMediaListResponse, SocialMediaRun, SocialMediaSyncRequest } from './types'

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
const fetchPageData = () => Promise.all([
  api.get<SocialMediaListResponse>('/api/social-media/videos'),
  api.get<SocialMediaRun | null>('/api/social-media/runs/latest'),
])

export default function SocialMediaList() {
  const { t } = useI18n()
  const { show } = useToast()
  const [data, setData] = useState<SocialMediaListResponse | null>(null)
  const [run, setRun] = useState<SocialMediaRun | null>(null)
  const [loading, setLoading] = useState(true)
  const syncing = run?.status === 'running'

  const load = useCallback(async () => {
    try {
      const [list, latestRun] = await fetchPageData()
      setData(list)
      setRun(latestRun)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      show(t('socialMedia.loadFailed', { message }), 'error')
    } finally {
      setLoading(false)
    }
  }, [show, t])

  useEffect(() => {
    let active = true
    void fetchPageData()
      .then(([list, latestRun]) => {
        if (!active) return
        setData(list)
        setRun(latestRun)
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
  }, [show, t])
  useEffect(() => {
    const timer = window.setInterval(() => void load(), 5000)
    return () => window.clearInterval(timer)
  }, [load])

  const syncNow = async () => {
    try {
      await api.post<SocialMediaSyncRequest>('/api/social-media/sync')
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

  return (
    <div className="mx-auto max-w-[1500px] space-y-5 px-4 py-6 md:px-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-950 dark:text-slate-100">{t('socialMedia.title')}</h1>
          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-slate-500 dark:text-slate-400">
            <span>{t('socialMedia.metricDate')}: {data?.metric_date ?? '—'}</span>
            <span>{t('socialMedia.updatedAt')}: {localDateTime(data?.collected_at ?? null)}</span>
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
          <div className="overflow-x-auto">
            <table className="min-w-[1260px] w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-400">
                <tr>
                  <th className="px-4 py-3">{t('socialMedia.videoName')}</th>
                  <th className="px-4 py-3">{t('socialMedia.publishedAt')}</th>
                  <th className="px-4 py-3">{t('socialMedia.platform')}</th>
                  <th className="px-4 py-3 text-right">CTR</th>
                  <th className="px-4 py-3 text-right">AVD</th>
                  <th className="px-4 py-3 text-right">AVP</th>
                  <th className="px-4 py-3 text-right">{t('socialMedia.duration')}</th>
                  <th className="px-4 py-3 text-right">{t('socialMedia.views')}</th>
                  <th className="px-4 py-3 text-right">{t('socialMedia.subscriberGrowth')}</th>
                  <th className="px-4 py-3">{t('socialMedia.updatedAt')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {data.items.map((video) => (
                  <tr key={video.id} className="hover:bg-slate-50/70 dark:hover:bg-slate-950/40">
                    <td className="max-w-sm px-4 py-3 font-medium text-slate-900 dark:text-slate-100">
                      <a href={`https://www.youtube.com/watch?v=${video.external_video_id}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 hover:text-violet-500">
                        <span className="truncate">{video.title}</span><ExternalLink size={13} className="shrink-0" />
                      </a>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-500">{localDateTime(video.published_at)}</td>
                    <td className="px-4 py-3 text-slate-500">{video.platform}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{formatPercent(video.ctr)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{formatDuration(video.average_view_duration_seconds)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{formatPercent(video.average_view_percentage)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{formatDuration(video.duration_seconds)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{video.views.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right tabular-nums" title={`${t('socialMedia.gained')} ${video.subscribers_gained} / ${t('socialMedia.lost')} ${video.subscribers_lost}`}>{formatNet(video.net_subscribers)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-500">{localDateTime(data.collected_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {data && data.total > 0 && <div className="text-sm text-slate-500">{t('socialMedia.total', { count: data.total })}</div>}
    </div>
  )
}
