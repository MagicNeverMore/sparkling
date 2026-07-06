import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, ExternalLink, RefreshCw, Search, Tag } from 'lucide-react'
import EmptyState from '../../components/EmptyState'
import { useToast } from '../../components/useToast'
import { api, ApiError } from '../../lib/api'
import { formatDateTime, formatRelative } from '../../lib/time'
import { useI18n } from '../../lib/I18nProvider'
import type { TrendItem, TrendListRaw, TrendRun } from './types'

const sourceOptions = ['reddit', 'github', 'hackernews', 'google']

export default function Trends() {
  const { lang, t } = useI18n()
  const { show } = useToast()
  const [items, setItems] = useState<TrendItem[]>([])
  const [total, setTotal] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [tagFilter, setTagFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const [latestRun, setLatestRun] = useState<TrendRun | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const selected = useMemo(
    () => items.find((item) => item.id === selectedId) ?? items[0] ?? null,
    [items, selectedId],
  )

  const categories = useMemo(() => {
    const set = new Set(items.map((item) => item.category).filter(Boolean) as string[])
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [items])

  useEffect(() => {
    const params = new URLSearchParams()
    if (query.trim()) params.set('q', query.trim())
    if (category) params.set('category', category)
    if (tagFilter.trim()) params.set('tag', tagFilter.trim())
    if (sourceFilter) params.set('source', sourceFilter)
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true)
    void api
      .get<TrendListRaw>(`/api/trends${params.toString() ? `?${params.toString()}` : ''}`)
      .then((result) => {
        setItems(result.items)
        setTotal(result.total)
        if (!selectedId || !result.items.some((item) => item.id === selectedId)) {
          setSelectedId(result.items[0]?.id ?? null)
        }
      })
      .catch((error) => {
        const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
        show(t('trends.loadFailed', { message }), 'error')
      })
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, category, tagFilter, sourceFilter, reloadKey])

  const loadLatestRun = () => {
    void api
      .get<TrendRun | null>('/api/trends/runs/latest')
      .then((run) => {
        setLatestRun(run)
        setRunning(run?.status === 'pending' || run?.status === 'running')
      })
      .catch(() => setLatestRun(null))
  }

  useEffect(() => {
    loadLatestRun()
    const timer = window.setInterval(() => {
      loadLatestRun()
      if (latestRun?.status === 'pending' || latestRun?.status === 'running') {
        setReloadKey((value) => value + 1)
      }
    }, 4000)
    return () => window.clearInterval(timer)
  }, [latestRun?.status])

  const runNow = async () => {
    setRunning(true)
    try {
      const run = await api.post<TrendRun>('/api/trends/run')
      setLatestRun(run)
      show(t('trends.runStarted'), 'success')
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(t('trends.runFailed', { message }), 'error')
      setRunning(false)
    }
  }

  const clearFilters = () => {
    setQuery('')
    setCategory('')
    setTagFilter('')
    setSourceFilter('')
  }

  const runStatusText = latestRun
    ? `${t(`trends.run.${latestRun.status}`)} · ${t('trends.runStats', { candidates: latestRun.candidate_count, saved: latestRun.saved_count })}`
    : t('trends.noRuns')

  return (
    <div className="mx-auto flex h-full w-full max-w-7xl flex-col px-4 py-6 md:px-6">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-950 dark:text-slate-100">{t('trends.title')}</h1>
          <p className="mt-1 text-sm text-slate-500">{runStatusText}</p>
          {latestRun?.error && (
            <div className="mt-2 flex items-center gap-2 text-sm text-rose-500">
              <AlertCircle size={15} />
              <span>{latestRun.error}</span>
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={runNow}
          disabled={running}
          className="inline-flex items-center gap-2 rounded-md bg-violet-500 px-3 py-2 text-sm font-medium text-white transition hover:bg-violet-400 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500 dark:disabled:bg-slate-800"
        >
          <RefreshCw size={16} className={running ? 'animate-spin' : ''} />
          {running ? t('trends.running') : t('trends.runNow')}
        </button>
      </div>

      <div className="mb-4 grid gap-3 md:grid-cols-[1fr_160px_150px_150px_auto]">
        <label className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t('trends.searchPlaceholder')}
            className="h-10 w-full rounded-md border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-950 outline-none focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
          />
        </label>
        <select
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200"
        >
          <option value="">{t('trends.allCategories')}</option>
          {categories.map((value) => (
            <option key={value} value={value}>{value}</option>
          ))}
        </select>
        <select
          value={sourceFilter}
          onChange={(event) => setSourceFilter(event.target.value)}
          className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200"
        >
          <option value="">{t('trends.allSources')}</option>
          {sourceOptions.map((value) => (
            <option key={value} value={value}>{value}</option>
          ))}
        </select>
        <label className="relative">
          <Tag className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={15} />
          <input
            value={tagFilter}
            onChange={(event) => setTagFilter(event.target.value)}
            placeholder="Tag"
            className="h-10 w-full rounded-md border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-950 outline-none focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
          />
        </label>
        <button
          type="button"
          onClick={clearFilters}
          className="h-10 rounded-md border border-slate-200 px-3 text-sm text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:border-slate-800 dark:hover:bg-slate-900 dark:hover:text-slate-200"
        >
          {t('trends.clear')}
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        {loading ? (
          <div className="flex h-96 items-center justify-center text-sm text-slate-500">{t('common.loading')}</div>
        ) : items.length === 0 ? (
          <div className="p-4">
            <EmptyState icon="↗" title={t('trends.emptyTitle')} description={t('trends.emptyDesc')} />
          </div>
        ) : (
          <div className="grid h-full min-h-[560px] md:grid-cols-[360px_1fr]">
            <div className="min-h-0 overflow-auto border-b border-slate-200 md:border-b-0 md:border-r dark:border-slate-800">
              <div className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 px-3 py-2 text-xs text-slate-500 backdrop-blur dark:border-slate-800 dark:bg-slate-900/95">
                {t('trends.total', { count: total })}
              </div>
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedId(item.id)}
                  className={`block w-full border-b border-slate-100 px-4 py-3 text-left transition dark:border-slate-800 ${
                    selected?.id === item.id
                      ? 'bg-violet-50 dark:bg-slate-800'
                      : 'hover:bg-slate-50 dark:hover:bg-slate-950/60'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="line-clamp-2 text-sm font-medium leading-5 text-slate-950 dark:text-slate-100">{item.title}</div>
                      <div className="mt-1 text-xs text-slate-500">{formatRelative(item.last_seen_at, lang)}</div>
                    </div>
                    <span className="rounded-md border border-slate-200 px-2 py-1 font-mono text-xs text-slate-600 dark:border-slate-700 dark:text-slate-300">
                      {Math.round(item.score)}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {item.category && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500 dark:bg-slate-950 dark:text-slate-400">{item.category}</span>}
                    {item.resources.slice(0, 2).map((resource) => (
                      <span key={`${item.id}-${resource.url}`} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500 dark:bg-slate-950 dark:text-slate-400">
                        {resource.source}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
            </div>

            {selected && (
              <article className="min-h-0 overflow-auto p-5 md:p-6">
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  {selected.category && <span className="rounded-md border border-slate-200 px-2 py-1 dark:border-slate-700">{selected.category}</span>}
                  <span className="rounded-md border border-slate-200 px-2 py-1 font-mono dark:border-slate-700">score {selected.score.toFixed(0)}</span>
                  <span>{formatDateTime(selected.last_seen_at, lang)}</span>
                </div>
                <h2 className="mt-4 text-2xl font-semibold leading-tight text-slate-950 dark:text-slate-100">{selected.title}</h2>
                {selected.scoring_reason && (
                  <p className="mt-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
                    {selected.scoring_reason}
                  </p>
                )}

                <section className="mt-6">
                  <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-100">Core Insight</h3>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-700 dark:text-slate-300">
                    {selected.core_insight || t('trends.noInsight')}
                  </p>
                </section>

                <section className="mt-6">
                  <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-100">Content</h3>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-700 dark:text-slate-300">
                    {selected.content || t('trends.noContent')}
                  </p>
                </section>

                {selected.tags.length > 0 && (
                  <section className="mt-6">
                    <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-100">Tags</h3>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {selected.tags.map((tag) => (
                        <span key={tag} className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-600 dark:bg-slate-950 dark:text-slate-300">
                          #{tag}
                        </span>
                      ))}
                    </div>
                  </section>
                )}

                <section className="mt-6">
                  <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-100">Resources</h3>
                  <div className="mt-2 divide-y divide-slate-100 rounded-md border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
                    {selected.resources.map((resource) => (
                      <a
                        key={resource.url}
                        href={resource.url}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-start justify-between gap-3 px-3 py-2 text-sm transition hover:bg-slate-50 dark:hover:bg-slate-950/60"
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-slate-800 dark:text-slate-200">{resource.title}</span>
                          <span className="mt-0.5 block text-xs text-slate-500">{resource.source}</span>
                        </span>
                        <ExternalLink size={15} className="mt-1 shrink-0 text-slate-400" />
                      </a>
                    ))}
                  </div>
                </section>
              </article>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
