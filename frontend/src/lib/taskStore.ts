import { create } from 'zustand'
import { api } from './api'

export interface Task {
  id: string
  title: string
  description?: string
  category?: string
  startDate?: string  // 'YYYY-MM-DD'
  dueDate?: string    // 'YYYY-MM-DD'
  completed: boolean
  completedAt?: string
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
  createdAt: r.created_at,
  updatedAt: r.updated_at,
})

export interface TaskCreatePayload {
  title: string
  description?: string
  category?: string
  startDate?: string
  dueDate?: string
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
    })
    set((s) => ({ tasks: s.tasks.map((t) => (t.id === id ? fromRaw(raw) : t)) }))
  },

  toggleComplete: async (id) => {
    const task = get().tasks.find((t) => t.id === id)
    if (!task) return
    // 乐观更新
    set((s) => ({
      tasks: s.tasks.map((t) =>
        t.id === id ? { ...t, completed: !t.completed, completedAt: !t.completed ? new Date().toISOString() : undefined } : t,
      ),
    }))
    try {
      const raw = await api.patch<TaskApiRaw>(`/api/tasks/${id}`, { completed: !task.completed })
      set((s) => ({ tasks: s.tasks.map((t) => (t.id === id ? fromRaw(raw) : t)) }))
    } catch {
      // 回滚
      set((s) => ({
        tasks: s.tasks.map((t) => (t.id === id ? task : t)),
      }))
    }
  },

  deleteTask: async (id) => {
    const previous = get().tasks
    set((s) => ({ tasks: s.tasks.filter((t) => t.id !== id) }))
    try {
      await api.del(`/api/tasks/${id}`)
    } catch {
      set({ tasks: previous })
    }
  },
}))
