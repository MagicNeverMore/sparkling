interface Props {
  status: 'online' | 'reconnecting' | 'offline'
  compact?: boolean
}

const config = {
  online: { label: '在线', dot: 'bg-emerald-400', text: 'text-emerald-400' },
  reconnecting: { label: '重连中', dot: 'bg-amber-400', text: 'text-amber-400' },
  offline: { label: '离线', dot: 'bg-slate-500', text: 'text-slate-500' },
}

export default function ConnectionDot({ status, compact = false }: Props) {
  const item = config[status]
  return (
    <span className="inline-flex items-center gap-2 text-xs">
      <span className={`h-2 w-2 rounded-full ${item.dot}`} />
      {!compact && <span className={item.text}>{item.label}</span>}
    </span>
  )
}
