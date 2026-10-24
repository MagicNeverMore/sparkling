import { format, isValid, parseISO } from 'date-fns'
import type { Topic } from './types'

export type TopicDateFilter = string | null
export const topicPublicationTime = (topic: Topic) => topic.published_at || topic.scheduled_at

export function topicPublicationDay(topic: Topic): string | null {
  const timestamp = topicPublicationTime(topic)
  if (!timestamp) return null
  const date = parseISO(timestamp)
  return isValid(date) ? format(date, 'yyyy-MM-dd') : null
}

export function filterTopicsByDay(topics: Topic[], day: TopicDateFilter): Topic[] {
  if (!day) return topics
  return topics.filter(topic => day === 'unscheduled' ? !topicPublicationDay(topic) : topicPublicationDay(topic) === day)
}

export function readTopicPageSize(): number {
  try {
    const size = Number(localStorage.getItem('sparkling-topic-page-size'))
    return [10, 20, 30].includes(size) ? size : 20
  } catch { return 20 }
}

export function rememberTopicPreference(key: string, value: string) {
  try { localStorage.setItem(key, value) } catch { /* 存储不可用时保留本次会话设置。 */ }
}
