import { useState } from 'react'
import { Check } from 'lucide-react'
import { parseISO, compareAsc } from 'date-fns'
import type { Task } from '../../lib/taskStore'
import { useI18n } from '../../lib/I18nProvider'

interface Props {
  tasks: Task[]
  highlightDate: Date | null
  onToggle: (id: string) => void
  onEdit: (task: Task) => void
  onDelete: (id: string) => void
}

function sortByDue(tasks: Task[]) {
  return [...tasks].sort((a, b) => {
    if (!a.dueDate && !b.dueDate) return 0
    if (!a.dueDate) return 1
    if (!b.dueDate) return -1
    return compareAsc(parseISO(a.dueDate), parseISO(b.dueDate))
  })
}

function TaskRow({
  task,
  onToggle,
  onEdit,
  onDelete,
}: {
  task: Task
  onToggle: (id: string) => void
  onEdit: (task: Task) => void
  onDelete: (id: string) => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const { t } = useI18n()

  return (
    <div className="group flex items-center gap-3 rounded-lg px-2 py-2.5 transition hover:bg-slate-100 dark:hover:bg-slate-800/50">
      {/* 复选框 */}
      <button
        type="button"
        onClick={() => onToggle(task.id)}
        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition ${
          task.completed
            ? 'border-emerald-400 bg-emerald-400/20 text-emerald-400'
            : 'border-slate-600 hover:border-violet-400'
        }`}
      >
        {task.completed && <Check size={12} strokeWidth={2.5} />}
      </button>

      {/* 内容 */}
      <div className="min-w-0 flex-1">
        <p className={`text-sm leading-snug ${task.completed ? 'text-slate-500 line-through' : 'text-slate-950 dark:text-slate-100'}`}>
          {task.title}
        </p>
        <div className="mt-0.5 flex flex-wrap items-center gap-2">
          {task.category && (
            <span className={`text-xs ${task.completed ? 'text-slate-600' : 'text-slate-500'}`}>
              {task.category}
            </span>
          )}
          {task.dueDate && (
            <span className={`text-xs ${task.completed ? 'text-slate-600' : 'text-slate-500'}`}>
              {t('tasks.due', { date: task.dueDate })}
            </span>
          )}
        </div>
      </div>

      {/* 三点菜单 */}
      <div className="relative shrink-0">
        <button
          type="button"
          onClick={() => setMenuOpen(!menuOpen)}
          className="flex h-6 w-6 items-center justify-center rounded text-slate-500 opacity-0 transition hover:bg-slate-100 hover:text-slate-900 group-hover:opacity-100 dark:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-300"
        >
          ···
        </button>
        {menuOpen && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
            <div className="absolute right-0 z-20 mt-1 w-28 rounded-lg border border-slate-200 bg-white py-1 shadow-xl dark:border-slate-700 dark:bg-slate-900">
              <button
                type="button"
                onClick={() => { onEdit(task); setMenuOpen(false) }}
                className="block w-full px-3 py-1.5 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                {t('tasks.edit')}
              </button>
              <button
                type="button"
                onClick={() => { onDelete(task.id); setMenuOpen(false) }}
                className="block w-full px-3 py-1.5 text-left text-sm text-rose-500 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-slate-800"
              >
                {t('common.delete')}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default function TaskList({ tasks, highlightDate, onToggle, onEdit, onDelete }: Props) {
  const [completedCollapsed, setCompletedCollapsed] = useState(true)
  const { t } = useI18n()

  const incomplete = sortByDue(tasks.filter((t) => !t.completed))
  const completed = tasks
    .filter((t) => t.completed)
    .sort((a, b) => {
      if (!a.completedAt || !b.completedAt) return 0
      return compareAsc(parseISO(b.completedAt), parseISO(a.completedAt))
    })

  // 高亮日期时筛选对应任务（仅用于视觉提示，不做过滤）
  void highlightDate

  return (
    <div className="flex flex-col">
      {/* 未完成 */}
      <div className="mb-1 flex items-center justify-between px-2">
        <span className="text-xs font-medium text-slate-500">{t('tasks.todo', { count: incomplete.length })}</span>
      </div>
      {incomplete.length === 0 ? (
        <div className="flex min-h-20 items-center justify-center rounded-lg border border-dashed border-slate-300 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-600">
          {t('tasks.noTodo')}
        </div>
      ) : (
        <div className="rounded-xl border border-slate-200 bg-white px-2 py-1 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
          {incomplete.map((t) => (
            <TaskRow key={t.id} task={t} onToggle={onToggle} onEdit={onEdit} onDelete={onDelete} />
          ))}
        </div>
      )}

      {/* 已完成 */}
      {completed.length > 0 && (
        <div className="mt-4">
          <button
            type="button"
            onClick={() => setCompletedCollapsed(!completedCollapsed)}
            className="mb-1 flex items-center gap-1 px-2 text-xs font-medium text-slate-500 hover:text-slate-700 dark:hover:text-slate-400"
          >
            <span className={`transition-transform ${completedCollapsed ? '' : 'rotate-90'}`}>▶</span>
            {t('tasks.completed', { count: completed.length })}
          </button>
          {!completedCollapsed && (
            <div className="rounded-xl border border-slate-200 bg-white px-2 py-1 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
              {completed.map((t) => (
                <TaskRow key={t.id} task={t} onToggle={onToggle} onEdit={onEdit} onDelete={onDelete} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
