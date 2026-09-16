import { create } from 'zustand'
import { api } from './api'
import { format } from 'date-fns'

export interface Task {
  id: string
  title: string
  description?: string
  category?: string
  startDate?: string  // 'YYYY-MM-DD'
  dueDate?: string    // 'YYYY-MM-DD'
  completed: boolean
  completedAt?: string
  actualCompletionDate?: string
  createdAt: string
  updatedAt: string
}

interface TaskApiRaw {
  id: string
  title: string
  description?: string | null
  category?: string | null
  start_date?: string | null
  due_date?: string | null
  completed: boolean
  completed_at?: string | null
  actual_completion_date?: string | null
  created_at: string
  updated_at: string
}

// snake_case → camelCase
const fromRaw = (r: TaskApiRaw): Task => ({
  id: r.id,
  title: r.title,
  description: r.description ?? undefined,
  category: r.category ?? undefined,
  startDate: r.start_date ?? undefined,
  dueDate: r.due_date ?? undefined,
  completed: r.completed,
  completedAt: r.completed_at ?? undefined,
  actualCompletionDate: r.actual_completion_date ?? undefined,
  createdAt: r.created_at,
  updatedAt: r.updated_at,
})

export interface TaskCreatePayload {
  title: string
  description?: string
  category?: string
  startDate?: string | null
  dueDate?: string | null
  completed?: boolean
  actualCompletionDate?: string | null
  topicId?: string
  timezone?: string
}

interface TaskState {
  tasks: Task[]
  loading: boolean
  loadTasks: () => Promise<void>
  addTask: (payload: TaskCreatePayload) => Promise<void>
  updateTask: (id: string, patch: Partial<TaskCreatePayload & { completed: boolean }>) => Promise<void>
  toggleComplete: (id: string) => Promise<void>
  deleteTask: (id: string) => Promise<void>
}

export const useTaskStore = create<TaskState>((set, get) => ({
  tasks: [],
  loading: false,

  loadTasks: async () => {
    set({ loading: true })
    try {
      const raw = await api.get<TaskApiRaw[]>('/api/tasks')
      set({ tasks: raw.map(fromRaw) })
    } finally {
      set({ loading: false })
    }
  },

  addTask: async (payload) => {
    const raw = await api.post<TaskApiRaw>('/api/tasks', {
      title: payload.title,
      description: payload.description,
      category: payload.category,
      start_date: payload.startDate,
      due_date: payload.dueDate,
      completed: payload.completed,
      actual_completion_date: payload.actualCompletionDate,
      topic_id: payload.topicId,
      timezone: payload.timezone,
    })
    set((s) => ({ tasks: [fromRaw(raw), ...s.tasks] }))
  },

  updateTask: async (id, patch) => {
    const raw = await api.patch<TaskApiRaw>(`/api/tasks/${id}`, {
      title: patch.title,
      description: patch.description,
      category: patch.category,
      start_date: patch.startDate,
      due_date: patch.dueDate,
      completed: patch.completed,
      actual_completion_date: patch.actualCompletionDate,
      timezone: patch.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone,
    })
    set((s) => ({ tasks: s.tasks.map((t) => (t.id === id ? fromRaw(raw) : t)) }))
  },

  toggleComplete: async (id) => {
    const task = get().tasks.find((t) => t.id === id)
    if (!task) return
    // 乐观更新
    set((s) => ({
      tasks: s.tasks.map((t) =>
        t.id === id ? { ...t, completed: !t.completed, completedAt: !t.completed ? new Date().toISOString() : undefined,
          actualCompletionDate: !t.completed ? format(new Date(), 'yyyy-MM-dd') : undefined } : t,
      ),
    }))
    try {
      const raw = await api.patch<TaskApiRaw>(`/api/tasks/${id}`, { completed: !task.completed,
        actual_completion_date: !task.completed ? format(new Date(), 'yyyy-MM-dd') : null,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone })
      set((s) => ({ tasks: s.tasks.map((t) => (t.id === id ? fromRaw(raw) : t)) }))
    } catch (error) {
      // 回滚
      set((s) => ({
        tasks: s.tasks.map((t) => (t.id === id ? task : t)),
      }))
      throw error
    }
  },

  deleteTask: async (id) => {
    const previous = get().tasks
    set((s) => ({ tasks: s.tasks.filter((t) => t.id !== id) }))
    try {
      await api.del(`/api/tasks/${id}`)
    } catch (error) {
      const deleted = previous.find((task) => task.id === id)
      set((s) => ({ tasks: deleted && !s.tasks.some((task) => task.id === id) ? [...s.tasks, deleted] : s.tasks }))
      throw error
    }
  },
}))
