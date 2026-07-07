import { useEffect, useState } from 'react'
import AtomCard from './AtomCard'
import EmptyState from '../../components/EmptyState'
import { api } from '../../lib/api'
import { type SearchResultMock } from '../../lib/mock'
import { useSparklingStore } from '../../lib/store'
import { useI18n } from '../../lib/I18nProvider'
import { MAX_SEARCH_QUERY_CHARS } from '../../lib/limits'

// 后端 /api/search 返回的原始类型
interface SearchRaw {
  atom: {
    id: string
    content: string
    content_type: string
    status: string
    version: number
    created_at: string
    updated_at: string
  }
  score: number
}

export default function Search() {
  const { t } = useI18n()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResultMock[]>([])
  const [searching, setSearching] = useState(false)
  const links = useSparklingStore((state) => state.links)

  useEffect(() => {
    const handle = window.setTimeout(() => {
      const q = query.trim()
      if (!q) {
        setResults([])
        setSearching(false)
        return
      }
      setSearching(true)
      void api
        .get<SearchRaw[]>(`/api/search?q=${encodeURIComponent(q)}`)
        .then((raw) => {
          const next: SearchResultMock[] = raw.map((r) => ({
            atom: {
              id: r.atom.id,
              content: r.atom.content,
              status: r.atom.status as SearchResultMock['atom']['status'],
              version: r.atom.version,
              createdAt: r.atom.created_at,
              updatedAt: r.atom.updated_at,
            },
            score: r.score,
          }))
          setResults(next)
          setSearching(false)
        })
        .catch(() => setSearching(false))
    }, 300)
    return () => window.clearTimeout(handle)
  }, [query])

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-6">
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={t('search.placeholder')}
        maxLength={MAX_SEARCH_QUERY_CHARS}
        className="w-full rounded-xl border border-slate-200 bg-white px-4 py-4 text-lg text-slate-950 shadow-sm outline-none placeholder:text-slate-400 focus:border-violet-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:shadow-none dark:placeholder:text-slate-500"
      />
      <div className="mt-5">
        {!query.trim() && <EmptyState icon="⌕" title={t('search.empty')} />}
        {query.trim() && (
          <div className="mb-3 text-sm text-slate-500">
            {searching ? t('search.searching') : t('search.results', { count: results.length })}
          </div>
        )}
        {query.trim() && !searching && results.length === 0 && <EmptyState icon="∅" title={t('search.noResult.title')} description={t('search.noResult.desc')} />}
        <div className="space-y-3">
          {results.map((result) => (
            <AtomCard key={result.atom.id} atom={result.atom} links={links} score={result.score} />
          ))}
        </div>
      </div>
    </div>
  )
}
