// Explicit execution only: node --experimental-strip-types --test tests/taskTimeline.test.ts
import assert from 'node:assert/strict'
import test from 'node:test'
import { completionDate, dayTone, localDate, taskActiveOn, taskTimeline } from '../src/features/tasks/taskTimeline.ts'
import type { Task } from '../src/lib/taskStore.ts'

const task: Task = { id: '1', title: 'Task', completed: true, startDate: '2026-08-28', dueDate: '2026-09-02', actualCompletionDate: '2026-09-05', createdAt: '', updatedAt: '' }
const today = '2026-09-16'

test('late completion crosses month with continuous active interval', () => {
  assert.equal(taskTimeline(task, today)?.end, '2026-09-05')
  assert.equal(taskTimeline(task, today)?.overdueDays, 3)
  assert.equal(dayTone(task, '2026-09-02', today), 'completed')
  assert.equal(dayTone(task, '2026-09-03', today), 'overdue')
  assert.equal(taskActiveOn(task, '2026-09-05', today), true)
  assert.equal(taskActiveOn(task, '2026-09-06', today), false)
})

test('early completion retains a planned tail excluded from selection', () => {
  const early = { ...task, actualCompletionDate: '2026-08-30' }
  assert.equal(taskTimeline(early, today)?.end, task.dueDate)
  assert.equal(dayTone(early, '2026-08-31', today), 'planned')
  assert.equal(taskActiveOn(early, '2026-08-31', today), false)
  assert.equal(taskActiveOn(early, '2026-08-30', today), true)
})

test('open overdue interval advances with today', () => {
  const open = { ...task, completed: false, actualCompletionDate: undefined }
  assert.equal(taskTimeline(open, today)?.activeEnd, today)
  assert.equal(taskTimeline(open, '2026-09-17')?.overdueDays, 15)
  assert.equal(dayTone(open, '2026-09-03', today), 'overdue')
})

test('same-day, missing dates, and date-only completion', () => {
  assert.equal(taskTimeline({ ...task, actualCompletionDate: task.dueDate }, today)?.overdueDays, 0)
  assert.equal(taskTimeline({ ...task, startDate: undefined, actualCompletionDate: '2026-09-01' }, today)?.start, '2026-09-01')
  assert.equal(taskTimeline({ ...task, dueDate: undefined }, today)?.overdueDays, 0)
  const open = { ...task, completed: false, dueDate: undefined }
  assert.equal(taskTimeline(open, today)?.end, task.startDate)
  assert.equal(taskTimeline({ ...open, startDate: undefined }, today), null)
  assert.equal(completionDate(task), '2026-09-05')
  assert.equal(completionDate({ ...task, actualCompletionDate: undefined, completedAt: '2026-09-05T01:00:00Z' }), localDate(new Date('2026-09-05T01:00:00Z')))
})
