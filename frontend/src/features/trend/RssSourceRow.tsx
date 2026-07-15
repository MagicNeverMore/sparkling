import { useState } from 'react'
import { TestTube2, Trash2 } from 'lucide-react'
import { useI18n } from '../../lib/I18nProvider'
import type { TrendRssSource } from './types'

interface RssSourceRowProps {
  source: TrendRssSource
  saving: boolean
  testing: boolean
  onSave: (sourceId: string, payload: Pick<TrendRssSource, 'name' | 'url' | 'enabled' | 'item_limit'>) => Promise<void>
  onTest: (sourceId: string, url: string) => Promise<void>
  onDelete: (source: TrendRssSource) => void
}

export function RssSourceRow({ source, saving, testing, onSave, onTest, onDelete }: RssSourceRowProps) {
  const { t } = useI18n()
  const [name, setName] = useState(source.name)
  const [url, setUrl] = useState(source.url)
  const [enabled, setEnabled] = useState(source.enabled)
  const [itemLimit, setItemLimit] = useState(source.item_limit)

  const save = () => {
    void onSave(source.id, {
      name: name.trim(),
      url: url.trim(),
      enabled,
      item_limit: itemLimit,
    })
  }

  return (
    <div className="rounded-md border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-950">
      <div className="grid gap-3 md:grid-cols-[1fr_2fr_100px_auto]">
        <label className="text-xs text-slate-500">
          {t('settings.rssName')}
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={120}
            className="mt-1 h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-950 outline-none focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
          />
        </label>
        <label className="text-xs text-slate-500">
          {t('settings.rssUrl')}
          <input
            type="url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            className="mt-1 h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-950 outline-none focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
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
        <div className="flex items-end gap-2">
          <button
            type="button"
            onClick={() => void onTest(source.id, url.trim())}
            disabled={saving || testing || !url.trim()}
            className="inline-flex h-9 items-center gap-1.5 rounded-md border border-sky-300 px-3 text-sm text-sky-700 transition hover:bg-sky-50 disabled:cursor-not-allowed disabled:border-slate-300 disabled:text-slate-400 dark:border-sky-900 dark:text-sky-300 dark:hover:bg-sky-950/30 dark:disabled:border-slate-700"
          >
            <TestTube2 size={15} aria-hidden="true" />
            {testing ? t('common.processing') : t('settings.testRssSource')}
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving || testing || !name.trim() || !url.trim()}
            className="h-9 rounded-md border border-slate-300 px-3 text-sm text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-400 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            {saving ? t('common.processing') : t('common.save')}
          </button>
          <button
            type="button"
            onClick={() => onDelete(source)}
            disabled={saving || testing}
            className="flex h-9 w-9 items-center justify-center rounded-md text-slate-500 transition hover:bg-rose-50 hover:text-rose-500 disabled:cursor-not-allowed dark:hover:bg-rose-950/30"
            aria-label={t('settings.deleteRssSource')}
            title={t('settings.deleteRssSource')}
          >
            <Trash2 size={16} aria-hidden="true" />
          </button>
        </div>
      </div>
      <label className="mt-3 flex items-center gap-2 text-xs text-slate-500">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(event) => setEnabled(event.target.checked)}
          className="h-4 w-4 rounded border-slate-300 accent-violet-400"
        />
        {t('settings.rssEnabled')}
      </label>
    </div>
  )
}
