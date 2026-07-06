import { Link } from 'react-router-dom'
import SimilarityBar from './SimilarityBar'
import type { AtomMock, LinkMock } from '../../lib/mock'
import { useI18n } from '../../lib/I18nProvider'

interface Props {
  link: LinkMock
  atom: AtomMock
  onConfirm: (id: string) => void
  onIgnore: (id: string) => void
}

export default function LinkSuggest({ link, atom, onConfirm, onIgnore }: Props) {
  const { t } = useI18n()
  return (
    <div className="animate-suggestion-in rounded-xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
      <div className="flex items-start gap-2">
        <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-violet-400" />
        <Link to={`/atoms/${atom.id}`} className="line-clamp-2 flex-1 text-sm leading-6 text-slate-950 hover:text-violet-500 dark:text-slate-100 dark:hover:text-violet-400">
          {atom.content}
        </Link>
      </div>
      <div className="mt-3">
        <SimilarityBar value={link.confidence} compact />
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button
          type="button"
          onClick={() => onIgnore(link.id)}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-600 transition hover:bg-slate-100 hover:text-slate-950 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
        >
          {t('link.ignore')}
        </button>
        <button
          type="button"
          onClick={() => onConfirm(link.id)}
          className="rounded-md bg-violet-400 px-3 py-1.5 text-xs font-medium text-slate-950 transition hover:bg-violet-300"
        >
          {t('common.confirm')}
        </button>
      </div>
    </div>
  )
}
