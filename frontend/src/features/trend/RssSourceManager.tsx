import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, Plus } from 'lucide-react'
import ConfirmDialog from '../../components/ConfirmDialog'
import { useToast } from '../../components/useToast'
import { api, ApiError } from '../../lib/api'
import { useI18n } from '../../lib/I18nProvider'
import { RssSourceRow } from './RssSourceRow'
import type { TrendRssSource, TrendRssTestResult } from './types'

type RssSourcePayload = Pick<TrendRssSource, 'name' | 'url' | 'enabled' | 'item_limit'>

export function RssSourceManager() {
  const { t } = useI18n()
  const { show } = useToast()
  const [sources, setSources] = useState<TrendRssSource[]>([])
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [itemLimit, setItemLimit] = useState(8)
  const [creating, setCreating] = useState(false)
  const [savingId, setSavingId] = useState<string | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<TrendRssSource | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    void api
      .get<TrendRssSource[]>('/api/settings/trend/rss-sources')
      .then(setSources)
      .catch((error) => {
        const message = error instanceof Error ? error.message : String(error)
        show(t('settings.readRssFailed', { message }), 'error')
      })
  }, [show, t])

  const addSource = async () => {
    setCreating(true)
    try {
      const created = await api.post<TrendRssSource>('/api/settings/trend/rss-sources', {
        name: name.trim(),
        url: url.trim(),
        enabled: true,
        item_limit: itemLimit,
      })
      setSources((current) => [...current, created])
      setName('')
      setUrl('')
      setItemLimit(8)
      show(t('settings.rssCreated'), 'success')
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(message, 'error')
    } finally {
      setCreating(false)
    }
  }

  const saveSource = async (sourceId: string, payload: RssSourcePayload) => {
    setSavingId(sourceId)
    try {
      const saved = await api.patch<TrendRssSource>(`/api/settings/trend/rss-sources/${sourceId}`, payload)
      setSources((current) => current.map((source) => (source.id === saved.id ? saved : source)))
      show(t('settings.rssSaved'), 'success')
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(message, 'error')
    } finally {
      setSavingId(null)
    }
  }

  const testSource = async (sourceId: string, sourceUrl: string) => {
    setTestingId(sourceId)
    try {
      const result = await api.post<TrendRssTestResult>(`/api/settings/trend/rss-sources/${sourceId}/test`, { url: sourceUrl })
      if (!result.ok) {
        show(t('settings.rssTestFailed', { message: result.message }), 'error')
        return
      }
      const titles = result.samples.map((sample) => sample.title).join('、')
      const message = titles
        ? `${t('settings.rssTestSuccess', { count: result.candidate_count })} ${t('settings.rssTestSamples', { titles })}`
        : t('settings.rssTestSuccess', { count: result.candidate_count })
      show(message, 'success')
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(t('settings.rssTestFailed', { message }), 'error')
    } finally {
      setTestingId(null)
    }
  }

  const deleteSource = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await api.del<void>(`/api/settings/trend/rss-sources/${deleteTarget.id}`)
      setSources((current) => current.filter((source) => source.id !== deleteTarget.id))
      show(t('settings.rssDeleted'), 'success')
      setDeleteTarget(null)
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(message, 'error')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="mt-5 border-t border-slate-200 pt-5 dark:border-slate-800">
      <button
        type="button"
        onClick={() => setCollapsed((value) => !value)}
        aria-expanded={!collapsed}
        aria-controls="custom-rss-sources"
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <span>
          <span className="text-sm font-medium text-slate-900 dark:text-slate-100">{t('settings.rssSources')}</span>
          <span className="ml-2 text-xs text-slate-500">({sources.length})</span>
        </span>
        <span className="flex items-center gap-1 text-xs text-slate-500">
          {collapsed ? t('settings.expandRssSources') : t('settings.collapseRssSources')}
          {collapsed ? <ChevronRight size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}
        </span>
      </button>

      <div id="custom-rss-sources" hidden={collapsed}>
          <p className="mt-1 text-xs leading-5 text-slate-500">{t('settings.rssSourcesDesc')}</p>

          <div className="mt-3 grid gap-3">
            {sources.map((source) => (
              <RssSourceRow
                key={source.id}
                source={source}
                saving={savingId === source.id}
                testing={testingId === source.id}
                onSave={saveSource}
                onTest={testSource}
                onDelete={setDeleteTarget}
              />
            ))}
            {sources.length === 0 && <p className="py-2 text-xs text-slate-500">{t('settings.noRssSources')}</p>}
          </div>

          <div className="mt-4 grid gap-3 rounded-md border border-dashed border-slate-300 p-3 md:grid-cols-[1fr_2fr_100px_auto] dark:border-slate-700">
            <label className="text-xs text-slate-500">
              {t('settings.rssName')}
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={120}
                placeholder={t('settings.rssNamePlaceholder')}
                className="mt-1 h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-950 outline-none placeholder:text-slate-400 focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
              />
            </label>
            <label className="text-xs text-slate-500">
              {t('settings.rssUrl')}
              <input
                type="url"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://example.com/feed.xml"
                className="mt-1 h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-950 outline-none placeholder:text-slate-400 focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
              />
            </label>
            <label className="text-xs text-slate-500">
              {t('settings.rssItemLimit')}
              <input
                type="number"
                min={1}
                max={50}
                value={itemLimit}
                onChange={(event) => setItemLimit(Number(event.target.value))}
                className="mt-1 h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-950 outline-none focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
              />
            </label>
            <button
              type="button"
              onClick={() => void addSource()}
              disabled={creating || !name.trim() || !url.trim()}
              className="mt-auto inline-flex h-9 items-center justify-center gap-1.5 rounded-md bg-emerald-500 px-3 text-sm font-medium text-white transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-slate-300 dark:disabled:bg-slate-800"
            >
              <Plus size={15} aria-hidden="true" />
              {creating ? t('common.processing') : t('settings.addRssSource')}
            </button>
          </div>
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title={t('settings.deleteRssSource')}
        confirmLabel={t('common.delete')}
        confirming={deleting}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void deleteSource()}
      >
        {t('settings.deleteRssSourceConfirm', { name: deleteTarget?.name ?? '' })}
      </ConfirmDialog>
    </div>
  )
}
