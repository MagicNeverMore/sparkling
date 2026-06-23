import { Link } from 'react-router-dom'
import LinkBadge from './LinkBadge'
import SimilarityBar from './SimilarityBar'
import type { AtomMock, LinkMock } from '../lib/mock'
import { formatRelative } from '../lib/time'

interface Props {
  atom: AtomMock
  links: LinkMock[]
  score?: number
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

export default function AtomCard({ atom, links, score }: Props) {
  const counts = countLinks(atom.id, links)

  return (
    <article className="rounded-xl border border-slate-800 bg-slate-900 p-4 transition hover:border-slate-700 hover:bg-slate-800">
      <div className="flex items-start gap-3">
        <Link to={`/atoms/${atom.id}`} className="min-w-0 flex-1 text-left">
          <p className="line-clamp-4 whitespace-pre-wrap text-sm leading-6 text-slate-100">{atom.content}</p>
        </Link>
        <div className="group relative">
          <button
            type="button"
            aria-label="更多"
            className="rounded-md px-2 py-1 text-slate-500 transition hover:bg-slate-700 hover:text-slate-100"
          >
            ⋯
          </button>
          <div className="absolute right-0 top-8 z-20 hidden w-28 rounded-md border border-slate-800 bg-slate-950 p-1 shadow-xl group-hover:block">
            <button type="button" disabled className="block w-full cursor-not-allowed rounded-md px-2 py-1 text-left text-xs text-slate-500">
              归档
            </button>
            <button type="button" disabled className="block w-full cursor-not-allowed rounded-md px-2 py-1 text-left text-xs text-slate-500">
              删除
            </button>
          </div>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <LinkBadge suggested={counts.suggested} confirmed={counts.confirmed} />
        <span className="text-xs text-slate-500">{formatRelative(atom.createdAt)}</span>
      </div>
      {score !== undefined && (
        <div className="mt-4">
          <SimilarityBar value={score} />
        </div>
      )}
    </article>
  )
}
