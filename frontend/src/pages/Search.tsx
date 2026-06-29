import { useEffect, useState } from 'react'
import AtomCard from '../components/AtomCard'
import EmptyState from '../components/EmptyState'
import { api } from '../lib/api'
import { type SearchResultMock } from '../lib/mock'
import { useSparklingStore } from '../lib/store'

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
        placeholder='🔍 语义搜索：试试 "晨跑 心率"…'
        className="w-full rounded-xl border border-slate-800 bg-slate-900 px-4 py-4 text-lg text-slate-100 outline-none placeholder:text-slate-500 focus:border-violet-400"
      />
      <div className="mt-5">
        {!query.trim() && <EmptyState icon="⌕" title="按相似度返回结果。试试关键词组合。" />}
        {query.trim() && (
          <div className="mb-3 text-sm text-slate-500">
            {searching ? '搜索中…' : `找到 ${results.length} 条结果`}
          </div>
        )}
        {query.trim() && !searching && results.length === 0 && <EmptyState icon="∅" title="没有匹配结果" description="换一个关键词组合再试试。" />}
        <div className="space-y-3">
          {results.map((result) => (
            <AtomCard key={result.atom.id} atom={result.atom} links={links} score={result.score} />
          ))}
        </div>
      </div>
    </div>
  )
}
