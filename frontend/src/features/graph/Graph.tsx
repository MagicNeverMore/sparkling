import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import GraphCanvas from './GraphCanvas'
import { useSparklingStore } from '../../lib/store'
import { formatDateTime } from '../../lib/time'
import { useI18n } from '../../lib/I18nProvider'

export default function Graph() {
  const { lang, t } = useI18n()
  const atoms = useSparklingStore((state) => state.atoms)
  const links = useSparklingStore((state) => state.links)
  const loading = useSparklingStore((state) => state.loading)
  const confirmLink = useSparklingStore((state) => state.confirmLink)
  const ignoreLink = useSparklingStore((state) => state.ignoreLink)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [pendingId, setPendingId] = useState<string | null>(null)

  const selectedAtom = atoms.find((a) => a.id === selectedId) ?? null

  const related = useMemo(() => {
    if (!selectedId) return { confirmed: [], suggested: [] }
    const confirmed: Array<{ linkId: string; atomId: string; confidence: number }> = []
    const suggested: Array<{ linkId: string; atomId: string; confidence: number }> = []
    links.forEach((link) => {
      if (link.fromAtomId !== selectedId && link.toAtomId !== selectedId) return
      const otherId = link.fromAtomId === selectedId ? link.toAtomId : link.fromAtomId
      if (link.userConfirmed) {
        confirmed.push({ linkId: link.id, atomId: otherId, confidence: link.confidence })
      } else {
        suggested.push({ linkId: link.id, atomId: otherId, confidence: link.confidence })
      }
    })
    return { confirmed, suggested }
  }, [selectedId, links])

  if (loading) {
    return <div className="p-6 text-slate-500">{t('graph.loading')}</div>
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
        <div className="absolute left-4 top-16 z-30 max-h-[calc(100%-5rem)] w-72 overflow-y-auto rounded-xl border border-slate-200 bg-white/95 shadow-2xl backdrop-blur dark:border-slate-800 dark:bg-slate-950/95">
          <div className="p-4">
            {/* 头部 */}
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs uppercase tracking-wide text-slate-500">{t('graph.nodeDetail')}</span>
              <button
                type="button"
                onClick={() => setSelectedId(null)}
                className="rounded p-0.5 text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-300"
              >
                ✕
              </button>
            </div>

            {/* 内容 */}
            <p className="mb-3 whitespace-pre-wrap text-sm leading-6 text-slate-950 dark:text-slate-100">
              {selectedAtom.content}
            </p>

            {/* 元信息 */}
            <div className="mb-3 space-y-1 text-xs text-slate-500">
              <div>{formatDateTime(selectedAtom.createdAt, lang)}</div>
              <div>{t('link.count', { count: related.confirmed.length + related.suggested.length })}</div>
            </div>

            <Link
              to={`/atoms/${selectedAtom.id}`}
              className="text-xs text-violet-300 transition hover:text-violet-100"
            >
              {t('graph.openDetail')}
            </Link>

            {/* 已确认关联 */}
            {related.confirmed.length > 0 && (
              <div className="mt-4">
                <div className="mb-2 text-xs uppercase tracking-wide text-slate-500">
                  {t('link.confirmedTitle')}
                </div>
                <div className="space-y-1.5">
                  {related.confirmed.map((item) => {
                    const target = atoms.find((a) => a.id === item.atomId)
                    if (!target) return null
                    const isProcessing = pendingId === item.linkId
                    return (
                      <div
                        key={item.linkId}
                        className="flex items-start gap-1.5 rounded-lg border border-slate-200 p-2 text-xs transition hover:border-slate-300 dark:border-slate-800 dark:hover:border-slate-700"
                      >
                        <button
                          type="button"
                          onClick={() => setSelectedId(target.id)}
                          className="flex min-w-0 flex-1 gap-2 text-left text-slate-500 transition hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
                        >
                          <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                          <span className="line-clamp-2 flex-1">{target.content}</span>
                          <span className="shrink-0 text-emerald-400/70">{item.confidence.toFixed(2)}</span>
                        </button>
                        <button
                          type="button"
                          disabled={isProcessing}
                          title={t('link.cancel')}
                          onClick={async () => {
                            setPendingId(item.linkId)
                            try {
                              await ignoreLink(item.linkId)
                            } finally {
                              setPendingId(null)
                            }
                          }}
                          className="rounded p-1 text-slate-500 transition hover:bg-rose-400/10 hover:text-rose-400 disabled:opacity-40"
                        >
                          ✕
                        </button>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* AI 建议关联 */}
            {related.suggested.length > 0 && (
              <div className="mt-4">
                <div className="mb-2 text-xs uppercase tracking-wide text-slate-500">
                  {t('link.aiSuggestedTitle')}
                </div>
                <div className="space-y-1.5">
                  {related.suggested.map((item) => {
                    const target = atoms.find((a) => a.id === item.atomId)
                    if (!target) return null
                    const isProcessing = pendingId === item.linkId
                    return (
                      <div
                        key={item.linkId}
                        className="flex items-start gap-1.5 rounded-lg border border-slate-200 p-2 text-xs transition hover:border-slate-300 dark:border-slate-800 dark:hover:border-slate-700"
                      >
                        {/* 点击文本区域跳转节点 */}
                        <button
                          type="button"
                          onClick={() => setSelectedId(target.id)}
                          className="flex min-w-0 flex-1 items-start gap-2 text-left text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
                        >
                          <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-violet-400" />
                          <span className="line-clamp-2 flex-1">{target.content}</span>
                          <span className="shrink-0 text-violet-400/70">
                            {item.confidence.toFixed(2)}
                          </span>
                        </button>
                        {/* 接受 / 拒绝 */}
                        <div className="flex shrink-0 gap-1">
                          <button
                            type="button"
                            disabled={isProcessing}
                            title={t('link.accept')}
                            onClick={async () => {
                              setPendingId(item.linkId)
                              try {
                                await confirmLink(item.linkId)
                              } finally {
                                setPendingId(null)
                              }
                            }}
                            className="rounded p-1 text-slate-500 transition hover:bg-emerald-400/10 hover:text-emerald-400 disabled:opacity-40"
                          >
                            ✓
                          </button>
                          <button
                            type="button"
                            disabled={isProcessing}
                            title={t('link.ignore')}
                            onClick={async () => {
                              setPendingId(item.linkId)
                              try {
                                await ignoreLink(item.linkId)
                              } finally {
                                setPendingId(null)
                              }
                            }}
                            className="rounded p-1 text-slate-500 transition hover:bg-rose-400/10 hover:text-rose-400 disabled:opacity-40"
                          >
                            ✕
                          </button>
                        </div>
                      </div>
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
