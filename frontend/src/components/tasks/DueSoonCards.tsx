import { useState } from 'react'
import { differenceInCalendarDays, parseISO, startOfToday } from 'date-fns'
import type { Task } from '../../lib/taskStore'

interface Props {
  tasks: Task[]
  onToggle: (id: string) => void
  onEdit: (task: Task) => void
}

const DEFAULT_VISIBLE = 4

function urgencyColor(daysLeft: number) {
  if (daysLeft <= 0) return 'text-rose-400'
  if (daysLeft <= 3) return 'text-amber-400'
  return 'text-slate-400'
}

function dueLabelText(daysLeft: number) {
  if (daysLeft < 0) return `逾期 ${Math.abs(daysLeft)} 天`
  if (daysLeft === 0) return '今天截止'
  return `还有 ${daysLeft} 天`
}

export default function DueSoonCards({ tasks, onToggle, onEdit }: Props) {
  const [expanded, setExpanded] = useState(false)
  const today = startOfToday()

  // 15 天内未完成的任务，按截止日期升序
  const dueSoon = tasks
    .filter((t) => !t.completed && t.dueDate)
    .map((t) => ({ task: t, daysLeft: differenceInCalendarDays(parseISO(t.dueDate!), today) }))
    .filter(({ daysLeft }) => daysLeft <= 15)
    .sort((a, b) => a.daysLeft - b.daysLeft)

  const total = dueSoon.length
  const visible = expanded ? dueSoon : dueSoon.slice(0, DEFAULT_VISIBLE)

  if (total === 0) return null

  return (
    <div className="mb-6">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-medium text-slate-400">即将截止</h2>
        <span className="text-xs text-slate-500">
          {visible.length}/{total}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {visible.map(({ task, daysLeft }) => (
          <div
            key={task.id}
            className="group flex flex-col gap-2 rounded-xl border border-slate-800 bg-slate-900 p-4 transition hover:border-slate-700"
          >
            <div className="flex items-start justify-between gap-2">
              <button
                type="button"
                onClick={() => onToggle(task.id)}
                className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-slate-600 transition hover:border-violet-400"
              />
              {task.category && (
                <span className="rounded-md bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
                  {task.category}
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={() => onEdit(task)}
              className="text-left text-sm font-medium text-slate-100 line-clamp-2 hover:text-violet-400"
            >
              {task.title}
            </button>
            <span className={`text-xs font-medium ${urgencyColor(daysLeft)}`}>
              {dueLabelText(daysLeft)}
            </span>
          </div>
        ))}
      </div>
      {total > DEFAULT_VISIBLE && (
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="mt-3 text-xs text-slate-500 hover:text-slate-300"
        >
          {expanded ? '收起' : `展开全部 ${total} 个`}
        </button>
      )}
    </div>
  )
}
