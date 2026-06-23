import { useEffect } from 'react'
import { createMockSuggestion } from './mock'
import { useSparklingStore } from './store'

const randomDelay = () => 8_000 + Math.floor(Math.random() * 7_000)

export const useMockWs = () => {
  const pushSuggestion = useSparklingStore((state) => state.pushSuggestion)
  const setWsStatus = useSparklingStore((state) => state.setWsStatus)

  useEffect(() => {
    let suggestionTimer: number | undefined
    const scheduleSuggestion = () => {
      suggestionTimer = window.setTimeout(() => {
        if (Math.random() < 0.3) {
          const link = createMockSuggestion()
          if (link) pushSuggestion(link)
        }
        scheduleSuggestion()
      }, randomDelay())
    }

    const statusTimer = window.setInterval(() => {
      setWsStatus('reconnecting')
      window.setTimeout(() => setWsStatus('online'), 1_000)
    }, 60_000)

    scheduleSuggestion()
    return () => {
      if (suggestionTimer) window.clearTimeout(suggestionTimer)
      window.clearInterval(statusTimer)
    }
  }, [pushSuggestion, setWsStatus])
}
