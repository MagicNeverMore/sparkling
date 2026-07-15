import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Graph, GraphEvent, NodeEvent, CanvasEvent } from '@antv/g6'
import type { IElementEvent } from '@antv/g6'
import type { AtomMock, LinkMock } from '../../lib/mock'
import { useTheme } from '../../lib/ThemeProvider'
import { useI18n } from '../../lib/I18nProvider'

interface Props {
  atoms: AtomMock[]
  links: LinkMock[]
  selectedId?: string | null
  onNodeSelect?: (id: string | null) => void
}

type LayoutPhase = 'full' | 'incremental'

interface GraphPosition {
  x: number
  y: number
}

interface LabelMetrics {
  text: string
  footprintRadius: number
}

const LABEL_MAX_CHARS = 10
const LABEL_FONT_SIZE = 10
const LABEL_LINE_HEIGHT = 12
const LABEL_OFFSET_Y = 3
const LABEL_COLLISION_PADDING = 10
const GRAPH_PADDING = 72
const FULL_LAYOUT_ITERATIONS = 500
const INCREMENTAL_LAYOUT_ITERATIONS = 140

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
  return chars.length > LABEL_MAX_CHARS
    ? `${chars.slice(0, LABEL_MAX_CHARS).join('')}…`
    : chars.join('')
}

let labelMeasureContext: CanvasRenderingContext2D | null | undefined

const measureLabelWidth = (text: string): number => {
  if (labelMeasureContext === undefined) {
    labelMeasureContext = document.createElement('canvas').getContext('2d')
    if (labelMeasureContext) {
      labelMeasureContext.font = `${LABEL_FONT_SIZE}px system-ui, sans-serif`
    }
  }

  if (labelMeasureContext) return labelMeasureContext.measureText(text).width

  return Array.from(text).reduce((width, char) => (
    width + ((char.codePointAt(0) ?? 0) <= 0xff ? LABEL_FONT_SIZE * 0.58 : LABEL_FONT_SIZE)
  ), 0)
}

const getLabelMetrics = (content: string, degree: number): LabelMetrics => {
  const text = truncateLabel(content)
  const width = Math.max(measureLabelWidth(text), LABEL_FONT_SIZE)
  const dotRadius = getDotRadius(degree)
  const labelBottom = dotRadius + LABEL_OFFSET_Y + LABEL_LINE_HEIGHT
  const footprintRadius = Math.hypot(width / 2, labelBottom) + LABEL_COLLISION_PADDING

  return { text, footprintRadius }
}

const clamp = (value: number, min: number, max: number): number => (
  Math.min(Math.max(value, min), max)
)

const getStableJitter = (id: string): GraphPosition => {
  const hash = hashId(id)
  const angle = (hash % 360) * (Math.PI / 180)
  const radius = 48 + (hash % 36)
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius }
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
  const { resolved } = useTheme()
  const { t } = useI18n()
  const containerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<Graph | null>(null)
  const graphLifecycleRef = useRef(0)
  const graphTaskQueueRef = useRef<Promise<void>>(Promise.resolve())
  const topologySignatureRef = useRef<string | null>(null)
  const labelSignatureRef = useRef<string | null>(null)
  const manualPositionsRef = useRef(new Map<string, GraphPosition>())
  const draggingNodeIdsRef = useRef(new Set<string>())

  // Ref 存储最新布局信息，供 G6 初始化闭包中的样式和 force 回调使用
  const degreeMapRef = useRef(new Map<string, number>())
  const labelMetricsMapRef = useRef(new Map<string, LabelMetrics>())
  const edgeEndpointsRef = useRef(new Map<string, readonly [string, string]>())
  const onNodeSelectRef = useRef(onNodeSelect)
  const selectedIdRef = useRef(selectedId)
  const focusIdRef = useRef<string | null>(null)
  const hoveredIdRef = useRef<string | null>(null)
  const searchMatchIdRef = useRef<string | null>(null)
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
  const isDark = resolved === 'dark'

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
  useEffect(() => { focusIdRef.current = focusId }, [focusId])

  const labelMetricsMap = useMemo(() => new Map(
    atoms.map((atom) => [atom.id, getLabelMetrics(atom.content, degreeMap.get(atom.id) ?? 0)]),
  ), [atoms, degreeMap])

  const edgeEndpoints = useMemo(() => new Map(
    visibleLinks.map((link) => [link.id, [link.fromAtomId, link.toAtomId] as const]),
  ), [visibleLinks])

  const topologySignature = useMemo(() => {
    const nodeIds = atoms.map((atom) => atom.id).sort()
    const edges = visibleLinks
      .map((link) => `${link.id}:${link.fromAtomId}:${link.toAtomId}`)
      .sort()
    return `${nodeIds.join(',')}|${edges.join(',')}`
  }, [atoms, visibleLinks])

  const labelSignature = useMemo(() => atoms
    .map((atom) => `${atom.id}:${labelMetricsMap.get(atom.id)?.text ?? ''}`)
    .sort()
    .join('|'), [atoms, labelMetricsMap])

  useEffect(() => { labelMetricsMapRef.current = labelMetricsMap }, [labelMetricsMap])
  useEffect(() => { edgeEndpointsRef.current = edgeEndpoints }, [edgeEndpoints])

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

  const createLayoutOptions = useCallback((phase: LayoutPhase) => ({
    type: 'd3-force' as const,
    link: {
      distance: (edge: { id: unknown }) => {
        const endpoints = edgeEndpointsRef.current.get(String(edge.id))
        if (!endpoints) return 160
        const [sourceId, targetId] = endpoints
        const sourceRadius = labelMetricsMapRef.current.get(sourceId)?.footprintRadius ?? 48
        const targetRadius = labelMetricsMapRef.current.get(targetId)?.footprintRadius ?? 48
        return clamp(sourceRadius + targetRadius + 40, 140, 220)
      },
      strength: 0.72,
      iterations: 2,
    },
    manyBody: { strength: -170, distanceMin: 24 },
    x: { strength: 0.025 },
    y: { strength: 0.025 },
    collide: {
      radius: (node: { id: unknown }) => (
        labelMetricsMapRef.current.get(String(node.id))?.footprintRadius ?? 48
      ),
      strength: 1,
      iterations: 3,
    },
    alpha: phase === 'full' ? 1 : 0.32,
    alphaMin: phase === 'full' ? 0.001 : 0.04,
    velocityDecay: 0.42,
    iterations: phase === 'full' ? FULL_LAYOUT_ITERATIONS : INCREMENTAL_LAYOUT_ITERATIONS,
  }), [])

  const getCurrentPositions = useCallback((graph: Graph) => {
    const positions = new Map<string, GraphPosition>()
    if (graph.rendered) {
      graph.getNodeData().forEach((node) => {
        const x = Number(node.style?.x)
        const y = Number(node.style?.y)
        if (Number.isFinite(x) && Number.isFinite(y)) positions.set(String(node.id), { x, y })
      })
    }
    manualPositionsRef.current.forEach((position, id) => positions.set(id, position))
    return positions
  }, [])

  const restoreManualPositions = useCallback(async (graph: Graph) => {
    const updates = Array.from(manualPositionsRef.current, ([id, position]) => ({
      id,
      style: { x: position.x, y: position.y },
    })).filter(({ id }) => atoms.some((atom) => atom.id === id))
    if (updates.length === 0) return

    graph.updateNodeData(updates)
    await graph.draw()
  }, [atoms])

  const fitGraph = useCallback(async (graph: Graph, animation: boolean | { duration: number } = false) => {
    await graph.fitView({ when: 'always', direction: 'both' }, animation)
  }, [])

  // 初始化 G6 图实例（仅一次）
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const graphMount = document.createElement('div')
    graphMount.className = 'relative h-full w-full touch-none'
    container.appendChild(graphMount)

    const lifecycleId = graphLifecycleRef.current + 1
    graphLifecycleRef.current = lifecycleId
    graphTaskQueueRef.current = Promise.resolve()
    const draggingNodeIds = draggingNodeIdsRef.current

    const graph = new Graph({
      container: graphMount,
      autoResize: true,
      animation: false,
      padding: GRAPH_PADDING,
      background: isDark ? '#020617' : '#f8fafc',
      node: {
        type: 'circle',
        style: (d) => {
          const id = d.id as string
          const degree = degreeMapRef.current.get(id) ?? 0
          const r = getDotRadius(degree)
          const fill = getNodeFill(id, degree)
          const label = labelMetricsMapRef.current.get(id)?.text
            ?? truncateLabel((d.data?.content as string) ?? '')
          return {
            size: r * 2,
            fill,
            stroke: 'none',
            draggable: true,
            cursor: 'default',
            // 枢纽节点加软发光
            shadowColor: degree >= 6 ? fill : 'transparent',
            shadowBlur: degree >= 6 ? 8 : 0,
            // 标签
            labelText: draggingNodeIds.has(id) ? '' : label,
            labelPlacement: 'bottom' as const,
            labelOffsetY: LABEL_OFFSET_Y,
            labelFontSize: LABEL_FONT_SIZE,
            labelLineHeight: LABEL_LINE_HEIGHT,
            labelFill: isDark ? '#94a3b8' : '#475569',
            labelWordWrap: false,
            labelBackground: true,
            labelBackgroundFill: isDark ? '#020617' : '#f8fafc',
            labelBackgroundOpacity: 0.9,
            labelBackgroundRadius: 3,
            labelPadding: [2, 4, 2, 4],
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
          strokeOpacity: (d.data?.userConfirmed as boolean) ? 0.72 : 0.55,
          lineDash: (d.data?.userConfirmed as boolean) ? undefined : [4, 4],
          endArrow: false,
        }),
      },
      layout: createLayoutOptions('full'),
      behaviors: [
        'drag-canvas',
        'zoom-canvas',
        {
          type: 'auto-adapt-label',
          key: 'auto-labels',
          padding: 6,
          throttle: 50,
          sortNode: (a: { id: unknown }, b: { id: unknown }) => {
            const getPriority = (id: string) => {
              if (id === selectedIdRef.current) return 10_000
              if (id === hoveredIdRef.current) return 9_000
              if (id === searchMatchIdRef.current || id === focusIdRef.current) return 8_000
              return degreeMapRef.current.get(id) ?? 0
            }
            const aId = String(a.id)
            const bId = String(b.id)
            const difference = getPriority(bId) - getPriority(aId)
            if (difference !== 0) return difference < 0 ? -1 : 1
            return aId === bId ? 0 : aId < bId ? -1 : 1
          },
        },
        {
          type: 'fix-element-size',
          key: 'keep-readable',
          enable: true,
          node: [{ shape: 'key' }, { shape: 'label' }],
          edge: [{ shape: 'key', fields: ['lineWidth'] }],
        },
      ],
    })

    graphRef.current = graph
    isFirstRenderRef.current = true
    topologySignatureRef.current = null
    labelSignatureRef.current = null

    let activePointerDrag: {
      id: string
      startClientX: number
      startClientY: number
      startCanvasX: number
      startCanvasY: number
      startX: number
      startY: number
      x: number
      y: number
      started: boolean
    } | null = null
    let suppressClickUntil = 0
    let nativeMoveFrame: number | null = null
    let nativeDragIdleTimer: ReturnType<typeof setTimeout> | null = null
    let nativeDrawQueue = Promise.resolve()
    const manualLabelElements = new Map<string, HTMLDivElement>()

    const syncManualLabel = (id: string, position: GraphPosition) => {
      if (!isActiveGraph(graph, lifecycleId)) return
      let labelElement = manualLabelElements.get(id)
      if (!labelElement) {
        labelElement = document.createElement('div')
        labelElement.dataset.manualGraphLabel = id
        labelElement.className = 'pointer-events-none absolute whitespace-nowrap rounded px-1 py-0.5 text-[10px] leading-3'
        labelElement.style.zIndex = '2'
        graphMount.appendChild(labelElement)
        manualLabelElements.set(id, labelElement)
      }

      labelElement.textContent = labelMetricsMapRef.current.get(id)?.text ?? ''
      labelElement.style.color = isDark ? '#94a3b8' : '#475569'
      labelElement.style.background = isDark ? 'rgba(2, 6, 23, 0.9)' : 'rgba(248, 250, 252, 0.9)'
      const [clientX, clientY] = graph.getClientByCanvas([position.x, position.y])
      const rect = graphMount.getBoundingClientRect()
      const degree = degreeMapRef.current.get(id) ?? 0
      labelElement.style.left = `${clientX - rect.left}px`
      labelElement.style.top = `${clientY - rect.top + getDotRadius(degree) + LABEL_OFFSET_Y}px`
      labelElement.style.transform = 'translateX(-50%)'
    }

    const syncManualLabels = () => {
      manualPositionsRef.current.forEach((position, id) => syncManualLabel(id, position))
      manualLabelElements.forEach((element, id) => {
        if (manualPositionsRef.current.has(id)) return
        element.remove()
        manualLabelElements.delete(id)
      })
    }

    const queueNodeDraw = (id: string, position: GraphPosition) => {
      nativeDrawQueue = nativeDrawQueue
        .catch(() => undefined)
        .then(async () => {
          if (!isActiveGraph(graph, lifecycleId)) return
          draggingNodeIds.add(id)
          graph.updateNodeData([{
            id,
            style: { x: position.x, y: position.y, labelText: '' },
          }])
          await graph.draw()
          syncManualLabel(id, position)
        })
    }

    const flushNativePointerMove = () => {
      nativeMoveFrame = null
      if (!activePointerDrag) return
      queueNodeDraw(
        activePointerDrag.id,
        { x: activePointerDrag.x, y: activePointerDrag.y },
      )
    }

    const finishNativePointerDrag = () => {
      if (!activePointerDrag) return
      if (nativeDragIdleTimer) {
        clearTimeout(nativeDragIdleTimer)
        nativeDragIdleTimer = null
      }
      if (nativeMoveFrame !== null) {
        window.cancelAnimationFrame(nativeMoveFrame)
        flushNativePointerMove()
      }

      const completedDrag = activePointerDrag
      activePointerDrag = null
      if (!completedDrag.started) return

      const position = { x: completedDrag.x, y: completedDrag.y }
      manualPositionsRef.current.set(completedDrag.id, position)
      syncManualLabel(completedDrag.id, position)
    }

    // G6 5.1.1 的带 label node 在 translate stage 会触发 AABB 异常。
    // 这里精确更新 model，并用随 viewport 同步的 DOM label 保持拖动后的文字可读。
    const handleNativePointerMove = (event: PointerEvent) => {
      if (!activePointerDrag) return

      const totalDistance = Math.hypot(
        event.clientX - activePointerDrag.startClientX,
        event.clientY - activePointerDrag.startClientY,
      )
      if (totalDistance < 3) return

      suppressClickUntil = Date.now() + 300
      const [canvasX, canvasY] = graph.getCanvasByClient([event.clientX, event.clientY])
      activePointerDrag.x = activePointerDrag.startX
        + canvasX - activePointerDrag.startCanvasX
      activePointerDrag.y = activePointerDrag.startY
        + canvasY - activePointerDrag.startCanvasY

      activePointerDrag.started = true
      manualPositionsRef.current.set(activePointerDrag.id, {
        x: activePointerDrag.x,
        y: activePointerDrag.y,
      })
      if (nativeMoveFrame === null) {
        nativeMoveFrame = window.requestAnimationFrame(flushNativePointerMove)
      }
      if (nativeDragIdleTimer) clearTimeout(nativeDragIdleTimer)
      nativeDragIdleTimer = setTimeout(finishNativePointerDrag, 1000)
      event.preventDefault()
    }

    window.addEventListener('pointermove', handleNativePointerMove)
    window.addEventListener('pointerup', finishNativePointerDrag)
    window.addEventListener('pointercancel', finishNativePointerDrag)
    graph.on(GraphEvent.AFTER_TRANSFORM, syncManualLabels)
    graph.on(GraphEvent.AFTER_DRAW, syncManualLabels)

    // 点击节点：选中 + 进入聚焦候选
    graph.on(NodeEvent.CLICK, (e: IElementEvent) => {
      if (Date.now() < suppressClickUntil) return
      const id = (e.target as { id: string }).id
      setFocusId(id)
      onNodeSelectRef.current?.(id)
      clearTooltipTimer()
      setTooltip(null)
    })

    graph.on(NodeEvent.POINTER_DOWN, (e: IElementEvent) => {
      const event = e as unknown as {
        client: { x: number; y: number }
      }
      const id = (e.target as { id: string }).id
      const node = graph.getNodeData(id)
      const x = Number(node.style?.x)
      const y = Number(node.style?.y)
      if (!Number.isFinite(x) || !Number.isFinite(y)) return
      const [canvasX, canvasY] = graph.getCanvasByClient([event.client.x, event.client.y])
      activePointerDrag = {
        id,
        startClientX: event.client.x,
        startClientY: event.client.y,
        startCanvasX: canvasX,
        startCanvasY: canvasY,
        startX: x,
        startY: y,
        x,
        y,
        started: false,
      }
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
      if (Date.now() < suppressClickUntil) return
      onNodeSelectRef.current?.(null)
      clearTooltipTimer()
      setTooltip(null)
    })

    // Hover 1.5s 后显示简介
    graph.on(NodeEvent.POINTER_ENTER, (e: IElementEvent) => {
      clearTooltipTimer()
      const id = (e.target as { id: string }).id
      hoveredIdRef.current = id
      graph.updateBehavior({ key: 'auto-labels' })
      try {
        if (!isActiveGraph(graph, lifecycleId)) return
        const nodeData = graph.getNodeData(id)
        const rect = graphMount.getBoundingClientRect()
        // G6 的 FederatedPointerEvent 使用 client point 表示浏览器坐标
        const point = (e as unknown as { client?: { x: number; y: number } }).client
        const clientX = point?.x ?? 0
        const clientY = point?.y ?? 0
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
      hoveredIdRef.current = null
      graph.updateBehavior({ key: 'auto-labels' })
      clearTooltipTimer()
      setTooltip(null)
    })

    return () => {
      if (nativeMoveFrame !== null) window.cancelAnimationFrame(nativeMoveFrame)
      if (nativeDragIdleTimer) clearTimeout(nativeDragIdleTimer)
      draggingNodeIds.clear()
      manualLabelElements.forEach((element) => element.remove())
      manualLabelElements.clear()
      window.removeEventListener('pointermove', handleNativePointerMove)
      window.removeEventListener('pointerup', finishNativePointerDrag)
      window.removeEventListener('pointercancel', finishNativePointerDrag)
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
  }, [createLayoutOptions, isActiveGraph, isDark])

  // 数据变化时区分完整布局、增量布局和仅重绘，减少无意义的位置跳动
  useEffect(() => {
    runGraphTask(async (graph, lifecycleId) => {
      const isInitialLayout = !graph.rendered || topologySignatureRef.current === null
      const topologyChanged = topologySignatureRef.current !== topologySignature
      const labelFootprintChanged = labelSignatureRef.current !== labelSignature
      const shouldLayout = isInitialLayout || topologyChanged || labelFootprintChanged
      const previousPositions = getCurrentPositions(graph)
      const positionedNodes = new Map(previousPositions)
      const stableAtoms = [...atoms].sort((a, b) => a.id.localeCompare(b.id))
      const stableLinks = [...visibleLinks].sort((a, b) => a.id.localeCompare(b.id))

      const previousValues = Array.from(previousPositions.values())
      const graphCenter = previousValues.length > 0
        ? previousValues.reduce(
            (center, position) => ({ x: center.x + position.x, y: center.y + position.y }),
            { x: 0, y: 0 },
          )
        : { x: 0, y: 0 }
      if (previousValues.length > 0) {
        graphCenter.x /= previousValues.length
        graphCenter.y /= previousValues.length
      }

      const nodes = stableAtoms.map((atom) => {
        let position = positionedNodes.get(atom.id)

        if (!position && previousPositions.size > 0) {
          const neighborIds = stableLinks.flatMap((link) => {
            if (link.fromAtomId === atom.id) return [link.toAtomId]
            if (link.toAtomId === atom.id) return [link.fromAtomId]
            return []
          })
          const neighborPositions = neighborIds
            .map((id) => positionedNodes.get(id))
            .filter((value): value is GraphPosition => value !== undefined)
          const anchor = neighborPositions.length > 0
            ? neighborPositions.reduce(
                (center, value) => ({ x: center.x + value.x, y: center.y + value.y }),
                { x: 0, y: 0 },
              )
            : { ...graphCenter }
          if (neighborPositions.length > 0) {
            anchor.x /= neighborPositions.length
            anchor.y /= neighborPositions.length
          }
          const jitter = getStableJitter(atom.id)
          position = { x: anchor.x + jitter.x, y: anchor.y + jitter.y }
          positionedNodes.set(atom.id, position)
        }

        return {
          id: atom.id,
          data: { content: atom.content },
          ...(position ? { style: { x: position.x, y: position.y } } : {}),
        }
      })

      graph.setData({
        nodes,
        edges: stableLinks.map((l) => ({
          id: l.id,
          source: l.fromAtomId,
          target: l.toAtomId,
          data: { userConfirmed: l.userConfirmed, confidence: l.confidence },
        })),
      })

      if (shouldLayout) {
        graph.setLayout(createLayoutOptions(isInitialLayout ? 'full' : 'incremental'))
        await graph.render()
        if (!isActiveGraph(graph, lifecycleId)) return
        await restoreManualPositions(graph)
      } else {
        await graph.draw()
      }
      if (!isActiveGraph(graph, lifecycleId)) return

      if (isFirstRenderRef.current) {
        isFirstRenderRef.current = false
        await fitGraph(graph)
        if (!isActiveGraph(graph, lifecycleId)) return
      }
      const sid = selectedIdRef.current
      if (sid) await graph.setElementState(sid, ['selected'])

      topologySignatureRef.current = topologySignature
      labelSignatureRef.current = labelSignature
    })
  }, [
    atoms,
    visibleLinks,
    topologySignature,
    labelSignature,
    createLayoutOptions,
    fitGraph,
    getCurrentPositions,
    isActiveGraph,
    restoreManualPositions,
    runGraphTask,
  ])

  // selectedId 变化时更新 G6 状态
  useEffect(() => {
    runGraphTask(async (graph) => {
      if (!graph.rendered) return

      // 全量更新：先清除所有，再设置选中
      const stateMap: Record<string, string[]> = {}
      atoms.forEach((a) => { stateMap[a.id] = [] })
      if (selectedId && selectedId in stateMap) stateMap[selectedId] = ['selected']
      await graph.setElementState(stateMap)
      graph.updateBehavior({ key: 'auto-labels' })
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
    const match = q ? atoms.find((a) => a.content.toLowerCase().includes(q)) : undefined
    searchMatchIdRef.current = match?.id ?? null
    runGraphTask(async (graph) => {
      if (!graph.rendered) return
      graph.updateBehavior({ key: 'auto-labels' })
      if (match) await graph.focusElement(match.id, { duration: 400 })
    })
  }, [query, atoms, runGraphTask])

  return (
    <div className="relative h-full min-h-[calc(100vh-3rem)] bg-slate-50 md:min-h-screen dark:bg-slate-950">
      {/* G6 画布挂载点 */}
      <div ref={containerRef} className="h-full w-full" />
      {graphError && (
        <div className="absolute left-1/2 top-1/2 z-30 max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-rose-300 bg-white px-4 py-3 text-sm leading-6 text-rose-600 shadow-xl dark:border-rose-500/50 dark:bg-slate-950 dark:text-rose-200">
          {t('graph.renderFailed', { message: graphError })}
        </div>
      )}

      {/* 左上：视图控制 */}
      <div className="pointer-events-auto absolute left-4 top-4 z-20 flex items-center gap-2 rounded-xl border border-slate-200 bg-white/95 p-2 shadow-xl backdrop-blur dark:border-slate-800 dark:bg-slate-900/95">
        <div className="flex overflow-hidden rounded-md border border-slate-200 dark:border-slate-700">
          <button
            type="button"
            onClick={() => setMode('all')}
            className={`px-3 py-1.5 text-sm transition ${
              mode === 'all'
                ? 'bg-violet-50 text-slate-950 dark:bg-slate-700 dark:text-slate-100'
                : 'text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'
            }`}
          >
            {t('graph.all')}
          </button>
          <button
            type="button"
            onClick={() => { if (focusId) setMode('focus') }}
            title={!focusId ? t('graph.pickNodeFirst') : undefined}
            className={`border-l border-slate-200 px-3 py-1.5 text-sm transition dark:border-slate-700 ${
              mode === 'focus'
                ? 'bg-violet-50 text-slate-950 dark:bg-slate-700 dark:text-slate-100'
                : focusId
                  ? 'text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'
                  : 'cursor-not-allowed text-slate-400 dark:text-slate-600'
            }`}
          >
            {t('graph.focus')}
          </button>
        </div>
        <button
          type="button"
          onClick={() => {
            setMode('all')
            setFocusId(null)
            manualPositionsRef.current.clear()
            draggingNodeIdsRef.current.clear()
            containerRef.current
              ?.querySelectorAll('[data-manual-graph-label]')
              .forEach((element) => element.remove())
            runGraphTask(async (graph, lifecycleId) => {
              if (!graph.rendered) return
              await graph.layout(createLayoutOptions('full'))
              if (!isActiveGraph(graph, lifecycleId)) return
              await fitGraph(graph, { duration: 300 })
            })
          }}
          className="rounded-md px-3 py-1.5 text-sm text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
        >
          {t('graph.reset')}
        </button>
        <button
          type="button"
          onClick={() => {
            runGraphTask(async (graph) => {
              if (graph.rendered) await fitGraph(graph, { duration: 300 })
            })
          }}
          className="rounded-md px-3 py-1.5 text-sm text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
        >
          {t('graph.fit')}
        </button>
      </div>

      {/* 右上：搜索 */}
      <div className="pointer-events-auto absolute right-4 top-4 z-20 w-44">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('graph.searchPlaceholder')}
          className="w-full rounded-md border border-slate-200 bg-white/95 px-3 py-1.5 text-sm text-slate-950 outline-none backdrop-blur placeholder:text-slate-400 focus:border-violet-400 dark:border-slate-800 dark:bg-slate-900/95 dark:text-slate-100 dark:placeholder:text-slate-600"
        />
      </div>

      {/* Tooltip：渲染在 React 层，始终在 G6 画布上方 */}
      {tooltip && (
        <div
          className="pointer-events-none absolute z-50 w-56 rounded-xl border border-slate-200 bg-white p-3 text-xs leading-5 text-slate-700 shadow-2xl dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300"
          style={{
            left: tooltip.x,
            top: tooltip.y,
            transform: 'translate(-50%, calc(-100% - 12px))',
          }}
        >
          <div className="line-clamp-4">{tooltip.content}</div>
          <div className="mt-2 text-slate-500">{t('link.count', { count: tooltip.degree })}</div>
        </div>
      )}

      {/* 左下：图例 */}
      <div className="absolute bottom-4 left-4 z-20 space-y-2 rounded-xl border border-slate-200 bg-white/95 p-3 text-xs text-slate-500 shadow-xl backdrop-blur dark:border-slate-800 dark:bg-slate-900/95">
        <div className="flex items-center gap-2">
          <span className="inline-block h-2 w-2 rounded-full bg-slate-500" />
          <span>{t('graph.isolatedNode')}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-cyan-400" />
          <span>{t('graph.connectedNode')}</span>
        </div>
        <div className="mt-1 border-t border-slate-200 pt-2 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <svg width="20" height="2" viewBox="0 0 20 2" aria-hidden="true">
              <line x1="0" y1="1" x2="20" y2="1" stroke="#64748b" strokeWidth="1.5" />
            </svg>
            <span>{t('link.confirmedTitle')}</span>
          </div>
          <div className="mt-1.5 flex items-center gap-2">
            <svg width="20" height="2" viewBox="0 0 20 2" aria-hidden="true">
              <line x1="0" y1="1" x2="20" y2="1" stroke="#334155" strokeWidth="1" strokeDasharray="4 3" />
            </svg>
            <span>{t('link.aiSuggestedTitle')}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
