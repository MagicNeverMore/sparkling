import type { ReactNode } from 'react'
import { useI18n } from '../lib/I18nProvider'

interface Props {
  open: boolean
  title: string
  children: ReactNode
  confirmLabel?: string
  confirming?: boolean
  onCancel: () => void
  onConfirm: () => void
}

export default function ConfirmDialog({ open, title, children, confirmLabel, confirming = false, onCancel, onConfirm }: Props) {
  const { t } = useI18n()
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-sm dark:bg-slate-950/70">
      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-4 shadow-2xl dark:border-slate-800 dark:bg-slate-900">
        <h2 className="text-base font-semibold text-slate-950 dark:text-slate-100">{title}</h2>
        <div className="mt-3 text-sm leading-6 text-slate-500 dark:text-slate-400">{children}</div>
        <div className="mt-5 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={confirming}
            className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-400 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:disabled:text-slate-500"
          >
            {t('common.cancel')}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={confirming}
            className="rounded-md bg-rose-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-rose-400 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
          >
            {confirming ? t('common.processing') : (confirmLabel ?? t('common.confirm'))}
          </button>
        </div>
      </div>
    </div>
  )
}
