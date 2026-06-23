import { create } from 'zustand'
import { mockApi, type AtomMock, type LinkMock } from './mock'

interface State {
  atoms: AtomMock[]
  links: LinkMock[]
  loading: boolean
  wsStatus: 'online' | 'reconnecting' | 'offline'
  loadInitial: () => Promise<void>
  addAtom: (content: string) => Promise<void>
  updateAtom: (id: string, patch: Partial<AtomMock>) => Promise<void>
  confirmLink: (id: string) => Promise<void>
  ignoreLink: (id: string) => Promise<void>
  pushSuggestion: (link: LinkMock) => void
  setWsStatus: (status: State['wsStatus']) => void
}

export const useSparklingStore = create<State>((set, get) => ({
  atoms: [],
  links: [],
  loading: true,
  wsStatus: 'online',
  loadInitial: async () => {
    set({ loading: true })
    // TODO(real-api): replace mockApi calls with lib/api.ts requests.
    const [atoms, links] = await Promise.all([mockApi.listAtoms(), mockApi.listLinks()])
    set({ atoms, links, loading: false })
  },
  addAtom: async (content: string) => {
    const tempId = `temp-${crypto.randomUUID()}`
    const createdAt = new Date().toISOString()
    const optimistic: AtomMock = { id: tempId, content, status: 'inbox', version: 1, createdAt, updatedAt: createdAt }
    set((state) => ({ atoms: [optimistic, ...state.atoms] }))
    // TODO(real-api): POST /api/atoms and replace the optimistic row with the persisted atom.
    const created = await mockApi.createAtom(content)
    set((state) => ({ atoms: state.atoms.map((atom) => (atom.id === tempId ? created : atom)) }))
  },
  updateAtom: async (id: string, patch: Partial<AtomMock>) => {
    const current = get().atoms.find((atom) => atom.id === id)
    if (!current) return
    // TODO(real-api): PATCH /api/atoms/:id with optimistic-lock version.
    const updated = await mockApi.updateAtom(id, patch, current.version)
    if (!updated) return
    set((state) => ({ atoms: state.atoms.map((atom) => (atom.id === id ? updated : atom)) }))
  },
  confirmLink: async (id: string) => {
    set((state) => ({
      links: state.links.map((link) => (link.id === id ? { ...link, userConfirmed: true, source: 'user' } : link)),
    }))
    // TODO(real-api): POST /api/links/:id/confirm.
    await mockApi.confirmLink(id)
  },
  ignoreLink: async (id: string) => {
    const previous = get().links
    set((state) => ({ links: state.links.filter((link) => link.id !== id) }))
    // TODO(real-api): POST /api/links/:id/ignore.
    try {
      await mockApi.ignoreLink(id)
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
  setWsStatus: (wsStatus) => set({ wsStatus }),
}))
