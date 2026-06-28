import { useState } from 'react'
import type { Task, TaskCreatePayload } from '../../lib/taskStore'

interface Props {
  open: boolean
  initial?: Task | null
  onClose: () => void
  onSave: (payload: TaskCreatePayload) => Promise<void>
}

const CATEGORIES = ['自媒体', 'App 开发', '其他']

// 内层组件通过 key 重置，避免 useEffect + setState 的 lint 问题
function TaskModalInner({ initial, onClose, onSave }: Omit<Props, 'open'>) {
  const [title, setTitle] = useState(initial?.title ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [category, setCategory] = useState(initial?.category ?? '')
  const [startDate, setStartDate] = useState(initial?.startDate ?? '')
  const [dueDate, setDueDate] = useState(initial?.dueDate ?? '')
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return
    setSaving(true)
    try {
      await onSave({
        title: title.trim(),
        description: description.trim() || undefined,
        category: category.trim() || undefined,
        startDate: startDate || undefined,
        dueDate: dueDate || undefined,
      })
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-2xl">
        <h2 className="mb-4 text-base font-semibold text-slate-100">
          {initial ? '编辑任务' : '新建任务'}
        </h2>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          {/* 标题 */}
          <div>
            <label className="mb-1 block text-xs text-slate-400">标题 *</label>
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="任务标题"
              className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-violet-400"
            />
          </div>

          {/* 描述 */}
          <div>
            <label className="mb-1 block text-xs text-slate-400">描述</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="可选"
              className="w-full resize-none rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-violet-400"
            />
          </div>

          {/* 分类 */}
          <div>
            <label className="mb-1 block text-xs text-slate-400">分类</label>
            <div className="flex flex-wrap gap-2">
              {CATEGORIES.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setCategory(category === c ? '' : c)}
                  className={`rounded-md border px-3 py-1 text-xs transition ${
                    category === c
                      ? 'border-violet-400 bg-violet-400/10 text-violet-400'
                      : 'border-slate-700 text-slate-400 hover:border-slate-600 hover:text-slate-300'
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
              value={CATEGORIES.includes(category) ? '' : category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="自定义分类…"
              className="mt-2 w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 outline-none focus:border-violet-400"
            />
          </div>

          {/* 日期 */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-slate-400">开始日期</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 outline-none focus:border-violet-400 [color-scheme:dark]"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-400">截止日期</label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 outline-none focus:border-violet-400 [color-scheme:dark]"
              />
            </div>
          </div>

          <div className="mt-2 flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-300 transition hover:bg-slate-800 disabled:cursor-not-allowed"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={saving || !title.trim()}
              className="rounded-md bg-violet-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-violet-400 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
            >
              {saving ? '保存中…' : '保存'}
            </button>
          </div>
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
