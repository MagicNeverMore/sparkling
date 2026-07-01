import { useI18n } from '../lib/I18nProvider'

interface Props {
  status: 'online' | 'reconnecting' | 'offline'
  compact?: boolean
}

const config = {
  online: { labelKey: 'ws.online', dot: 'bg-emerald-400', text: 'text-emerald-400' },
  reconnecting: { labelKey: 'ws.reconnecting', dot: 'bg-amber-400', text: 'text-amber-400' },
  offline: { labelKey: 'ws.offline', dot: 'bg-slate-500', text: 'text-slate-500' },
}

export default function ConnectionDot({ status, compact = false }: Props) {
  const { t } = useI18n()
  const item = config[status]
  return (
    <span className="inline-flex items-center gap-2 text-xs">
      <span className={`h-2 w-2 rounded-full ${item.dot}`} />
      {!compact && <span className={item.text}>{t(item.labelKey)}</span>}
    </span>
  )
}
