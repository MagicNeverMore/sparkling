import { create } from 'zustand'
import { ConflictError, type AtomMock, type LinkMock } from './mock'
import { api, ApiError } from './api'

// 后端 API 原始响应类型（snake_case）
interface AtomRaw {
  id: string
  content: string
  content_type: string
  status: string
  version: number
  created_at: string
  updated_at: string
}

interface LinkRaw {
  id: string
  from_atom_id: string
  to_atom_id: string
  link_type: string | null
  confidence: number | null
  source: string
  user_confirmed: boolean
  user_ignored: boolean
  created_at: string
}

const fromAtomRaw = (r: AtomRaw): AtomMock => ({
  id: r.id,
  content: r.content,
  status: r.status as AtomMock['status'],
  version: r.version,
  createdAt: r.created_at,
  updatedAt: r.updated_at,
})

const fromLinkRaw = (r: LinkRaw): LinkMock => ({
  id: r.id,
  fromAtomId: r.from_atom_id,
  toAtomId: r.to_atom_id,
  confidence: r.confidence ?? 0,
  source: r.source as LinkMock['source'],
  userConfirmed: r.user_confirmed,
})

interface State {
  atoms: AtomMock[]
  links: LinkMock[]
  loading: boolean
  errorMessage: string | null
  wsStatus: 'online' | 'reconnecting' | 'offline'
  loadInitial: () => Promise<void>
  addAtom: (content: string) => Promise<void>
  updateAtom: (id: string, patch: Partial<AtomMock>) => Promise<void>
  deleteAtom: (id: string) => Promise<void>
  confirmLink: (id: string) => Promise<void>
  ignoreLink: (id: string) => Promise<void>
  pushSuggestion: (link: LinkMock) => void
  removeAtomLocally: (id: string) => void
  setWsStatus: (status: State['wsStatus']) => void
}

export const useSparklingStore = create<State>((set, get) => ({
  atoms: [],
  links: [],
  loading: true,
  errorMessage: null,
  wsStatus: 'online',

  loadInitial: async () => {
    set({ loading: true, errorMessage: null })
    try {
      const [rawAtoms, rawLinks] = await Promise.all([
        api.get<AtomRaw[]>('/api/atoms'),
        api.get<LinkRaw[]>('/api/links'),
      ])
      set({ atoms: rawAtoms.map(fromAtomRaw), links: rawLinks.map(fromLinkRaw), loading: false })
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      set({ loading: false, errorMessage: message })
    }
  },

  addAtom: async (content: string) => {
    const tempId = `temp-${crypto.randomUUID()}`
    const createdAt = new Date().toISOString()
    const optimistic: AtomMock = { id: tempId, content, status: 'inbox', version: 1, createdAt, updatedAt: createdAt }
    set((state) => ({ atoms: [optimistic, ...state.atoms] }))
    const raw = await api.post<AtomRaw>('/api/atoms', { content })
    const created = fromAtomRaw(raw)
    set((state) => ({ atoms: state.atoms.map((atom) => (atom.id === tempId ? created : atom)) }))
  },

  updateAtom: async (id: string, patch: Partial<AtomMock>) => {
    const current = get().atoms.find((atom) => atom.id === id)
    if (!current) return
    try {
      const raw = await api.patch<AtomRaw>(`/api/atoms/${id}`, { content: patch.content, version: current.version })
      const updated = fromAtomRaw(raw)
      set((state) => ({ atoms: state.atoms.map((atom) => (atom.id === id ? updated : atom)) }))
    } catch (error) {
      // 409 版本冲突转换为 ConflictError，供 AtomDetail 捕获并提示
      if (error instanceof ApiError && error.status === 409) throw new ConflictError()
      throw error
    }
  },

  deleteAtom: async (id: string) => {
    const previousAtoms = get().atoms
    const previousLinks = get().links
    set((state) => ({
      atoms: state.atoms.filter((atom) => atom.id !== id),
      links: state.links.filter((link) => link.fromAtomId !== id && link.toAtomId !== id),
    }))
    try {
      await api.del(`/api/atoms/${id}`)
    } catch (error) {
      set({ atoms: previousAtoms, links: previousLinks })
      throw error
    }
  },

  confirmLink: async (id: string) => {
    // 乐观更新，失败不回滚（单用户场景下不会冲突）
    set((state) => ({
      links: state.links.map((link) =>
        link.id === id ? { ...link, userConfirmed: true, source: 'user' as const } : link,
      ),
    }))
    await api.post(`/api/links/${id}/confirm`)
  },

  ignoreLink: async (id: string) => {
    const previous = get().links
    set((state) => ({ links: state.links.filter((link) => link.id !== id) }))
    try {
      await api.post(`/api/links/${id}/ignore`)
    } catch {
      set({ links: previous })
    }
  },

  pushSuggestion: (link: LinkMock) => {
    set((state) => {
      if (state.links.some((item) => item.id === link.id)) return state
      return { links: [link, ...state.links] }
    })
  },

  removeAtomLocally: (id: string) => {
    set((state) => ({
      atoms: state.atoms.filter((atom) => atom.id !== id),
      links: state.links.filter((link) => link.fromAtomId !== id && link.toAtomId !== id),
    }))
  },

  setWsStatus: (wsStatus) => set({ wsStatus }),
}))
