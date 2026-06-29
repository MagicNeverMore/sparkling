import { useEffect, useRef } from 'react'
import type { LinkMock } from './mock'
import { useSparklingStore } from './store'

// 后端 link 事件的 data payload（snake_case）
interface LinkEventData {
  id: string
  from_atom_id: string
  to_atom_id: string
  confidence: number | null
  source: string
  user_confirmed: boolean
}

interface AtomDeletedEventData {
  id: string
}

const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`
const RECONNECT_DELAY = 3_000

export const useWs = () => {
  const pushSuggestion = useSparklingStore((state) => state.pushSuggestion)
  const removeAtomLocally = useSparklingStore((state) => state.removeAtomLocally)
  const setWsStatus = useSparklingStore((state) => state.setWsStatus)
  // useRef 保存 ws 实例和重连 timer，避免闭包陈旧引用
  const wsRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<number | undefined>(undefined)
  const destroyedRef = useRef(false)

  useEffect(() => {
    destroyedRef.current = false

    const connect = () => {
      if (destroyedRef.current) return
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        if (!destroyedRef.current) setWsStatus('online')
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data as string) as { type: string; data: unknown }
          // link.suggested 和 link.created（ai_auto 自动确认）都推送到 store
          if (msg.type === 'link.suggested' || msg.type === 'link.created') {
            const d = msg.data as LinkEventData
            const link: LinkMock = {
              id: d.id,
              fromAtomId: d.from_atom_id,
              toAtomId: d.to_atom_id,
              confidence: d.confidence ?? 0,
              source: d.source as LinkMock['source'],
              userConfirmed: d.user_confirmed,
            }
            pushSuggestion(link)
          } else if (msg.type === 'atom.deleted') {
            const d = msg.data as AtomDeletedEventData
            removeAtomLocally(d.id)
          }
        } catch {
          // 忽略非 JSON 消息
        }
      }

      ws.onclose = () => {
        if (destroyedRef.current) return
        setWsStatus('reconnecting')
        timerRef.current = window.setTimeout(connect, RECONNECT_DELAY)
      }

      ws.onerror = () => {
        // onerror 后 onclose 会自动触发，由 onclose 处理重连
        ws.close()
      }
    }

    connect()

    return () => {
      destroyedRef.current = true
      window.clearTimeout(timerRef.current)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [pushSuggestion, removeAtomLocally, setWsStatus])
}
