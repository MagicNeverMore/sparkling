import { useEffect, useState } from 'react'
import { useTaskStore, type Task, type TaskCreatePayload } from '../lib/taskStore'
import DueSoonCards from '../components/tasks/DueSoonCards'
import TaskCalendar from '../components/tasks/TaskCalendar'
import TaskList from '../components/tasks/TaskList'
import TaskModal from '../components/tasks/TaskModal'
import { useToast } from '../components/useToast'
import { useI18n } from '../lib/I18nProvider'

export default function Tasks() {
  const { tasks, loading, loadTasks, addTask, updateTask, toggleComplete, deleteTask } = useTaskStore()
  const { t } = useI18n()
  const { show: showToast } = useToast()

  const [modalOpen, setModalOpen] = useState(false)
  const [editingTask, setEditingTask] = useState<Task | null>(null)
  const [highlightDate, setHighlightDate] = useState<Date | null>(null)

  useEffect(() => {
    void loadTasks()
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
    setEditingTask(task)
    setModalOpen(true)
  }

  const handleDelete = async (id: string) => {
    await deleteTask(id)
    showToast(t('common.deleted'), 'info')
  }

  const openCreate = () => {
    setEditingTask(null)
    setModalOpen(true)
  }

  return (
    <div className="relative mx-auto w-full max-w-7xl px-4 py-6 md:px-6">
      {/* 页头 */}
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-950 dark:text-slate-100">{t('tasks.title')}</h1>
        <button
          type="button"
          onClick={openCreate}
          className="flex items-center gap-1.5 rounded-lg bg-violet-500 px-3 py-1.5 text-sm font-medium text-white transition hover:bg-violet-400"
        >
          <span className="text-base leading-none">+</span>
          {t('tasks.new')}
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20 text-sm text-slate-500">{t('common.loading')}</div>
      ) : (
        <div className="flex flex-col gap-0 md:grid md:grid-cols-[1fr_320px] md:gap-6 lg:grid-cols-[1fr_360px]">
          {/* 左列：即将截止 + 日历 */}
          <div className="order-2 md:order-1">
            <DueSoonCards tasks={tasks} onToggle={toggleComplete} onEdit={handleEdit} />
            <TaskCalendar tasks={tasks} onDateClick={setHighlightDate} />
          </div>

          {/* 右列：任务列表 */}
          <div className="order-1 mb-6 md:order-2 md:mb-0">
            <TaskList
              tasks={tasks}
              highlightDate={highlightDate}
              onToggle={toggleComplete}
              onEdit={handleEdit}
              onDelete={handleDelete}
            />
          </div>
        </div>
      )}

      <TaskModal
        open={modalOpen}
        initial={editingTask}
        onClose={() => setModalOpen(false)}
        onSave={handleSave}
      />
    </div>
  )
}
