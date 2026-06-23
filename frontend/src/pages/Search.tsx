import { useEffect, useState } from 'react'
import AtomCard from '../components/AtomCard'
import EmptyState from '../components/EmptyState'
import { mockApi, type SearchResultMock } from '../lib/mock'
import { useSparklingStore } from '../lib/store'

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
      // TODO(real-api): GET /api/search?q=... and map backend scores into SearchResultMock.
      void mockApi.search(q).then((next) => {
        setResults(next)
        setSearching(false)
      })
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
