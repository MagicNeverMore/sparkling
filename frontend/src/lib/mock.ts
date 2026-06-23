// TODO(real-api): 整个文件由 lib/api.ts 真实调用替换；保留类型定义供组件使用
export interface AtomMock {
  id: string
  content: string
  status: 'inbox' | 'active' | 'archived'
  version: number
  createdAt: string
  updatedAt: string
}

export interface LinkMock {
  id: string
  fromAtomId: string
  toAtomId: string
  confidence: number
  source: 'ai_auto' | 'ai_suggested' | 'user'
  userConfirmed: boolean
}

export interface SearchResultMock {
  atom: AtomMock
  score: number
}

export class ConflictError extends Error {
  constructor(message = 'Version conflict') {
    super(message)
    this.name = 'ConflictError'
  }
}

const now = Date.now()
const minutes = (value: number) => new Date(now - value * 60_000).toISOString()
const hours = (value: number) => new Date(now - value * 60 * 60_000).toISOString()
const days = (value: number) => new Date(now - value * 24 * 60 * 60_000).toISOString()

let atomSeq = 16
let linkSeq = 21

const createAtom = (
  id: string,
  content: string,
  createdAt: string,
  status: AtomMock['status'] = 'inbox',
): AtomMock => ({
  id,
  content,
  status,
  version: 1,
  createdAt,
  updatedAt: createdAt,
})

let atoms: AtomMock[] = [
  createAtom('atom-01', '晨跑前 5 分钟动态热身，比直接开跑更容易找到节奏感。', minutes(1), 'active'),
  createAtom('atom-02', '低强度有氧最好保持在心率二区，能跑很久但还能完整说话。', minutes(7), 'active'),
  createAtom('atom-03', '配速不应该每天硬拉，轻松跑的意义是给身体留恢复空间。', minutes(18), 'active'),
  createAtom('atom-04', '出汗多的时候只补水不补电解质，后半程更容易头晕和脱水。', hours(2), 'active'),
  createAtom('atom-05', '晨跑让我一天更清醒，夜跑反而容易把神经系统激活到睡不着。', hours(5), 'active'),
  createAtom('atom-06', '番茄钟不是为了制造紧张感，而是给开始工作一个足够低的门槛。', hours(7), 'active'),
  createAtom('atom-07', 'Deep Work 的关键是提前定义清楚产出物，不然只是长时间坐在电脑前。', hours(9), 'active'),
  createAtom('atom-08', '上下文切换的成本比想象大，切出去一次就要重新加载任务状态。', days(1), 'active'),
  createAtom('atom-09', '专注力恢复需要真正离屏，刷短视频不是休息，是继续消耗注意力。', days(1), 'active'),
  createAtom('atom-10', '写作的肌肉记忆来自每天固定时间开一个空白文档，先写烂也没关系。', days(2), 'active'),
  createAtom('atom-11', '阅读速率不是越快越好，能复述核心问题才说明真的读进去了。', days(2), 'active'),
  createAtom('atom-12', '笔记复习最好隔几天回看一次，把当时的高亮改写成自己的判断。', days(3), 'active'),
  createAtom('atom-13', '咖啡机又开始漏水，可能是密封圈老化，需要周末拆开看看。', days(4)),
  createAtom('atom-14', '周末想去江边走走，顺便找一家安静的店整理下个月计划。', days(5)),
  createAtom('atom-15', '昨晚梦到老同学一起赶火车，醒来只记得站台特别亮。', days(6)),
]

let links: LinkMock[] = [
  { id: 'link-01', fromAtomId: 'atom-01', toAtomId: 'atom-02', confidence: 0.93, source: 'ai_auto', userConfirmed: true },
  { id: 'link-02', fromAtomId: 'atom-01', toAtomId: 'atom-03', confidence: 0.9, source: 'ai_auto', userConfirmed: true },
  { id: 'link-03', fromAtomId: 'atom-02', toAtomId: 'atom-03', confidence: 0.88, source: 'ai_auto', userConfirmed: true },
  { id: 'link-04', fromAtomId: 'atom-04', toAtomId: 'atom-05', confidence: 0.86, source: 'ai_auto', userConfirmed: true },
  { id: 'link-05', fromAtomId: 'atom-07', toAtomId: 'atom-08', confidence: 0.91, source: 'ai_auto', userConfirmed: true },
  { id: 'link-06', fromAtomId: 'atom-10', toAtomId: 'atom-12', confidence: 0.84, source: 'user', userConfirmed: true },
  { id: 'link-07', fromAtomId: 'atom-06', toAtomId: 'atom-07', confidence: 0.82, source: 'user', userConfirmed: true },
  { id: 'link-08', fromAtomId: 'atom-11', toAtomId: 'atom-12', confidence: 0.8, source: 'user', userConfirmed: true },
  { id: 'link-09', fromAtomId: 'atom-01', toAtomId: 'atom-04', confidence: 0.77, source: 'ai_suggested', userConfirmed: false },
  { id: 'link-10', fromAtomId: 'atom-02', toAtomId: 'atom-04', confidence: 0.74, source: 'ai_suggested', userConfirmed: false },
  { id: 'link-11', fromAtomId: 'atom-02', toAtomId: 'atom-05', confidence: 0.72, source: 'ai_suggested', userConfirmed: false },
  { id: 'link-12', fromAtomId: 'atom-03', toAtomId: 'atom-05', confidence: 0.69, source: 'ai_suggested', userConfirmed: false },
  { id: 'link-13', fromAtomId: 'atom-06', toAtomId: 'atom-08', confidence: 0.76, source: 'ai_suggested', userConfirmed: false },
  { id: 'link-14', fromAtomId: 'atom-06', toAtomId: 'atom-09', confidence: 0.73, source: 'ai_suggested', userConfirmed: false },
  { id: 'link-15', fromAtomId: 'atom-07', toAtomId: 'atom-09', confidence: 0.79, source: 'ai_suggested', userConfirmed: false },
  { id: 'link-16', fromAtomId: 'atom-08', toAtomId: 'atom-09', confidence: 0.83, source: 'ai_suggested', userConfirmed: false },
  { id: 'link-17', fromAtomId: 'atom-10', toAtomId: 'atom-11', confidence: 0.75, source: 'ai_suggested', userConfirmed: false },
  { id: 'link-18', fromAtomId: 'atom-05', toAtomId: 'atom-09', confidence: 0.66, source: 'ai_suggested', userConfirmed: false },
  { id: 'link-19', fromAtomId: 'atom-12', toAtomId: 'atom-14', confidence: 0.62, source: 'ai_suggested', userConfirmed: false },
  { id: 'link-20', fromAtomId: 'atom-08', toAtomId: 'atom-10', confidence: 0.68, source: 'ai_suggested', userConfirmed: false },
]

const delay = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))
const cloneAtoms = () => atoms.map((atom) => ({ ...atom }))
const cloneLinks = () => links.map((link) => ({ ...link }))

const normalize = (value: string) => value.trim().toLowerCase()

export const mockApi = {
  listAtoms: async () => {
    await delay(120)
    return cloneAtoms()
  },
  getAtom: async (id: string) => {
    await delay(80)
    const atom = atoms.find((item) => item.id === id)
    return atom ? { ...atom } : undefined
  },
  createAtom: async (content: string) => {
    await delay(140)
    const createdAt = new Date().toISOString()
    const atom = createAtom(`atom-${atomSeq++}`, content, createdAt)
    atoms = [atom, ...atoms]
    return { ...atom }
  },
  updateAtom: async (id: string, patch: Partial<AtomMock>, version: number) => {
    await delay(120)
    const atom = atoms.find((item) => item.id === id)
    if (!atom) return undefined
    if (atom.version !== version) throw new ConflictError()
    const updated: AtomMock = {
      ...atom,
      ...patch,
      id: atom.id,
      version: atom.version + 1,
      updatedAt: new Date().toISOString(),
    }
    atoms = atoms.map((item) => (item.id === id ? updated : item))
    return { ...updated }
  },
  listLinks: async () => {
    await delay(100)
    return cloneLinks()
  },
  confirmLink: async (id: string) => {
    await delay(90)
    const next = links.find((link) => link.id === id)
    if (!next) return undefined
    const confirmed: LinkMock = { ...next, userConfirmed: true, source: next.source === 'ai_suggested' ? 'user' : next.source }
    links = links.map((link) => (link.id === id ? confirmed : link))
    return { ...confirmed }
  },
  ignoreLink: async (id: string) => {
    await delay(90)
    links = links.filter((link) => link.id !== id)
  },
  search: async (q: string) => {
    await delay(120)
    const query = normalize(q)
    if (!query) return []
    const terms = query.split(/\s+/).filter(Boolean)
    const results = atoms
      .map((atom) => {
        const content = normalize(atom.content)
        const hits = terms.filter((term) => content.includes(term)).length
        const fuzzy = [...query].filter((char) => content.includes(char)).length / Math.max(query.length, 1)
        const score = Math.min(0.98, hits * 0.22 + fuzzy * 0.52 + (content.includes(query) ? 0.24 : 0))
        return { atom: { ...atom }, score }
      })
      .filter((result) => result.score >= 0.18)
      .sort((a, b) => b.score - a.score)
    return results
  },
}

export const createMockSuggestion = (): LinkMock | undefined => {
  const scattered = atoms.filter((atom) => ['atom-13', 'atom-14', 'atom-15'].includes(atom.id) || atom.id.startsWith('atom-'))
  const from = scattered[Math.floor(Math.random() * Math.min(scattered.length, 6))]
  const to = atoms[Math.floor(Math.random() * atoms.length)]
  if (!from || !to || from.id === to.id) return undefined
  const exists = links.some(
    (link) =>
      (link.fromAtomId === from.id && link.toAtomId === to.id) ||
      (link.fromAtomId === to.id && link.toAtomId === from.id),
  )
  if (exists) return undefined
  const link: LinkMock = {
    id: `link-${linkSeq++}`,
    fromAtomId: from.id,
    toAtomId: to.id,
    confidence: Number((0.62 + Math.random() * 0.2).toFixed(2)),
    source: 'ai_suggested',
    userConfirmed: false,
  }
  links = [link, ...links]
  return { ...link }
}
