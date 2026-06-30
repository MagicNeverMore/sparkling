import { useState } from 'react'
import { Check } from 'lucide-react'
import { parseISO, compareAsc } from 'date-fns'
import type { Task } from '../../lib/taskStore'

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

  return (
    <div className="group flex items-center gap-3 rounded-lg px-2 py-2.5 transition hover:bg-slate-800/50">
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
        <p className={`text-sm leading-snug ${task.completed ? 'text-slate-500 line-through' : 'text-slate-100'}`}>
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
              截止 {task.dueDate}
            </span>
          )}
        </div>
      </div>

      {/* 三点菜单 */}
      <div className="relative shrink-0">
        <button
          type="button"
          onClick={() => setMenuOpen(!menuOpen)}
          className="flex h-6 w-6 items-center justify-center rounded text-slate-600 opacity-0 transition hover:bg-slate-700 hover:text-slate-300 group-hover:opacity-100"
        >
          ···
        </button>
        {menuOpen && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
            <div className="absolute right-0 z-20 mt-1 w-28 rounded-lg border border-slate-700 bg-slate-900 py-1 shadow-xl">
              <button
                type="button"
                onClick={() => { onEdit(task); setMenuOpen(false) }}
                className="block w-full px-3 py-1.5 text-left text-sm text-slate-300 hover:bg-slate-800"
              >
                编辑
              </button>
              <button
                type="button"
                onClick={() => { onDelete(task.id); setMenuOpen(false) }}
                className="block w-full px-3 py-1.5 text-left text-sm text-rose-400 hover:bg-slate-800"
              >
                删除
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
        <span className="text-xs font-medium text-slate-500">待完成 {incomplete.length}</span>
      </div>
      {incomplete.length === 0 ? (
        <div className="flex min-h-20 items-center justify-center rounded-lg border border-dashed border-slate-800 text-sm text-slate-600">
          暂无待完成任务
        </div>
      ) : (
        <div className="rounded-xl border border-slate-800 bg-slate-900 px-2 py-1">
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
            className="mb-1 flex items-center gap-1 px-2 text-xs font-medium text-slate-500 hover:text-slate-400"
          >
            <span className={`transition-transform ${completedCollapsed ? '' : 'rotate-90'}`}>▶</span>
            已完成 {completed.length}
          </button>
          {!completedCollapsed && (
            <div className="rounded-xl border border-slate-800 bg-slate-900 px-2 py-1">
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
