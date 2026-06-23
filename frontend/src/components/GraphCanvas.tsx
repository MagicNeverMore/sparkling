import { useEffect, useMemo, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { Link } from 'react-router-dom'
import type { AtomMock, LinkMock } from '../lib/mock'

interface Props {
  atoms: AtomMock[]
  links: LinkMock[]
}

interface GraphNodeData {
  id: string
  content: string
  degree: number
  size: number
  highlight: boolean
}

const getLinkedAtomIds = (atomId: string, links: LinkMock[]) => {
  const ids = new Set<string>([atomId])
  links.forEach((link) => {
    if (link.fromAtomId === atomId) ids.add(link.toAtomId)
    if (link.toAtomId === atomId) ids.add(link.fromAtomId)
  })
  return ids
}

const getSecondDegreeIds = (atomId: string, links: LinkMock[]) => {
  const firstDegree = getLinkedAtomIds(atomId, links)
  const ids = new Set(firstDegree)
  firstDegree.forEach((id) => getLinkedAtomIds(id, links).forEach((linkedId) => ids.add(linkedId)))
  return ids
}

function ThoughtNode({ data }: NodeProps<GraphNodeData>) {
  return (
    <div className="group relative flex items-center justify-center">
      <div
        className={`flex items-center justify-center rounded-full border-2 bg-slate-900 p-3 text-center text-xs leading-5 shadow-xl transition ${
          data.highlight
            ? 'border-violet-400 text-violet-400 ring-2 ring-violet-400/40'
            : data.degree >= 5
              ? 'border-violet-400 text-slate-100'
              : 'border-slate-700 text-slate-100'
        }`}
        style={{ width: data.size, height: data.size }}
      >
        <span className="line-clamp-3">{data.content.slice(0, 20)}</span>
      </div>
      <div className="nodrag nopan pointer-events-auto absolute left-1/2 top-full z-30 mt-2 hidden w-64 -translate-x-1/2 rounded-xl border border-slate-800 bg-slate-950 p-3 text-left text-xs leading-5 text-slate-300 shadow-2xl group-hover:block">
        <div className="line-clamp-4">{data.content}</div>
        <div className="mt-2 text-slate-500">关联数 {data.degree}</div>
        <Link to={`/atoms/${data.id}`} className="mt-2 inline-flex text-violet-300 transition hover:text-violet-100">
          打开 →
        </Link>
      </div>
    </div>
  )
}

const nodeTypes = { thought: ThoughtNode }

function GraphInner({ atoms, links }: Props) {
  const flow = useReactFlow()
  const [mode, setMode] = useState<'all' | 'focus'>('all')
  const [focusId, setFocusId] = useState<string | null>(null)
  const [query, setQuery] = useState('')

  const visibleIds = useMemo(() => {
    if (mode !== 'focus' || !focusId) return new Set(atoms.map((atom) => atom.id))
    return getSecondDegreeIds(focusId, links)
  }, [atoms, focusId, links, mode])

  const degreeMap = useMemo(() => {
    const map = new Map<string, number>()
    links.forEach((link) => {
      map.set(link.fromAtomId, (map.get(link.fromAtomId) ?? 0) + 1)
      map.set(link.toAtomId, (map.get(link.toAtomId) ?? 0) + 1)
    })
    return map
  }, [links])

  const visibleAtoms = useMemo(() => atoms.filter((atom) => visibleIds.has(atom.id)), [atoms, visibleIds])

  const nodes = useMemo<Node<GraphNodeData>[]>(() => {
    const radius = Math.max(260, visibleAtoms.length * 42)
    const q = query.trim().toLowerCase()
    return visibleAtoms.map((atom, index) => {
      const angle = (Math.PI * 2 * index) / Math.max(visibleAtoms.length, 1)
      const degree = degreeMap.get(atom.id) ?? 0
      const size = Math.min(120, 64 + degree * 6)
      return {
        id: atom.id,
        type: 'thought',
        position: {
          x: Math.cos(angle) * radius + radius,
          y: Math.sin(angle) * radius + radius,
        },
        data: {
          id: atom.id,
          content: atom.content,
          degree,
          size,
          highlight: atom.id === focusId || (q.length > 0 && atom.content.toLowerCase().includes(q)),
        },
      }
    })
  }, [degreeMap, focusId, query, visibleAtoms])

  const edges = useMemo<Edge[]>(() => {
    const visible = new Set(visibleAtoms.map((atom) => atom.id))
    return links
      .filter((link) => visible.has(link.fromAtomId) && visible.has(link.toAtomId))
      .map((link) => ({
        id: link.id,
        source: link.fromAtomId,
        target: link.toAtomId,
        animated: !link.userConfirmed,
        style: {
          stroke: link.userConfirmed ? '#34d399' : '#a78bfa',
          strokeWidth: link.userConfirmed ? 2 : 1.5,
          strokeDasharray: link.userConfirmed ? undefined : '6 6',
        },
      }))
  }, [links, visibleAtoms])

  useEffect(() => {
    const q = query.trim().toLowerCase()
    if (!q) return
    const match = nodes.find((node) => node.data.content.toLowerCase().includes(q))
    if (!match) return
    const size = match.data.size
    void flow.setCenter(match.position.x + size / 2, match.position.y + size / 2, { zoom: 1.5, duration: 400 })
  }, [flow, nodes, query])

  const reset = () => {
    setMode('all')
    setFocusId(null)
    window.setTimeout(() => flow.fitView({ padding: 0.18, duration: 400 }), 0)
  }

  const selectMode = (nextMode: 'all' | 'focus') => {
    if (nextMode === 'focus' && !focusId) {
      setMode('all')
      return
    }
    setMode(nextMode)
  }

  return (
    <div className="relative h-full min-h-[calc(100vh-3rem)] bg-slate-950 md:min-h-screen">
      <div className="absolute left-4 top-4 z-20 flex flex-wrap items-center gap-2 rounded-xl border border-slate-800 bg-slate-900/95 p-2 shadow-xl backdrop-blur">
        <select
          value={mode}
          onChange={(event) => selectMode(event.target.value as 'all' | 'focus')}
          className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-violet-400"
        >
          <option value="all">全图 ▾</option>
          <option value="focus">聚焦</option>
          <option disabled>主题模式</option>
        </select>
        <button type="button" onClick={reset} className="rounded-md px-3 py-2 text-sm text-slate-400 transition hover:bg-slate-800 hover:text-slate-100">
          Reset
        </button>
        <button
          type="button"
          onClick={() => flow.fitView({ padding: 0.18, duration: 400 })}
          className="rounded-md px-3 py-2 text-sm text-slate-400 transition hover:bg-slate-800 hover:text-slate-100"
        >
          适应屏幕
        </button>
      </div>
      <div className="absolute right-4 top-4 z-20 w-[min(22rem,calc(100vw-2rem))]">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索节点"
          className="w-full rounded-md border border-slate-800 bg-slate-900/95 px-3 py-2 text-sm text-slate-100 outline-none backdrop-blur placeholder:text-slate-500 focus:border-violet-400"
        />
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.2}
        maxZoom={2}
        onNodeClick={(_, node) => {
          setFocusId(node.id)
        }}
        onNodeDoubleClick={(_, node) => {
          setFocusId(node.id)
          setMode('focus')
        }}
      >
        <Background color="#334155" gap={24} />
        <Controls className="!border-slate-800 !bg-slate-900 !shadow-xl" />
      </ReactFlow>
    </div>
  )
}

export default function GraphCanvas(props: Props) {
  return (
    <ReactFlowProvider>
      <GraphInner {...props} />
    </ReactFlowProvider>
  )
}
