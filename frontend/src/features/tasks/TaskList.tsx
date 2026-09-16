import { useState } from 'react'
import { Check, ChevronDown, Trash2 } from 'lucide-react'
import type { Task } from '../../lib/taskStore'
import { useI18n } from '../../lib/I18nProvider'
import { completionDate, taskTimeline } from './taskTimeline'

interface Props {
  tasks: Task[]
  today: string
  pendingIds: Set<string>
  onToggle: (id: string) => void
  onEdit: (task: Task) => void
  onDelete: (id: string) => void
}

export default function TaskList({ tasks, today, pendingIds, onToggle, onEdit, onDelete }: Props) {
  const [completedExpanded, setCompletedExpanded] = useState(true)
  const { lang } = useI18n()
  const zh = lang === 'zh'
  const incomplete = tasks.filter(task => !task.completed).sort((a, b) => (a.dueDate ?? '9999').localeCompare(b.dueDate ?? '9999'))
  const completed = tasks.filter(task => task.completed).sort((a, b) => (completionDate(b) ?? '').localeCompare(completionDate(a) ?? ''))
  const row = (task: Task) => {
    const actual = completionDate(task)
    const overdue = taskTimeline(task, today)?.overdueDays ?? 0
    return <div key={task.id} className="flex items-start gap-2 border-b border-slate-100 py-3 last:border-0 dark:border-slate-800">
      <button type="button" disabled={pendingIds.has(task.id)} aria-label={zh ? (task.completed ? '重新打开任务' : '完成任务') : (task.completed ? 'Reopen task' : 'Complete task')} aria-pressed={task.completed} onClick={() => onToggle(task.id)} className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border disabled:opacity-50 ${task.completed ? 'border-emerald-500 bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300' : 'border-slate-400 hover:border-violet-500'}`}>{task.completed && <Check size={15} />}</button>
      <button type="button" onClick={() => onEdit(task)} className="min-w-0 flex-1 rounded text-left hover:text-violet-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-500">
        <span className="block break-words text-sm font-medium text-slate-900 dark:text-slate-100">{task.title}</span>
        <span className="mt-1 flex flex-wrap gap-x-2 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
          {task.category && <span>{task.category}</span>}
          {task.dueDate && <span>{zh ? '截止' : 'Due'} {task.dueDate}</span>}
          {actual && <span className="text-emerald-700 dark:text-emerald-400">{zh ? '完成' : 'Finished'} {actual}</span>}
          {overdue > 0 && <span className="text-orange-700 dark:text-orange-400">{zh ? `延期 ${overdue} 天` : `${overdue} days overdue`}</span>}
          {!task.startDate && !task.dueDate && !actual && <span>{zh ? '未排期' : 'Unscheduled'}</span>}
        </span>
      </button>
      <button type="button" disabled={pendingIds.has(task.id)} aria-label={zh ? '删除任务' : 'Delete task'} onClick={() => onDelete(task.id)} className="rounded-lg p-2 text-slate-400 hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950"><Trash2 size={15} /></button>
    </div>
  }
  return <div>
    {tasks.length === 0 && <p className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500 dark:border-slate-700">{zh ? '没有符合条件的任务' : 'No matching tasks'}</p>}
    {incomplete.length > 0 && <section><h3 className="text-xs font-medium text-slate-500">{zh ? '未完成' : 'Open'} · {incomplete.length}</h3>{incomplete.map(row)}</section>}
    {completed.length > 0 && <section className="mt-4"><button type="button" aria-expanded={completedExpanded} onClick={() => setCompletedExpanded(value => !value)} className="mb-1 flex items-center gap-1 text-xs font-medium text-slate-500"><ChevronDown size={14} className={completedExpanded ? '' : '-rotate-90'} />{zh ? '已完成' : 'Completed'} · {completed.length}</button>{completedExpanded && completed.map(row)}</section>}
  </div>
}
