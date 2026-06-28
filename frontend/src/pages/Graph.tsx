import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import GraphCanvas from '../components/GraphCanvas'
import { useSparklingStore } from '../lib/store'
import { formatDateTime } from '../lib/time'

export default function Graph() {
  const atoms = useSparklingStore((state) => state.atoms)
  const links = useSparklingStore((state) => state.links)
  const loading = useSparklingStore((state) => state.loading)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const selectedAtom = atoms.find((a) => a.id === selectedId) ?? null

  const related = useMemo(() => {
    if (!selectedId) return { confirmed: [], suggested: [] }
    const confirmed: Array<{ linkId: string; atomId: string }> = []
    const suggested: Array<{ linkId: string; atomId: string; confidence: number }> = []
    links.forEach((link) => {
      if (link.fromAtomId !== selectedId && link.toAtomId !== selectedId) return
      const otherId = link.fromAtomId === selectedId ? link.toAtomId : link.fromAtomId
      if (link.userConfirmed) {
        confirmed.push({ linkId: link.id, atomId: otherId })
      } else {
        suggested.push({ linkId: link.id, atomId: otherId, confidence: link.confidence })
      }
    })
    return { confirmed, suggested }
  }, [selectedId, links])

  if (loading) {
    return <div className="p-6 text-slate-500">加载图谱…</div>
  }

  return (
    <div className="relative h-full overflow-hidden">
      {/* 图谱画布，全屏占满 */}
      <GraphCanvas
        atoms={atoms}
        links={links}
        selectedId={selectedId}
        onNodeSelect={setSelectedId}
      />

      {/* 节点详情浮层 — 仅点击节点后出现，位于左侧工具栏下方 */}
      {selectedAtom && (
        <div className="absolute left-4 top-16 z-30 w-72 max-h-[calc(100%-5rem)] overflow-y-auto rounded-xl border border-slate-800 bg-slate-950/95 shadow-2xl backdrop-blur">
          <div className="p-4">
            {/* 头部 */}
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs uppercase tracking-wide text-slate-500">节点详情</span>
              <button
                type="button"
                onClick={() => setSelectedId(null)}
                className="rounded p-0.5 text-slate-500 transition hover:bg-slate-800 hover:text-slate-300"
              >
                ✕
              </button>
            </div>

            {/* 内容 */}
            <p className="mb-3 whitespace-pre-wrap text-sm leading-6 text-slate-100">
              {selectedAtom.content}
            </p>

            {/* 元信息 */}
            <div className="mb-3 space-y-1 text-xs text-slate-500">
              <div>{formatDateTime(selectedAtom.createdAt)}</div>
              <div>关联数 {related.confirmed.length + related.suggested.length}</div>
            </div>

            <Link
              to={`/atoms/${selectedAtom.id}`}
              className="text-xs text-violet-300 transition hover:text-violet-100"
            >
              打开详情 →
            </Link>

            {/* 已确认关联 */}
            {related.confirmed.length > 0 && (
              <div className="mt-4">
                <div className="mb-2 text-xs uppercase tracking-wide text-slate-500">
                  已确认关联
                </div>
                <div className="space-y-1.5">
                  {related.confirmed.map((item) => {
                    const target = atoms.find((a) => a.id === item.atomId)
                    if (!target) return null
                    return (
                      <button
                        key={item.linkId}
                        type="button"
                        onClick={() => setSelectedId(target.id)}
                        className="flex w-full gap-2 rounded-lg border border-slate-800 p-2 text-left text-xs text-slate-400 transition hover:border-slate-700 hover:text-slate-200"
                      >
                        <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                        <span className="line-clamp-2">{target.content}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {/* AI 建议关联 */}
            {related.suggested.length > 0 && (
              <div className="mt-4">
                <div className="mb-2 text-xs uppercase tracking-wide text-slate-500">
                  AI 建议关联
                </div>
                <div className="space-y-1.5">
                  {related.suggested.map((item) => {
                    const target = atoms.find((a) => a.id === item.atomId)
                    if (!target) return null
                    return (
                      <button
                        key={item.linkId}
                        type="button"
                        onClick={() => setSelectedId(target.id)}
                        className="flex w-full gap-2 rounded-lg border border-slate-800 p-2 text-left text-xs text-slate-400 transition hover:border-slate-700 hover:text-slate-200"
                      >
                        <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-violet-400" />
                        <span className="line-clamp-2 flex-1">{target.content}</span>
                        <span className="shrink-0 text-violet-400/70">
                          {item.confidence.toFixed(2)}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
