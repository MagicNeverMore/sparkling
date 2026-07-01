import type { ToastItem } from './useToast'

interface Props {
  toasts: ToastItem[]
  onDismiss: (id: string) => void
}

const toneClass: Record<ToastItem['tone'], string> = {
  success: 'border-emerald-400/40 text-emerald-400',
  warning: 'border-amber-400/40 text-amber-400',
  error: 'border-rose-500/50 text-rose-400',
  info: 'border-violet-400/40 text-violet-400',
}

export default function Toast({ toasts, onDismiss }: Props) {
  return (
    <div className="fixed right-4 top-4 z-[60] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2">
      {toasts.map((toast) => (
        <button
          key={toast.id}
          type="button"
          onClick={() => onDismiss(toast.id)}
          className={`animate-suggestion-in rounded-xl border bg-white px-4 py-3 text-left text-sm shadow-xl dark:bg-slate-900 ${toneClass[toast.tone]}`}
        >
          {toast.message}
        </button>
      ))}
    </div>
  )
}
