export type TopicStatus = 'not_started' | 'working' | 'published'

export interface TopicPublication {
  id: string
  platform: string
  social_media_video_id: string | null
  video_title: string | null
  external_video_id: string | null
}

export interface Topic {
  id: string
  title: string
  description: string | null
  category: string | null
  status: TopicStatus
  scheduled_at: string | null
  published_at: string | null
  cover_url: string | null
  task_id: string | null
  task_completed: boolean | null
  publications: TopicPublication[]
  created_at: string
  updated_at: string
}

export interface TopicListResponse {
  items: Topic[]
  categories: string[]
}

export interface SocialVideo {
  id: string
  title: string
  platform: string
  external_video_id: string
  published_at: string
}
