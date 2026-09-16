import { useEffect, useRef, useState } from 'react'
import type { Task, TaskCreatePayload } from '../../lib/taskStore'
import { useI18n } from '../../lib/I18nProvider'
import { api } from '../../lib/api'
import { completionDate, localDate } from './taskTimeline'
import { useToday } from './useToday'

interface Props {
  open: boolean
  initial?: Task | null
  onClose: () => void
  onSave: (payload: TaskCreatePayload) => Promise<void>
}

const CATEGORIES = ['自媒体', 'App 开发', '其他']

interface AvailableTopic {
  id: string
  title: string
}

// 内层组件通过 key 重置，避免 useEffect + setState 的 lint 问题
function TaskModalInner({ initial, onClose, onSave }: Omit<Props, 'open'>) {
  const { t, lang } = useI18n()
  const zh = lang === 'zh'
  const today = useToday()
  const dialogRef = useRef<HTMLDivElement>(null)
  const [title, setTitle] = useState(initial?.title ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [category, setCategory] = useState(initial?.category ?? '')
  const [startDate, setStartDate] = useState(initial?.startDate ?? '')
  const [dueDate, setDueDate] = useState(initial?.dueDate ?? '')
  const [topicId, setTopicId] = useState('')
  const [topics, setTopics] = useState<AvailableTopic[]>([])
  const [saving, setSaving] = useState(false)
  const [completed, setCompleted] = useState(initial?.completed ?? false)
  const [actualDate, setActualDate] = useState(initial ? completionDate(initial) ?? '' : '')
  const [error, setError] = useState('')

  useEffect(() => {
    if (initial || category !== '自媒体') return
    void api.get<AvailableTopic[]>('/api/social-media/topic/available').then(setTopics).catch(() => setTopics([]))
  }, [category, initial])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return
    setError('')
    dialogRef.current?.focus()
    setSaving(true)
    try {
      await onSave({
        title: title.trim(),
        description: description.trim() || undefined,
        category: category.trim() || undefined,
        startDate: startDate || null,
        dueDate: dueDate || null,
        completed,
        actualCompletionDate: completed ? actualDate : null,
        topicId: topicId || undefined,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      })
      onClose()
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-sm dark:bg-slate-950/70">
      <div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="task-modal-title" onKeyDown={event => {
        if (event.key === 'Escape' && !saving) onClose()
        if (event.key !== 'Tab') return
        const controls = dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled)')
        if (!controls?.length) { event.preventDefault(); return }
        const first = controls[0], last = controls[controls.length - 1]
        if (document.activeElement === dialogRef.current) { event.preventDefault(); (event.shiftKey ? last : first).focus() }
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
      }} className="max-h-[90dvh] w-full max-w-md overflow-y-auto rounded-xl border border-slate-200 bg-white p-5 shadow-2xl dark:border-slate-800 dark:bg-slate-900">
        <h2 id="task-modal-title" className="mb-4 text-base font-semibold text-slate-950 dark:text-slate-100">
          {initial ? t('tasks.modal.edit') : t('tasks.modal.new')}
        </h2>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <fieldset disabled={saving} className="flex min-w-0 flex-col gap-3">
          {error && <p role="alert" className="rounded-lg bg-rose-50 p-3 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-200">{error}</p>}
          {/* 标题 */}
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">{t('tasks.titleLabel')}</label>
            <input
              autoFocus
              required
              aria-label={t('tasks.titleLabel')}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('tasks.titlePlaceholder')}
              className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 placeholder-slate-400 outline-none focus:border-violet-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder-slate-500"
            />
          </div>

          {/* 描述 */}
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">{t('tasks.description')}</label>
            <textarea
              aria-label={t('tasks.description')}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder={t('tasks.optional')}
              className="w-full resize-none rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 placeholder-slate-400 outline-none focus:border-violet-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder-slate-500"
            />
          </div>

          {/* 分类 */}
          <div>
            <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">{t('tasks.category')}</label>
            <div className="flex flex-wrap gap-2">
              {CATEGORIES.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setCategory(category === c ? '' : c)}
                  className={`rounded-md border px-3 py-1 text-xs transition ${
                    category === c
                      ? 'border-violet-400 bg-violet-400/10 text-violet-400'
                      : 'border-slate-300 text-slate-500 hover:border-slate-400 hover:text-slate-800 dark:border-slate-700 dark:text-slate-400 dark:hover:border-slate-600 dark:hover:text-slate-300'
                  }`}
                >
                  {c}
                </button>
              ))}
              {!CATEGORIES.includes(category) && category && (
                <span className="rounded-md border border-violet-400 bg-violet-400/10 px-3 py-1 text-xs text-violet-400">
                  {category}
                </span>
              )}
            </div>
            <input
              aria-label={t('tasks.customCategory')}
              value={CATEGORIES.includes(category) ? '' : category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder={t('tasks.customCategory')}
              className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-950 placeholder-slate-400 outline-none focus:border-violet-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder-slate-500"
            />
          </div>

          {!initial && category === '自媒体' && (
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">关联选题（未开始）</label>
              <select aria-label={zh ? '关联选题' : 'Linked topic'} value={topicId} onChange={(e) => setTopicId(e.target.value)} className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-violet-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100">
                <option value="">不关联选题</option>
                {topics.map((topic) => <option key={topic.id} value={topic.id}>{topic.title}</option>)}
              </select>
              {topicId && <p className="mt-1 text-xs text-slate-500">创建后该选题会自动变为「工作中」。</p>}
            </div>
          )}

          {/* 日期 */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">{t('tasks.startDate')}</label>
              <input
                type="date"
                aria-label={t('tasks.startDate')}
                max={completed && actualDate ? actualDate : dueDate || undefined}
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-violet-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500 dark:text-slate-400">{t('tasks.dueDate')}</label>
              <input
                type="date"
                aria-label={t('tasks.dueDate')}
                min={startDate || undefined}
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-violet-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
            <label className="flex items-center gap-2 text-sm text-slate-800 dark:text-slate-200">
              <input type="checkbox" checked={completed} onChange={event => {
                setCompleted(event.target.checked)
                setActualDate(event.target.checked ? localDate() : '')
              }} className="h-4 w-4 accent-violet-600" />
              {zh ? '已完成' : 'Completed'}
            </label>
            {completed && <label className="mt-3 block text-xs text-slate-500 dark:text-slate-400">
              {zh ? '实际完成日期' : 'Actual completion date'}
              <input type="date" required min={startDate || undefined} max={today} value={actualDate} onChange={event => setActualDate(event.target.value)} className="mt-1 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 focus:border-violet-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100" />
            </label>}
          </div>

          <div className="mt-2 flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              disabled={saving || !title.trim()}
              className="rounded-md bg-violet-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-violet-400 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
            >
              {saving ? t('tasks.saving') : t('common.save')}
            </button>
          </div>
          </fieldset>
        </form>
      </div>
    </div>
  )
}

export default function TaskModal({ open, initial, onClose, onSave }: Props) {
  if (!open) return null
  // key 变化时 React 重新挂载 Inner，state 自然重置
  return (
    <TaskModalInner
      key={initial?.id ?? 'new'}
      initial={initial}
      onClose={onClose}
      onSave={onSave}
    />
  )
}
