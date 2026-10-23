import { useState } from 'react'
import { ArrowDown, ArrowUp, Check, GripVertical } from 'lucide-react'
import type { BoardStatus, Task } from '../../lib/taskStore'
import { useI18n } from '../../lib/I18nProvider'
import { taskTimeline } from './taskTimeline'

interface Props {
  tasks: Task[]
  today: string
  busy: boolean
  onMove: (id: string, status: BoardStatus, beforeId?: string) => void
  onComplete: (id: string) => void
  onEdit: (task: Task) => void
}

const columns: BoardStatus[] = ['doing', 'next', 'backlog']
const accents = { doing: 'bg-violet-500', next: 'bg-sky-500', backlog: 'bg-slate-400' }

export default function TaskBoard({ tasks, today, busy, onMove, onComplete, onEdit }: Props) {
  const { lang } = useI18n()
  const zh = lang === 'zh'
  const [activeTab, setActiveTab] = useState<BoardStatus>('doing')
  const [dragId, setDragId] = useState<string | null>(null)
  const [dropTarget, setDropTarget] = useState<string | null>(null)
  const labels = { doing: zh ? '正在做' : 'Doing', next: zh ? '下一步' : 'Up next', backlog: zh ? '待安排' : 'Backlog' }
  const hints = { doing: zh ? '专注手头正在推进的事' : 'Focus on what is in progress', next: zh ? '从上到下，就是执行顺序' : 'Your next actions, in order', backlog: zh ? '按截止日期排序，随时挑选' : 'Sorted by due date, ready to pick' }
  const grouped = Object.fromEntries(columns.map(status => [status, tasks.filter(task => !task.completed && (task.boardStatus ?? 'backlog') === status).sort((a, b) => {
    if (status === 'backlog') return (a.dueDate ?? '9999').localeCompare(b.dueDate ?? '9999') || a.createdAt.localeCompare(b.createdAt) || a.id.localeCompare(b.id)
    return (a.boardPosition ?? 0) - (b.boardPosition ?? 0) || a.createdAt.localeCompare(b.createdAt) || a.id.localeCompare(b.id)
  })])) as Record<BoardStatus, Task[]>
  const drop = (status: BoardStatus, beforeId?: string) => {
    if (!busy && dragId && dragId !== beforeId) onMove(dragId, status, status === 'backlog' ? undefined : beforeId)
    setDragId(null)
    setDropTarget(null)
  }
  const buttonClass = 'rounded-md px-2 py-1.5 text-xs text-slate-600 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-500 disabled:cursor-not-allowed disabled:opacity-40 dark:text-slate-300 dark:hover:bg-slate-800'

  return <section aria-label={zh ? '任务看板' : 'Task board'} aria-busy={busy} className="mb-7">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
      <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">{zh ? '执行看板' : 'Execution board'}</h2>
      <p className="text-xs text-slate-500" aria-live="polite">{busy ? (zh ? '正在保存…' : 'Saving…') : (zh ? '拖动卡片调整安排，也可使用卡片按钮' : 'Drag cards or use their controls to arrange tasks')}</p>
    </div>
    <div className="mb-3 flex gap-1 rounded-lg bg-slate-100 p-1 md:hidden dark:bg-slate-900" role="group" aria-label={zh ? '选择看板列' : 'Choose board column'}>
      {columns.map(status => <button key={status} type="button" aria-pressed={activeTab === status} onClick={() => setActiveTab(status)} className={`flex-1 rounded-md px-2 py-2 text-sm ${activeTab === status ? 'bg-white font-medium text-violet-700 shadow-sm dark:bg-slate-800 dark:text-violet-300' : 'text-slate-500'}`}>{labels[status]} {grouped[status].length}</button>)}
    </div>
    <div className="grid items-start gap-3 md:grid-cols-3">
      {columns.map(status => <section key={status} aria-label={labels[status]} onDragOver={event => { if (dragId && !busy) { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; setDropTarget(status) } }} onDrop={event => { event.preventDefault(); drop(status) }} className={`${activeTab === status ? 'block' : 'hidden md:block'} rounded-xl border p-3 ${dropTarget === status ? 'border-violet-400 bg-violet-50 dark:bg-violet-950/30' : 'border-slate-200 bg-slate-50/80 dark:border-slate-800 dark:bg-slate-900/50'}`}>
        <div className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${accents[status]}`} /><h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{labels[status]}</h3><span className="text-xs text-slate-500">{grouped[status].length}</span></div>
        <p className="mb-3 mt-1 text-xs text-slate-500">{hints[status]}</p>
        {status === 'doing' && grouped.doing.length > 3 && <p role="status" className="mb-3 rounded-lg bg-amber-50 p-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-200">{zh ? '同时进行超过 3 项，建议先聚焦最重要的任务。' : 'More than 3 in progress. Consider focusing on the most important tasks.'}</p>}
        <div className="max-h-[360px] min-h-28 space-y-2 overflow-y-auto pr-1">
          {grouped[status].length === 0 && <p className="rounded-lg border border-dashed border-slate-300 px-3 py-8 text-center text-xs text-slate-500 dark:border-slate-700">{zh ? '将任务移到这里' : 'Move a task here'}</p>}
          {grouped[status].map((task, index, list) => {
            const overdue = taskTimeline(task, today)?.overdueDays ?? 0
            return <article key={task.id} draggable={!busy} onDragStart={event => { event.dataTransfer.setData('text/plain', task.id); event.dataTransfer.effectAllowed = 'move'; setDragId(task.id) }} onDragEnd={() => { setDragId(null); setDropTarget(null) }} onDragOver={event => { if (dragId && !busy) { event.preventDefault(); event.stopPropagation(); setDropTarget(task.id) } }} onDrop={event => { event.preventDefault(); event.stopPropagation(); drop(status, task.id) }} className={`rounded-lg border bg-white p-3 shadow-sm dark:bg-slate-900 ${dropTarget === task.id ? 'border-violet-500 border-t-4' : 'border-slate-200 dark:border-slate-700'} ${dragId === task.id ? 'opacity-50' : ''}`}>
              <div className="flex items-start gap-2"><GripVertical size={15} aria-hidden="true" className="mt-0.5 shrink-0 cursor-grab text-slate-400" /><button type="button" disabled={busy} onClick={() => onEdit(task)} className="min-w-0 flex-1 break-words text-left text-sm font-medium text-slate-900 hover:text-violet-600 dark:text-slate-100">{task.title}</button></div>
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500 dark:text-slate-400">
                {task.category && <span className="rounded bg-slate-100 px-1.5 py-0.5 dark:bg-slate-800">{task.category}</span>}
                <span>{task.dueDate ? `${zh ? '截止' : 'Due'} ${task.dueDate}` : (zh ? '无截止日期' : 'No due date')}</span>
                {overdue > 0 && <span className="font-medium text-orange-700 dark:text-orange-400">{zh ? `已延期 ${overdue} 天` : `${overdue} days overdue`}</span>}
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-1 border-t border-slate-100 pt-2 dark:border-slate-800">
                {columns.filter(value => value !== status).map(value => <button key={value} type="button" disabled={busy} onClick={() => onMove(task.id, value)} className={buttonClass}>{value === 'doing' ? (zh ? '开始' : 'Start') : value === 'next' ? (zh ? '下一步' : 'Up next') : (zh ? '待安排' : 'Backlog')}</button>)}
                <button type="button" disabled={busy} onClick={() => onComplete(task.id)} className={`${buttonClass} flex items-center gap-1`}><Check size={13} />{zh ? '完成' : 'Done'}</button>
                {status !== 'backlog' && <span className="ml-auto flex"><button type="button" disabled={busy || index === 0} aria-label={zh ? '上移任务' : 'Move task up'} onClick={() => onMove(task.id, status, list[index - 1].id)} className={buttonClass}><ArrowUp size={14} /></button><button type="button" disabled={busy || index === list.length - 1} aria-label={zh ? '下移任务' : 'Move task down'} onClick={() => onMove(task.id, status, list[index + 2]?.id)} className={buttonClass}><ArrowDown size={14} /></button></span>}
              </div>
            </article>
          })}
        </div>
      </section>)}
    </div>
  </section>
}
