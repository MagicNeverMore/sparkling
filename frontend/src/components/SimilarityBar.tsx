interface Props {
  value: number
  compact?: boolean
}

export default function SimilarityBar({ value, compact = false }: Props) {
  const pct = Math.round(value * 100)
  return (
    <div className={`flex items-center gap-2 ${compact ? 'text-[11px]' : 'text-xs'} text-slate-500`}>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
        <div className="h-full rounded-full bg-violet-400" style={{ width: `${pct}%` }} />
      </div>
      <span className="w-9 text-right font-mono tabular-nums">{pct}%</span>
    </div>
  )
}
