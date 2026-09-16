import { differenceInCalendarDays, format, parseISO } from 'date-fns'
import type { Task } from '../../lib/taskStore'

export const localDate = (date = new Date()) => format(date, 'yyyy-MM-dd')

export function completionDate(task: Task): string | undefined {
  if (!task.completed) return undefined
  return task.actualCompletionDate ?? (task.completedAt ? localDate(parseISO(task.completedAt)) : undefined)
}

export function taskTimeline(task: Task, today: string) {
  const actual = completionDate(task)
  const dates = [task.dueDate, actual].filter((date): date is string => !!date).sort()
  const start = task.startDate ?? dates[0]
  if (!start) return null
  const activeEnd = actual ?? (task.completed ? task.dueDate ?? start
    : task.dueDate ? (task.dueDate < today ? today : task.dueDate) : start)
  // 淡色计划尾段参与排布，但不参与当天进行中筛选。
  const end = [start, activeEnd, task.dueDate ?? start].sort().at(-1)!
  const overdueDays = task.dueDate && activeEnd > task.dueDate
    ? differenceInCalendarDays(parseISO(activeEnd), parseISO(task.dueDate)) : 0
  return { start, end, activeEnd, actual, overdueDays }
}

export function taskActiveOn(task: Task, day: string, today: string) {
  const interval = taskTimeline(task, today)
  return !!interval && day >= interval.start && day <= interval.activeEnd
}

export function dayTone(task: Task, day: string, today: string) {
  const interval = taskTimeline(task, today)
  if (interval?.actual && day > interval.actual) return 'planned'
  if (task.dueDate && day > task.dueDate) return 'overdue'
  return task.completed ? 'completed' : 'normal'
}
