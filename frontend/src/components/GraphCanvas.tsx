import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Graph, NodeEvent, CanvasEvent } from '@antv/g6'
import type { IElementEvent } from '@antv/g6'
import type { AtomMock, LinkMock } from '../lib/mock'

interface Props {
  atoms: AtomMock[]
  links: LinkMock[]
  selectedId?: string | null
  onNodeSelect?: (id: string | null) => void
}

// 多色调色板，颜色由 atom id hash 决定
const PALETTE = [
  '#22d3ee', // cyan
  '#60a5fa', // blue
  '#a78bfa', // violet
  '#f472b6', // pink
  '#fb923c', // orange
  '#facc15', // yellow
  '#34d399', // emerald
  '#f87171', // red
  '#a3e635', // lime
  '#2dd4bf', // teal
]

function hashId(id: string): number {
  return Array.from(id).reduce((acc, ch) => acc + ch.charCodeAt(0), 0)
}

function getDotRadius(degree: number): number {
  if (degree === 0) return 4
  if (degree === 1) return 5
  if (degree <= 3) return 6
  if (degree <= 6) return 8
  if (degree <= 10) return 11
  return 14
}

function getNodeFill(atomId: string, degree: number): string {
  if (degree === 0) return '#475569'
  return PALETTE[hashId(atomId) % PALETTE.length]
}

const truncateLabel = (content: string): string => {
  const chars = Array.from(content.trim())
  return chars.length > 10 ? `${chars.slice(0, 10).join('')}…` : chars.join('')
}

const getLinkedIds = (atomId: string, links: LinkMock[]) => {
  const ids = new Set<string>([atomId])
  links.forEach((l) => {
    if (l.fromAtomId === atomId) ids.add(l.toAtomId)
    if (l.toAtomId === atomId) ids.add(l.fromAtomId)
  })
  return ids
}

const getSecondDegreeIds = (atomId: string, links: LinkMock[]) => {
  const first = getLinkedIds(atomId, links)
  const ids = new Set(first)
  first.forEach((id) => getLinkedIds(id, links).forEach((sub) => ids.add(sub)))
  return ids
}

export default function GraphCanvas({ atoms, links, selectedId, onNodeSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<Graph | null>(null)
  const graphLifecycleRef = useRef(0)
  const graphTaskQueueRef = useRef<Promise<void>>(Promise.resolve())

  // Ref 存储最新的 degree map，供 G6 样式函数（在 init 闭包中）使用
  const degreeMapRef = useRef(new Map<string, number>())
  const onNodeSelectRef = useRef(onNodeSelect)
  const selectedIdRef = useRef(selectedId)
  const tooltipTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // 首次渲染标记，用于初始缩放处理
  const isFirstRenderRef = useRef(true)

  const [tooltip, setTooltip] = useState<{
    content: string
    degree: number
    x: number
    y: number
  } | null>(null)
  const [mode, setMode] = useState<'all' | 'focus'>('all')
  const [focusId, setFocusId] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [graphError, setGraphError] = useState<string | null>(null)

  const visibleLinks = useMemo(() => {
    const atomIds = new Set(atoms.map((atom) => atom.id))
    return links.filter((link) => atomIds.has(link.fromAtomId) && atomIds.has(link.toAtomId))
  }, [atoms, links])

  // 同步 refs
  useEffect(() => { onNodeSelectRef.current = onNodeSelect }, [onNodeSelect])
  useEffect(() => { selectedIdRef.current = selectedId }, [selectedId])

  // 计算每个节点的关联度
  const degreeMap = useMemo(() => {
    const map = new Map<string, number>()
    visibleLinks.forEach((l) => {
      map.set(l.fromAtomId, (map.get(l.fromAtomId) ?? 0) + 1)
      map.set(l.toAtomId, (map.get(l.toAtomId) ?? 0) + 1)
    })
    return map
  }, [visibleLinks])

  useEffect(() => { degreeMapRef.current = degreeMap }, [degreeMap])

  const clearTooltipTimer = () => {
    if (tooltipTimerRef.current) {
      clearTimeout(tooltipTimerRef.current)
      tooltipTimerRef.current = null
    }
  }

  const isActiveGraph = useCallback((graph: Graph, lifecycleId: number) => {
    return graphRef.current === graph && graphLifecycleRef.current === lifecycleId && !graph.destroyed
  }, [])

  const runGraphTask = useCallback((
    task: (graph: Graph, lifecycleId: number) => Promise<void> | void,
  ) => {
    const graph = graphRef.current
    const lifecycleId = graphLifecycleRef.current
    if (!graph || graph.destroyed) return

    graphTaskQueueRef.current = graphTaskQueueRef.current
      .catch(() => undefined)
      .then(async () => {
        if (!isActiveGraph(graph, lifecycleId)) return
        await task(graph, lifecycleId)
        setGraphError(null)
      })
      .catch((error) => {
        if (!isActiveGraph(graph, lifecycleId)) return
        const message = error instanceof Error ? error.message : String(error)
        setGraphError(message)
      })
  }, [isActiveGraph])

  // 初始化 G6 图实例（仅一次）
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const graphMount = document.createElement('div')
    graphMount.className = 'h-full w-full'
    container.appendChild(graphMount)

    const lifecycleId = graphLifecycleRef.current + 1
    graphLifecycleRef.current = lifecycleId
    graphTaskQueueRef.current = Promise.resolve()

    const graph = new Graph({
      container: graphMount,
      autoResize: true,
      animation: false,
      background: '#020617',
      node: {
        type: 'circle',
        style: (d) => {
          const id = d.id as string
          const degree = degreeMapRef.current.get(id) ?? 0
          const r = getDotRadius(degree)
          const fill = getNodeFill(id, degree)
          return {
            size: r * 2,
            fill,
            stroke: 'none',
            cursor: 'pointer',
            // 枢纽节点加软发光
            shadowColor: degree >= 6 ? fill : 'transparent',
            shadowBlur: degree >= 6 ? 8 : 0,
            // 标签
            labelText: truncateLabel((d.data?.content as string) ?? ''),
            labelPlacement: 'bottom' as const,
            labelOffsetY: 2,
            labelFontSize: 9,
            labelFill: '#475569',
            labelWordWrap: false,
          }
        },
        // 选中态：白色描边 + 紫色晕光
        state: {
          selected: {
            stroke: '#ffffff',
            lineWidth: 2.5,
            shadowColor: '#c084fc',
            shadowBlur: 14,
          },
        },
      },
      edge: {
        type: 'line',
        style: (d) => ({
          stroke: (d.data?.userConfirmed as boolean) ? '#64748b' : '#334155',
          lineWidth: (d.data?.userConfirmed as boolean) ? 1.5 : 1,
          lineDash: (d.data?.userConfirmed as boolean) ? undefined : [4, 4],
          endArrow: false,
        }),
      },
      layout: {
        type: 'd3-force',
        // d3-force 细粒度参数
        link: { distance: 80 },
        manyBody: { strength: -90 },
        x: { strength: 0.05 },
        y: { strength: 0.05 },
        // 碰撞半径随 degree 动态调整，大节点周围留出更多空间
        collide: {
          radius: (node: { id: unknown }) =>
            getDotRadius(degreeMapRef.current.get(node.id as string) ?? 0) + 24,
        },
        iterations: 300,
      },
      behaviors: ['drag-canvas', 'zoom-canvas', 'drag-element'],
    })

    graphRef.current = graph

    // 点击节点：选中 + 进入聚焦候选
    graph.on(NodeEvent.CLICK, (e: IElementEvent) => {
      const id = (e.target as { id: string }).id
      setFocusId(id)
      onNodeSelectRef.current?.(id)
      clearTooltipTimer()
      setTooltip(null)
    })

    // 双击节点：进入聚焦模式
    graph.on(NodeEvent.DBLCLICK, (e: IElementEvent) => {
      const id = (e.target as { id: string }).id
      setFocusId(id)
      setMode('focus')
      onNodeSelectRef.current?.(id)
      clearTooltipTimer()
      setTooltip(null)
    })

    // 点击画布空白：取消选中
    graph.on(CanvasEvent.CLICK, () => {
      onNodeSelectRef.current?.(null)
      clearTooltipTimer()
      setTooltip(null)
    })

    // Hover 1.5s 后显示简介
    graph.on(NodeEvent.POINTER_ENTER, (e: IElementEvent) => {
      clearTooltipTimer()
      const id = (e.target as { id: string }).id
      try {
        if (!isActiveGraph(graph, lifecycleId)) return
        const nodeData = graph.getNodeData(id)
        const rect = graphMount.getBoundingClientRect()
        // G6 的 FederatedPointerEvent 透传 clientX/clientY
        const clientX = (e as unknown as PointerEvent).clientX ?? 0
        const clientY = (e as unknown as PointerEvent).clientY ?? 0
        tooltipTimerRef.current = setTimeout(() => {
          if (!isActiveGraph(graph, lifecycleId)) return
          setTooltip({
            content: (nodeData.data?.content as string) ?? '',
            degree: degreeMapRef.current.get(id) ?? 0,
            x: clientX - rect.left,
            y: clientY - rect.top,
          })
        }, 1500)
      } catch {
        // 节点可能已不存在，忽略
      }
    })

    graph.on(NodeEvent.POINTER_LEAVE, () => {
      clearTooltipTimer()
      setTooltip(null)
    })

    return () => {
      clearTooltipTimer()
      graphLifecycleRef.current += 1
      if (graphRef.current === graph) graphRef.current = null
      const pendingTasks = graphTaskQueueRef.current
      void pendingTasks
        .catch(() => undefined)
        .finally(() => {
          if (!graph.destroyed) graph.destroy()
          graphMount.remove()
        })
    }
  }, [isActiveGraph])

  // 数据变化时更新图（re-render 重新布局）
  useEffect(() => {
    runGraphTask(async (graph, lifecycleId) => {
      graph.setData({
        nodes: atoms.map((a) => ({ id: a.id, data: { content: a.content } })),
        edges: visibleLinks.map((l) => ({
          id: l.id,
          source: l.fromAtomId,
          target: l.toAtomId,
          data: { userConfirmed: l.userConfirmed, confidence: l.confidence },
        })),
      })

      await graph.render()
      if (!isActiveGraph(graph, lifecycleId)) return

      if (isFirstRenderRef.current) {
        isFirstRenderRef.current = false
        // 先无动画 fitView，再无动画缩至 70%，一步到位不闪烁
        await graph.fitView(undefined, false)
        if (!isActiveGraph(graph, lifecycleId)) return
        const fitted = graph.getZoom()
        await graph.zoomTo(Math.max(fitted * 0.63, 0.15), false)
        if (!isActiveGraph(graph, lifecycleId)) return
      }
      const sid = selectedIdRef.current
      if (sid) await graph.setElementState(sid, ['selected'])
    })
  }, [atoms, visibleLinks, isActiveGraph, runGraphTask])

  // selectedId 变化时更新 G6 状态
  useEffect(() => {
    runGraphTask(async (graph) => {
      if (!graph.rendered) return

      // 全量更新：先清除所有，再设置选中
      const stateMap: Record<string, string[]> = {}
      atoms.forEach((a) => { stateMap[a.id] = [] })
      if (selectedId) stateMap[selectedId] = ['selected']
      await graph.setElementState(stateMap)
    })
  }, [selectedId, atoms, runGraphTask])

  // mode / focusId 变化：显示/隐藏节点和边
  useEffect(() => {
    runGraphTask(async (graph) => {
      if (!graph.rendered) return

      if (mode === 'all' || !focusId) {
        graph.updateNodeData(atoms.map((a) => ({ id: a.id, style: { visibility: 'visible' as const } })))
        graph.updateEdgeData(visibleLinks.map((l) => ({ id: l.id, style: { visibility: 'visible' as const } })))
      } else {
        const visibleNodeIds = getSecondDegreeIds(focusId, visibleLinks)
        const visibleEdgeIds = new Set(
          visibleLinks
            .filter((l) => visibleNodeIds.has(l.fromAtomId) && visibleNodeIds.has(l.toAtomId))
            .map((l) => l.id),
        )
        graph.updateNodeData(
          atoms.map((a) => ({
            id: a.id,
            style: { visibility: (visibleNodeIds.has(a.id) ? 'visible' : 'hidden') as 'visible' | 'hidden' },
          })),
        )
        graph.updateEdgeData(
          visibleLinks.map((l) => ({
            id: l.id,
            style: { visibility: (visibleEdgeIds.has(l.id) ? 'visible' : 'hidden') as 'visible' | 'hidden' },
          })),
        )
      }
      await graph.draw()
    })
  }, [mode, focusId, atoms, visibleLinks, runGraphTask])

  // 搜索：定位到第一个匹配节点
  useEffect(() => {
    const q = query.trim().toLowerCase()
    if (!q) return
    const match = atoms.find((a) => a.content.toLowerCase().includes(q))
    if (!match) return
    runGraphTask(async (graph) => {
      if (!graph.rendered) return
      await graph.focusElement(match.id, { duration: 400 })
    })
  }, [query, atoms, runGraphTask])

  return (
    <div className="relative h-full min-h-[calc(100vh-3rem)] bg-slate-950 md:min-h-screen">
      {/* G6 画布挂载点 */}
      <div ref={containerRef} className="h-full w-full" />
      {graphError && (
        <div className="absolute left-1/2 top-1/2 z-30 max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-rose-500/50 bg-slate-950 px-4 py-3 text-sm leading-6 text-rose-200 shadow-xl">
          图谱渲染失败：{graphError}
        </div>
      )}

      {/* 左上：视图控制 */}
      <div className="pointer-events-auto absolute left-4 top-4 z-20 flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-900/95 p-2 shadow-xl backdrop-blur">
        <div className="flex overflow-hidden rounded-md border border-slate-700">
          <button
            type="button"
            onClick={() => setMode('all')}
            className={`px-3 py-1.5 text-sm transition ${
              mode === 'all'
                ? 'bg-slate-700 text-slate-100'
                : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
            }`}
          >
            全图
          </button>
          <button
            type="button"
            onClick={() => { if (focusId) setMode('focus') }}
            title={!focusId ? '先单击一个节点' : undefined}
            className={`border-l border-slate-700 px-3 py-1.5 text-sm transition ${
              mode === 'focus'
                ? 'bg-slate-700 text-slate-100'
                : focusId
                  ? 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
                  : 'cursor-not-allowed text-slate-600'
            }`}
          >
            聚焦
          </button>
        </div>
        <button
          type="button"
          onClick={() => {
            setMode('all')
            setFocusId(null)
            runGraphTask(async (graph) => {
              if (graph.rendered) await graph.fitView()
            })
          }}
          className="rounded-md px-3 py-1.5 text-sm text-slate-400 transition hover:bg-slate-800 hover:text-slate-100"
        >
          重置
        </button>
        <button
          type="button"
          onClick={() => {
            runGraphTask(async (graph) => {
              if (graph.rendered) await graph.fitView()
            })
          }}
          className="rounded-md px-3 py-1.5 text-sm text-slate-400 transition hover:bg-slate-800 hover:text-slate-100"
        >
          适应
        </button>
      </div>

      {/* 右上：搜索 */}
      <div className="pointer-events-auto absolute right-4 top-4 z-20 w-44">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索节点…"
          className="w-full rounded-md border border-slate-800 bg-slate-900/95 px-3 py-1.5 text-sm text-slate-100 outline-none backdrop-blur placeholder:text-slate-600 focus:border-violet-400"
        />
      </div>

      {/* Tooltip：渲染在 React 层，始终在 G6 画布上方 */}
      {tooltip && (
        <div
          className="pointer-events-none absolute z-50 w-56 rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs leading-5 text-slate-300 shadow-2xl"
          style={{
            left: tooltip.x,
            top: tooltip.y,
            transform: 'translate(-50%, calc(-100% - 12px))',
          }}
        >
          <div className="line-clamp-4">{tooltip.content}</div>
          <div className="mt-2 text-slate-500">关联数 {tooltip.degree}</div>
        </div>
      )}

      {/* 左下：图例 */}
      <div className="absolute bottom-4 left-4 z-20 space-y-2 rounded-xl border border-slate-800 bg-slate-900/95 p-3 text-xs text-slate-500 shadow-xl backdrop-blur">
        <div className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full bg-slate-500" />
          <span>孤立节点</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-cyan-400" />
          <span>有关联（色由 id 决定）</span>
        </div>
        <div className="mt-1 border-t border-slate-800 pt-2">
          <div className="flex items-center gap-2">
            <svg width="20" height="2" viewBox="0 0 20 2" aria-hidden="true">
              <line x1="0" y1="1" x2="20" y2="1" stroke="#64748b" strokeWidth="1.5" />
            </svg>
            <span>已确认</span>
          </div>
          <div className="mt-1.5 flex items-center gap-2">
            <svg width="20" height="2" viewBox="0 0 20 2" aria-hidden="true">
              <line x1="0" y1="1" x2="20" y2="1" stroke="#334155" strokeWidth="1" strokeDasharray="4 3" />
            </svg>
            <span>AI 建议</span>
          </div>
        </div>
      </div>
    </div>
  )
}
