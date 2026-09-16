import { useEffect, useRef, useState } from 'react'
import { Plus } from 'lucide-react'
import { useTaskStore, type Task, type TaskCreatePayload } from '../../lib/taskStore'
import TaskCalendar from './TaskCalendar'
import TaskList from './TaskList'
import TaskModal from './TaskModal'
import ConfirmDialog from '../../components/ConfirmDialog'
import { useToast } from '../../components/useToast'
import { useI18n } from '../../lib/I18nProvider'
import { taskActiveOn } from './taskTimeline'
import { useToday } from './useToday'

export default function Tasks() {
  const { tasks, loading, loadTasks, addTask, updateTask, toggleComplete, deleteTask } = useTaskStore()
  const { t, lang } = useI18n()
  const zh = lang === 'zh'
  const { show: showToast } = useToast()
  const today = useToday()
  const [modalOpen, setModalOpen] = useState(false)
  const [editingTask, setEditingTask] = useState<Task | null>(null)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState('')
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set())
  const pending = useRef(new Set<string>())
  const modalTrigger = useRef<HTMLElement | null>(null)
  const refresh = () => {
    setLoadError('')
    void loadTasks().catch(error => setLoadError(error instanceof Error ? error.message : String(error)))
  }
  useEffect(() => {
    void loadTasks().catch(error => setLoadError(error instanceof Error ? error.message : String(error)))
  }, [loadTasks])

  const handleSave = async (payload: TaskCreatePayload) => {
    if (editingTask) {
      await updateTask(editingTask.id, payload)
      showToast(t('tasks.updated'), 'success')
    } else {
      await addTask(payload)
      showToast(t('tasks.created'), 'success')
    }
  }
  const handleEdit = (task: Task) => {
    if (pending.current.has(task.id)) return
    modalTrigger.current = document.activeElement as HTMLElement | null
    setEditingTask(task)
    setModalOpen(true)
  }
  const closeModal = () => {
    setModalOpen(false)
    requestAnimationFrame(() => modalTrigger.current?.focus())
  }
  const act = async (id: string, operation: () => Promise<void>) => {
    if (pending.current.has(id)) return
    pending.current.add(id)
    setPendingIds(new Set(pending.current))
    try { await operation() } catch (error) {
      showToast(error instanceof Error ? error.message : String(error), 'error')
    } finally {
      pending.current.delete(id)
      setPendingIds(new Set(pending.current))
    }
  }
  const visibleTasks = selectedDate ? tasks.filter(task => taskActiveOn(task, selectedDate, today)) : tasks

  return (
    <div className="mx-auto w-full max-w-[1500px] px-4 py-6 md:px-6">
      <header className="mb-6 flex items-start justify-between gap-3">
        <div><h1 className="text-xl font-semibold text-slate-950 dark:text-slate-100">{t('tasks.title')}</h1><p className="mt-1 text-sm text-slate-500">{zh ? '让计划与实际进度，一目了然。' : 'Your plans and actual progress, together.'}</p></div>
        <button type="button" onClick={() => { modalTrigger.current = document.activeElement as HTMLElement | null; setEditingTask(null); setModalOpen(true) }} className="flex shrink-0 items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-2 text-sm font-medium text-white hover:bg-violet-500"><Plus size={16} />{t('tasks.new')}</button>
      </header>
      {loadError && <div role="alert" className="mb-4 rounded-xl bg-rose-50 p-4 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-200">{loadError}<button type="button" onClick={refresh} className="ml-3 underline">{zh ? '重试' : 'Retry'}</button></div>}
      {loading ? <div className="py-20 text-center text-sm text-slate-500">{t('common.loading')}</div> : (
        <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0"><TaskCalendar tasks={tasks} today={today} selectedDate={selectedDate} onDateClick={setSelectedDate} onEdit={handleEdit} /></div>
          <aside className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{selectedDate ?? (zh ? '全部任务' : 'All tasks')} <span className="ml-1 text-slate-400">{visibleTasks.length}</span></h2>
              {selectedDate && <button type="button" onClick={() => setSelectedDate(null)} className="text-xs text-violet-600 dark:text-violet-300">{zh ? '全部任务' : 'All tasks'}</button>}
            </div>
            {selectedDate && <p className="mb-4 text-xs text-slate-500">{zh ? '当天进行或完成的任务，不含提前完成后的计划尾段。' : 'Tasks active or finished on this day; remaining plan tails are excluded.'}</p>}
            <TaskList tasks={visibleTasks} today={today} pendingIds={pendingIds} onToggle={id => { void act(id, () => toggleComplete(id)) }} onEdit={handleEdit} onDelete={setDeleteId} />
          </aside>
        </div>
      )}
      <TaskModal open={modalOpen} initial={editingTask} onClose={closeModal} onSave={handleSave} />
      <ConfirmDialog open={deleteId !== null} title={zh ? '删除任务？' : 'Delete task?'} confirming={deleteId !== null && pendingIds.has(deleteId)} onCancel={() => setDeleteId(null)} onConfirm={() => {
        if (deleteId) void act(deleteId, async () => { await deleteTask(deleteId); setDeleteId(null); showToast(t('common.deleted'), 'info') })
      }}>{zh ? '删除后无法恢复。' : 'This cannot be undone.'}</ConfirmDialog>
    </div>
  )
}
