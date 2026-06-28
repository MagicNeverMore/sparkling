import { useEffect, useMemo, useState } from 'react'
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from 'd3-force'
import ReactFlow, {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  Position,
  ReactFlowProvider,
  getStraightPath,
  useNodesState,
  useReactFlow,
  type Edge,
  type EdgeProps,
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
  highlight: boolean
}

interface LayoutNode extends SimulationNodeDatum {
  id: string
  content: string
  degree: number
}

interface LayoutLink extends SimulationLinkDatum<LayoutNode> {
  source: string
  target: string
  strength: number
}

const PILL_HEIGHT = 32
const FORCE_LINK_DISTANCE = 120
const FORCE_CHARGE_STRENGTH = -350

const truncateNodeContent = (content: string) => {
  const chars = Array.from(content.trim())
  return chars.length > 14 ? `${chars.slice(0, 14).join('')}…` : chars.join('')
}

const estimateRadius = (text: string, degree: number) => {
  const visibleChars = Math.min(Array.from(text.trim()).length, 14)
  const charWidth = degree >= 5 ? 15 : 13
  const estimatedWidth = visibleChars * charWidth + 24
  return Math.min(110, Math.max(50, estimatedWidth / 2))
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
  const pillClassName = data.highlight
    ? 'border-violet-300 bg-violet-400 text-slate-950 ring-2 ring-violet-400/40'
    : data.degree >= 5
      ? 'border-violet-400 bg-slate-900 text-violet-200'
      : 'border-slate-700 bg-slate-900 text-slate-200'

  return (
    <div className="group relative inline-flex">
      <Handle type="source" id="source-top" position={Position.Top} className="!h-2 !w-2 !border-0 !bg-transparent" />
      <Handle type="target" id="target-top" position={Position.Top} className="!h-2 !w-2 !border-0 !bg-transparent" />
      <Handle type="source" id="source-right" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-transparent" />
      <Handle type="target" id="target-right" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-transparent" />
      <Handle type="source" id="source-bottom" position={Position.Bottom} className="!h-2 !w-2 !border-0 !bg-transparent" />
      <Handle type="target" id="target-bottom" position={Position.Bottom} className="!h-2 !w-2 !border-0 !bg-transparent" />
      <Handle type="source" id="source-left" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-transparent" />
      <Handle type="target" id="target-left" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-transparent" />
      <div className={`inline-flex h-8 items-center whitespace-nowrap rounded-full border px-3 py-1.5 leading-none shadow-lg transition ${data.degree >= 5 ? 'text-sm' : 'text-xs'} ${pillClassName}`}>
        {truncateNodeContent(data.content)}
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

function SuggestedEdge({ id, sourceX, sourceY, targetX, targetY, data, style }: EdgeProps<{ confidence: number }>) {
  const [edgePath, labelX, labelY] = getStraightPath({ sourceX, sourceY, targetX, targetY })

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={style} />
      <EdgeLabelRenderer>
        <div
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          className="pointer-events-none absolute rounded border border-slate-800 bg-slate-950 px-1 py-0.5 text-[10px] text-violet-300/80"
        >
          {data?.confidence.toFixed(2)}
        </div>
      </EdgeLabelRenderer>
    </>
  )
}

const edgeTypes = { 'labeled-suggestion': SuggestedEdge }

function GraphInner({ atoms, links }: Props) {
  const flow = useReactFlow()
  const [nodes, setNodes, onNodesChange] = useNodesState<GraphNodeData>([])
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

  const layoutNodes = useMemo<Node<GraphNodeData>[]>(() => {
    const visible = new Set(visibleAtoms.map((atom) => atom.id))
    const layoutNodes: LayoutNode[] = visibleAtoms.map((atom) => ({
      id: atom.id,
      content: atom.content,
      degree: degreeMap.get(atom.id) ?? 0,
    }))
    const layoutLinks: LayoutLink[] = links
      .filter((link) => visible.has(link.fromAtomId) && visible.has(link.toAtomId))
      .map((link) => ({
        source: link.fromAtomId,
        target: link.toAtomId,
        strength: link.confidence,
      }))

    const sim = forceSimulation<LayoutNode>(layoutNodes)
      .force(
        'link',
        forceLink<LayoutNode, LayoutLink>(layoutLinks)
          .id((node) => node.id)
          .distance(FORCE_LINK_DISTANCE)
          .strength((link) => link.strength),
      )
      .force('charge', forceManyBody<LayoutNode>().strength(FORCE_CHARGE_STRENGTH))
      .force('center', forceCenter(0, 0))
      .force('collide', forceCollide<LayoutNode>((node) => estimateRadius(node.content, node.degree) + 16))
      .stop()

    for (let i = 0; i < 300; i += 1) sim.tick()

    const positionMap = new Map(layoutNodes.map((node) => [node.id, { x: node.x ?? 0, y: node.y ?? 0 }]))
    const q = query.trim().toLowerCase()
    return visibleAtoms.map((atom) => {
      const position = positionMap.get(atom.id) ?? { x: 0, y: 0 }
      const degree = degreeMap.get(atom.id) ?? 0
      const radius = estimateRadius(atom.content, degree)
      return {
        id: atom.id,
        type: 'thought',
        position: {
          x: position.x - radius,
          y: position.y - PILL_HEIGHT / 2,
        },
        data: {
          id: atom.id,
          content: atom.content,
          degree,
          highlight: atom.id === focusId || (q.length > 0 && atom.content.toLowerCase().includes(q)),
        },
      }
    })
  }, [degreeMap, focusId, links, query, visibleAtoms])

  const visibleAtomKey = useMemo(() => visibleAtoms.map((atom) => atom.id).join('|'), [visibleAtoms])

  useEffect(() => {
    setNodes((currentNodes) => {
      const currentById = new Map(currentNodes.map((node) => [node.id, node]))
      return layoutNodes.map((node) => {
        const current = currentById.get(node.id)
        if (!current) return node
        return {
          ...node,
          dragging: current.dragging,
          position: current.position,
          selected: current.selected,
        }
      })
    })
  }, [layoutNodes, setNodes])

  const edges = useMemo<Edge[]>(() => {
    const visible = new Set(visibleAtoms.map((atom) => atom.id))
    return links
      .filter((link) => visible.has(link.fromAtomId) && visible.has(link.toAtomId))
      .map((link) => ({
        id: link.id,
        source: link.fromAtomId,
        target: link.toAtomId,
        type: link.userConfirmed ? undefined : 'labeled-suggestion',
        animated: false,
        data: { confidence: link.confidence },
        style: {
          stroke: link.userConfirmed ? '#34d399' : '#a78bfa',
          strokeWidth: link.userConfirmed ? 1.5 + link.confidence * 1.5 : 1 + link.confidence * 1.5,
          strokeDasharray: link.userConfirmed ? undefined : '6 6',
        },
      }))
  }, [links, visibleAtoms])

  useEffect(() => {
    const q = query.trim().toLowerCase()
    if (!q) return
    const match = nodes.find((node) => node.data.content.toLowerCase().includes(q))
    if (!match) return
    void flow.setCenter(match.position.x + estimateRadius(match.data.content, match.data.degree), match.position.y + PILL_HEIGHT / 2, { zoom: 1.5, duration: 400 })
  }, [flow, nodes, query])

  useEffect(() => {
    if (nodes.length === 0) return undefined
    let secondFrame = 0
    const fitGraph = () => {
      void flow.fitView({ padding: 0.2, duration: 0 })
    }
    const firstFrame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(fitGraph)
    })
    const fallback = window.setTimeout(fitGraph, 120)
    return () => {
      window.cancelAnimationFrame(firstFrame)
      window.cancelAnimationFrame(secondFrame)
      window.clearTimeout(fallback)
    }
  }, [flow, nodes.length, visibleAtomKey])

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
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        minZoom={0.2}
        maxZoom={2}
        nodesDraggable
        nodesFocusable
        elementsSelectable
        onNodeClick={(_, node) => {
          setFocusId(node.id)
        }}
        onNodeDoubleClick={(_, node) => {
          setFocusId(node.id)
          setMode('focus')
        }}
      >
        <Background color="#334155" gap={24} />
        <Controls position="top-right" className="!border-slate-800 !bg-slate-900 !shadow-xl" />
      </ReactFlow>
      <div className="absolute bottom-4 right-4 z-20 space-y-1.5 rounded-xl border border-slate-800 bg-slate-900/95 p-3 text-xs text-slate-400 shadow-xl backdrop-blur">
        <div className="text-slate-300">图例</div>
        <div className="flex items-center gap-2">
          <svg width="24" height="2" viewBox="0 0 24 2" aria-hidden="true">
            <line x1="0" y1="1" x2="24" y2="1" stroke="#34d399" strokeWidth="2" />
          </svg>
          <span>已确认关联</span>
        </div>
        <div className="flex items-center gap-2">
          <svg width="24" height="2" viewBox="0 0 24 2" aria-hidden="true">
            <line x1="0" y1="1" x2="24" y2="1" stroke="#a78bfa" strokeWidth="2" strokeDasharray="4 4" />
          </svg>
          <span>AI 建议 (带相似度)</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full bg-violet-400 ring-2 ring-violet-400/30" />
          <span>枢纽（≥5 关联）</span>
        </div>
      </div>
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
