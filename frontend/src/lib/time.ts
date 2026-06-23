import type { AtomMock } from './mock'

const rtf = new Intl.RelativeTimeFormat('zh-CN', { numeric: 'auto' })

export const formatRelative = (iso: string) => {
  const diffMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return rtf.format(-hours, 'hour')
  const days = Math.floor(hours / 24)
  if (days === 1) return '昨天'
  if (days < 7) return `${days} 天前`
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' }).format(new Date(iso))
}

export const formatDateTime = (iso: string) =>
  new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso))

export const groupAtomTime = (iso: string) => {
  const diffMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 5) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const date = new Date(iso)
  const today = new Date()
  const yesterday = new Date()
  yesterday.setDate(today.getDate() - 1)
  if (date.toDateString() === today.toDateString()) return '今天'
  if (date.toDateString() === yesterday.toDateString()) return '昨天'
  return date.toISOString().slice(0, 10)
}

export const groupAtomsByTime = (atoms: AtomMock[]) =>
  [...atoms]
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
    .reduce<Record<string, AtomMock[]>>((groups, atom) => {
      const label = groupAtomTime(atom.createdAt)
      groups[label] = [...(groups[label] ?? []), atom]
      return groups
    }, {})
