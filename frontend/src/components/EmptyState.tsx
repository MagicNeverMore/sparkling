interface Props {
  icon?: string
  title: string
  description?: string
}

export default function EmptyState({ icon = '🌱', title, description }: Props) {
  return (
    <div className="flex min-h-56 flex-col items-center justify-center rounded-xl border border-dashed border-slate-800 bg-slate-900/50 p-6 text-center">
      <div className="text-4xl">{icon}</div>
      <div className="mt-3 text-sm font-medium text-slate-100">{title}</div>
      {description && <p className="mt-2 max-w-sm text-sm leading-6 text-slate-500">{description}</p>}
    </div>
  )
}
