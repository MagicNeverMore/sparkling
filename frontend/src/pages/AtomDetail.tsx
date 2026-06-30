import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import EmptyState from '../components/EmptyState'
import LinkSuggest from '../components/LinkSuggest'
import { useToast } from '../components/useToast'
import { ConflictError } from '../lib/mock'
import { formatDateTime } from '../lib/time'
import { useSparklingStore } from '../lib/store'

export default function AtomDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { show } = useToast()
  const atoms = useSparklingStore((state) => state.atoms)
  const links = useSparklingStore((state) => state.links)
  const loading = useSparklingStore((state) => state.loading)
  const updateAtom = useSparklingStore((state) => state.updateAtom)
  const deleteAtom = useSparklingStore((state) => state.deleteAtom)
  const confirmLink = useSparklingStore((state) => state.confirmLink)
  const ignoreLink = useSparklingStore((state) => state.ignoreLink)
  const loadInitial = useSparklingStore((state) => state.loadInitial)
  const atom = atoms.find((item) => item.id === id)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [pendingLinkId, setPendingLinkId] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    setDraft(atom?.content ?? '')
  }, [atom?.content])

  useEffect(() => {
    if (!editing) return
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${textarea.scrollHeight}px`
    textarea.focus()
  }, [draft, editing])

  const related = useMemo(() => {
    const confirmed: Array<{ linkId: string; atomId: string }> = []
    const suggested: Array<{ linkId: string; atomId: string }> = []
    links.forEach((link) => {
      if (!id || (link.fromAtomId !== id && link.toAtomId !== id)) return
      const otherId = link.fromAtomId === id ? link.toAtomId : link.fromAtomId
      if (link.userConfirmed) confirmed.push({ linkId: link.id, atomId: otherId })
      else suggested.push({ linkId: link.id, atomId: otherId })
    })
    return { confirmed, suggested }
  }, [id, links])

  const save = async () => {
    if (!atom) return
    const next = draft.trim()
    if (!next) {
      show('内容不能为空', 'warning')
      return
    }
    if (next === atom.content) {
      setEditing(false)
      return
    }
    try {
      await updateAtom(atom.id, { content: next })
      setEditing(false)
      show('已保存', 'success')
    } catch (error) {
      if (error instanceof ConflictError) {
        show('版本冲突，已重新加载最新内容', 'warning')
        await loadInitial()
        return
      }
      show('保存失败', 'error')
    }
  }

  const remove = async () => {
    if (!atom) return
    if (!window.confirm('删除后会保留 30 天，之后自动清理。确认删除？')) return
    try {
      await deleteAtom(atom.id)
      show('已删除', 'info')
      navigate('/inbox', { replace: true })
    } catch {
      show('删除失败', 'error')
    }
  }

  if (loading) {
    return <div className="mx-auto max-w-5xl px-4 py-6 text-slate-500">加载中…</div>
  }

  if (!atom) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-6">
        <EmptyState icon="∅" title="没有找到这个想法" description="它可能已经被删除，或 mock 数据已刷新。" />
      </div>
    )
  }

  return (
    <div className="mx-auto grid max-w-6xl gap-6 px-4 py-6 md:px-6 lg:grid-cols-[2fr_1fr]">
      <section className="min-w-0">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="mb-4 rounded-md border border-slate-800 px-3 py-2 text-sm text-slate-400 transition hover:bg-slate-900 hover:text-slate-100"
        >
          ← 返回
        </button>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="mb-4 flex flex-wrap justify-end gap-2">
            {!editing && (
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-200 transition hover:bg-slate-800"
              >
                变更
              </button>
            )}
            {editing && (
              <button
                type="button"
                onClick={() => void save()}
                className="rounded-md bg-violet-500 px-3 py-2 text-sm font-medium text-white transition hover:bg-violet-400"
              >
                保存
              </button>
            )}
            <button
              type="button"
              onClick={() => void remove()}
              className="rounded-md border border-rose-900/70 px-3 py-2 text-sm text-rose-300 transition hover:bg-rose-950/60 hover:text-rose-100"
            >
              删除
            </button>
          </div>
          {editing ? (
            <textarea
              ref={textareaRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              className="min-h-48 w-full resize-none bg-transparent text-2xl leading-10 text-slate-100 outline-none"
            />
          ) : (
            <button type="button" onClick={() => setEditing(true)} className="block w-full text-left">
              <p className="whitespace-pre-wrap text-2xl leading-10 text-slate-100">{atom.content}</p>
            </button>
          )}
          <div className="mt-6 flex flex-wrap gap-3 border-t border-slate-800 pt-4 text-xs text-slate-500">
            <span>创建 {formatDateTime(atom.createdAt)}</span>
            <span>状态 {atom.status}</span>
            <span>version {atom.version}</span>
          </div>
        </div>
      </section>

      <aside className="space-y-6">
        <section>
          <h2 className="mb-3 text-sm font-medium text-slate-100">已确认 ({related.confirmed.length})</h2>
          <div className="space-y-2">
            {related.confirmed.map((item) => {
              const target = atoms.find((candidate) => candidate.id === item.atomId)
              if (!target) return null
              const isProcessing = pendingLinkId === item.linkId
              return (
                <div
                  key={item.linkId}
                  className="flex items-start gap-2 rounded-xl border border-slate-800 bg-slate-900 p-3 text-sm leading-6 text-slate-300 transition hover:border-slate-700 hover:bg-slate-800"
                >
                  <Link to={`/atoms/${target.id}`} className="flex min-w-0 flex-1 gap-2">
                    <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-emerald-400" />
                    <span className="line-clamp-2">{target.content}</span>
                  </Link>
                  <button
                    type="button"
                    disabled={isProcessing}
                    title="取消关联"
                    onClick={async () => {
                      setPendingLinkId(item.linkId)
                      try {
                        await ignoreLink(item.linkId)
                      } finally {
                        setPendingLinkId(null)
                      }
                    }}
                    className="rounded p-1 text-slate-500 transition hover:bg-rose-400/10 hover:text-rose-400 disabled:opacity-40"
                  >
                    ✕
                  </button>
                </div>
              )
            })}
            {related.confirmed.length === 0 && <div className="text-sm text-slate-500">还没有已确认关联</div>}
          </div>
        </section>

        <section>
          <h2 className="mb-3 text-sm font-medium text-slate-100">AI 建议 ({related.suggested.length})</h2>
          <div className="space-y-3">
            {related.suggested.map((item) => {
              const link = links.find((candidate) => candidate.id === item.linkId)
              const target = atoms.find((candidate) => candidate.id === item.atomId)
              if (!link || !target) return null
              return (
                <LinkSuggest
                  key={item.linkId}
                  link={link}
                  atom={target}
                  onConfirm={(linkId) => void confirmLink(linkId)}
                  onIgnore={(linkId) => void ignoreLink(linkId)}
                />
              )
            })}
            {related.suggested.length === 0 && <div className="text-sm text-slate-500">没有待确认建议</div>}
          </div>
        </section>
      </aside>
    </div>
  )
}
