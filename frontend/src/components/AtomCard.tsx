import { Link } from 'react-router-dom'
import LinkBadge from './LinkBadge'
import SimilarityBar from './SimilarityBar'
import type { AtomMock, LinkMock } from '../lib/mock'
import { formatRelative } from '../lib/time'
import { useI18n } from '../lib/I18nProvider'

interface Props {
  atom: AtomMock
  links: LinkMock[]
  score?: number
  onDelete?: (id: string) => void | Promise<void>
}

const countLinks = (atomId: string, links: LinkMock[]) =>
  links.reduce(
    (acc, link) => {
      if (link.fromAtomId !== atomId && link.toAtomId !== atomId) return acc
      if (link.userConfirmed) acc.confirmed += 1
      else acc.suggested += 1
      return acc
    },
    { suggested: 0, confirmed: 0 },
  )

export default function AtomCard({ atom, links, score, onDelete }: Props) {
  const { lang, t } = useI18n()
  const counts = countLinks(atom.id, links)
  const deleteAtom = () => {
    if (!window.confirm(t('atom.confirmDelete'))) return
    onDelete?.(atom.id)
  }

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-300 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:shadow-none dark:hover:border-slate-700 dark:hover:bg-slate-800">
      <div className="flex items-start gap-3">
        <Link to={`/atoms/${atom.id}`} className="min-w-0 flex-1 text-left">
          <p className="line-clamp-4 whitespace-pre-wrap text-sm leading-6 text-slate-950 dark:text-slate-100">{atom.content}</p>
        </Link>
        <div className="group relative">
          <button
            type="button"
            aria-label={t('common.more')}
            className="rounded-md px-2 py-1 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-700 dark:hover:text-slate-100"
          >
            ⋯
          </button>
          <div className="absolute right-0 top-8 z-20 hidden w-28 rounded-md border border-slate-200 bg-white p-1 shadow-xl group-hover:block dark:border-slate-800 dark:bg-slate-950">
            <Link
              to={`/atoms/${atom.id}`}
              className="block w-full rounded-md px-2 py-1 text-left text-xs text-slate-600 transition hover:bg-slate-100 hover:text-slate-950 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            >
              {t('common.edit')}
            </Link>
            <button
              type="button"
              onClick={deleteAtom}
              disabled={!onDelete}
              className="block w-full rounded-md px-2 py-1 text-left text-xs text-rose-500 transition hover:bg-rose-50 hover:text-rose-700 disabled:cursor-not-allowed disabled:text-slate-400 disabled:hover:bg-transparent dark:text-rose-300 dark:hover:bg-rose-950/60 dark:hover:text-rose-100 dark:disabled:text-slate-500"
            >
              {t('common.delete')}
            </button>
          </div>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <LinkBadge suggested={counts.suggested} confirmed={counts.confirmed} />
        <span className="text-xs text-slate-500">{formatRelative(atom.createdAt, lang)}</span>
      </div>
      {score !== undefined && (
        <div className="mt-4">
          <SimilarityBar value={score} />
        </div>
      )}
    </article>
  )
}
