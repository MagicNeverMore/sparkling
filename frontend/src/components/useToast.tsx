import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import Toast from './Toast'
import { createClientId } from '../lib/id'

export interface ToastItem {
  id: string
  message: string
  tone: 'success' | 'warning' | 'error' | 'info'
}

interface ToastContextValue {
  show: (message: string, tone?: ToastItem['tone']) => void
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const dismiss = useCallback((id: string) => {
    setToasts((items) => items.filter((item) => item.id !== id))
  }, [])

  const show = useCallback(
    (message: string, tone: ToastItem['tone'] = 'info') => {
      const id = createClientId('toast')
      setToasts((items) => [...items, { id, message, tone }])
      window.setTimeout(() => dismiss(id), 3_000)
    },
    [dismiss],
  )

  const value = useMemo(() => ({ show }), [show])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <Toast toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  )
}

export const useToast = () => {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
