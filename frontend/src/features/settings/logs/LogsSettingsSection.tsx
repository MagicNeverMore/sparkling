import { RefreshCw, Search } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useToast } from '../../../components/useToast'
import { api } from '../../../lib/api'
import { useI18n } from '../../../lib/I18nProvider'
import type { LogEntry, LogPage } from './types'

const entryColor = (entry: LogEntry) => {
  if (entry.text.includes('| ERROR') || entry.text.includes('| CRITICAL')) return 'text-rose-600 dark:text-rose-300'
  if (entry.text.includes('| WARNING')) return 'text-amber-600 dark:text-amber-300'
  if (entry.text.includes('| DEBUG')) return 'text-slate-400 dark:text-slate-500'
  return 'text-slate-700 dark:text-slate-300'
}

export default function LogsSettingsSection() {
  const { t } = useI18n()
  const { show } = useToast()
  const [page, setPage] = useState<LogPage | null>(null)
  const [file, setFile] = useState('')
  const [level, setLevel] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)

  const loadLogs = useCallback(async (before?: number, prepend = false) => {
    setLoading(true)
    const params = new URLSearchParams({ limit: '200' })
    if (file) params.set('file', file)
    if (level) params.set('level', level)
    if (query.trim()) params.set('query', query.trim())
    if (before) params.set('before', String(before))
    try {
      const next = await api.get<LogPage>(`/api/settings/logs?${params.toString()}`)
      setPage((current) => prepend && current
        ? { ...next, items: [...next.items, ...current.items] }
        : next)
      if (!file && next.file) setFile(next.file)
    } catch (error) {
      show(t('settings.logsLoadFailed', { message: error instanceof Error ? error.message : String(error) }), 'error')
    } finally {
      setLoading(false)
    }
  }, [file, level, query, show, t])

  useEffect(() => {
    const timer = window.setTimeout(() => void loadLogs(), 250)
    return () => window.clearTimeout(timer)
  }, [loadLogs])

  const selectedFile = page?.files.find((item) => item.name === page.file)

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-950 dark:text-slate-100">{t('settings.logs')}</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{t('settings.logsDesc')}</p>
        </div>
        <button type="button" onClick={() => void loadLogs()} disabled={loading} className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />{t('settings.refreshLogs')}
        </button>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-[minmax(0,1fr)_160px_minmax(0,1fr)]">
        <label className="text-sm text-slate-500 dark:text-slate-400">
          {t('settings.logFile')}
          <select value={file} onChange={(event) => setFile(event.target.value)} className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100">
            {page?.files.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
          </select>
        </label>
        <label className="text-sm text-slate-500 dark:text-slate-400">
          {t('settings.logLevel')}
          <select value={level} onChange={(event) => setLevel(event.target.value)} className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100">
            <option value="">{t('settings.allLevels')}</option>
            {['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'].map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label className="text-sm text-slate-500 dark:text-slate-400">
          {t('settings.searchLogs')}
          <span className="relative mt-2 block">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t('settings.searchLogsPlaceholder')} className="w-full rounded-md border border-slate-200 bg-white py-2 pl-9 pr-3 text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100" />
          </span>
        </label>
      </div>

      <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
        <span>{t('settings.logMatches', { count: page?.total_matches ?? 0 })}</span>
        {selectedFile && <span>{selectedFile.name} · {(selectedFile.size_bytes / 1024).toFixed(1)} KB</span>}
      </div>

      <div className="mt-3 max-h-[65vh] overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs leading-5 dark:border-slate-800 dark:bg-slate-950">
        {page?.items.length ? page.items.map((entry) => (
          <div key={`${entry.line_number}-${entry.text}`} className={`flex min-w-max gap-3 ${entryColor(entry)}`}>
            <span className="w-14 shrink-0 select-none text-right text-slate-400">{entry.line_number}</span>
            <span className="whitespace-pre">{entry.text}</span>
          </div>
        )) : <div className="py-8 text-center text-slate-500">{loading ? t('common.loading') : t('settings.noLogs')}</div>}
      </div>

      {page?.next_before && (
        <div className="mt-4 flex justify-center">
          <button type="button" onClick={() => void loadLogs(page.next_before ?? undefined, true)} disabled={loading} className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
            {t('settings.loadOlderLogs')}
          </button>
        </div>
      )}
    </section>
  )
}
