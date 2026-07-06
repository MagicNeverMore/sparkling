import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import EmptyState from '../components/EmptyState'
import LinkSuggest from '../components/LinkSuggest'
import { useToast } from '../components/useToast'
import { ConflictError } from '../lib/mock'
import { formatDateTime } from '../lib/time'
import { useSparklingStore } from '../lib/store'
import { useI18n } from '../lib/I18nProvider'

export default function AtomDetail() {
  const { lang, t } = useI18n()
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
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
      show(t('atom.contentRequired'), 'warning')
      return
    }
    if (next === atom.content) {
      setEditing(false)
      return
    }
    try {
      await updateAtom(atom.id, { content: next })
      setEditing(false)
      show(t('common.saved'), 'success')
    } catch (error) {
      if (error instanceof ConflictError) {
        show(t('atom.conflict'), 'warning')
        await loadInitial()
        return
      }
      show(t('common.saveFailed'), 'error')
    }
  }

  const remove = async () => {
    if (!atom) return
    if (!window.confirm(t('atom.confirmDelete'))) return
    try {
      await deleteAtom(atom.id)
      show(t('common.deleted'), 'info')
      navigate('/inbox', { replace: true })
    } catch {
      show(t('common.deleteFailed'), 'error')
    }
  }

  if (loading) {
    return <div className="mx-auto max-w-5xl px-4 py-6 text-slate-500">{t('common.loading')}</div>
  }

  if (!atom) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-6">
        <EmptyState icon="∅" title={t('atom.notFound.title')} description={t('atom.notFound.desc')} />
      </div>
    )
  }

  return (
    <div className="mx-auto grid max-w-6xl gap-6 px-4 py-6 md:px-6 lg:grid-cols-[2fr_1fr]">
      <section className="min-w-0">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="mb-4 rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
        >
          {t('common.back')}
        </button>
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
          <div className="mb-4 flex flex-wrap justify-end gap-2">
            {!editing && (
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                {t('common.edit')}
              </button>
            )}
            {editing && (
              <button
                type="button"
                onClick={() => void save()}
                className="rounded-md bg-violet-500 px-3 py-2 text-sm font-medium text-white transition hover:bg-violet-400"
              >
                {t('common.save')}
              </button>
            )}
            <button
              type="button"
              onClick={() => void remove()}
              className="rounded-md border border-rose-200 px-3 py-2 text-sm text-rose-600 transition hover:bg-rose-50 hover:text-rose-700 dark:border-rose-900/70 dark:text-rose-300 dark:hover:bg-rose-950/60 dark:hover:text-rose-100"
            >
              {t('common.delete')}
            </button>
          </div>
          {editing ? (
            <textarea
              ref={textareaRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              className="min-h-48 w-full resize-none bg-transparent text-2xl leading-10 text-slate-950 outline-none dark:text-slate-100"
            />
          ) : (
            <button type="button" onClick={() => setEditing(true)} className="block w-full text-left">
              <p className="whitespace-pre-wrap text-2xl leading-10 text-slate-950 dark:text-slate-100">{atom.content}</p>
            </button>
          )}
          <div className="mt-6 flex flex-wrap gap-3 border-t border-slate-200 pt-4 text-xs text-slate-500 dark:border-slate-800">
            <span>{t('atom.created', { value: formatDateTime(atom.createdAt, lang) })}</span>
            <span>{t('atom.status', { value: atom.status })}</span>
            <span>version {atom.version}</span>
          </div>
        </div>
      </section>

      <aside className="space-y-6">
        <section>
          <h2 className="mb-3 text-sm font-medium text-slate-950 dark:text-slate-100">{t('link.confirmedTitle')} ({related.confirmed.length})</h2>
          <div className="space-y-2">
            {related.confirmed.map((item) => {
              const target = atoms.find((candidate) => candidate.id === item.atomId)
              if (!target) return null
              const isProcessing = pendingLinkId === item.linkId
              return (
                <div
                  key={item.linkId}
                  className="flex items-start gap-2 rounded-xl border border-slate-200 bg-white p-3 text-sm leading-6 text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:hover:border-slate-700 dark:hover:bg-slate-800"
                >
                  <Link to={`/atoms/${target.id}`} className="flex min-w-0 flex-1 gap-2">
                    <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-emerald-400" />
                    <span className="line-clamp-2">{target.content}</span>
                  </Link>
                  <button
                    type="button"
                    disabled={isProcessing}
                    title={t('link.cancel')}
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
            {related.confirmed.length === 0 && <div className="text-sm text-slate-500">{t('link.noConfirmed')}</div>}
          </div>
        </section>

        <section>
          <h2 className="mb-3 text-sm font-medium text-slate-950 dark:text-slate-100">{t('link.aiSuggestedTitle')} ({related.suggested.length})</h2>
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
            {related.suggested.length === 0 && <div className="text-sm text-slate-500">{t('link.noSuggested')}</div>}
          </div>
        </section>
      </aside>
    </div>
  )
}
