import type { AtomMock } from './mock'
import type { Lang } from './I18nProvider'

const localeFor = (lang: Lang) => (lang === 'zh' ? 'zh-CN' : 'en-US')

export const formatRelative = (iso: string, lang: Lang = 'zh') => {
  const rtf = new Intl.RelativeTimeFormat(localeFor(lang), { numeric: 'auto' })
  const diffMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 1) return lang === 'zh' ? '刚刚' : 'Just now'
  if (minutes < 60) return lang === 'zh' ? `${minutes} 分钟前` : `${minutes} minutes ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return rtf.format(-hours, 'hour')
  const days = Math.floor(hours / 24)
  if (days === 1) return lang === 'zh' ? '昨天' : 'Yesterday'
  if (days < 7) return lang === 'zh' ? `${days} 天前` : `${days} days ago`
  return new Intl.DateTimeFormat(localeFor(lang), { month: '2-digit', day: '2-digit' }).format(new Date(iso))
}

export const formatDateTime = (iso: string, lang: Lang = 'zh') =>
  new Intl.DateTimeFormat(localeFor(lang), {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso))

export const groupAtomTime = (iso: string, lang: Lang = 'zh') => {
  const diffMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 5) return lang === 'zh' ? '刚刚' : 'Just now'
  if (minutes < 60) return lang === 'zh' ? `${minutes} 分钟前` : `${minutes} minutes ago`
  const date = new Date(iso)
  const today = new Date()
  const yesterday = new Date()
  yesterday.setDate(today.getDate() - 1)
  if (date.toDateString() === today.toDateString()) return lang === 'zh' ? '今天' : 'Today'
  if (date.toDateString() === yesterday.toDateString()) return lang === 'zh' ? '昨天' : 'Yesterday'
  return date.toISOString().slice(0, 10)
}

export const groupAtomsByTime = (atoms: AtomMock[], lang: Lang = 'zh') =>
  [...atoms]
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
    .reduce<Record<string, AtomMock[]>>((groups, atom) => {
      const label = groupAtomTime(atom.createdAt, lang)
      groups[label] = [...(groups[label] ?? []), atom]
      return groups
    }, {})
