import type { PerformanceRating } from './types'
import { performanceLabels } from './types'
const colors: Record<PerformanceRating, string> = {
  excellent: 'bg-emerald-100 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-950 dark:text-emerald-300',
  good: 'bg-blue-100 text-blue-800 ring-blue-600/20 dark:bg-blue-950 dark:text-blue-300',
  average: 'bg-amber-100 text-amber-800 ring-amber-600/20 dark:bg-amber-950 dark:text-amber-300',
  poor: 'bg-rose-100 text-rose-800 ring-rose-600/20 dark:bg-rose-950 dark:text-rose-300',
}

export default function PerformanceBadge({ rating }: { rating: PerformanceRating | null }) {
  if (!rating) return <span className="text-xs text-slate-400">待评价</span>
  return <span aria-label={`表现：${performanceLabels[rating]}`} className={`inline-flex min-w-8 items-center justify-center rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${colors[rating]}`}>{performanceLabels[rating]}</span>
}
