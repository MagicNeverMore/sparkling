export interface SocialMediaVideo {
  id: string
  external_video_id: string
  title: string
  published_at: string
  platform: string
  ctr: number | null
  average_view_duration_seconds: number | null
  average_view_percentage: number | null
  duration_seconds: number
  views: number
  subscribers_gained: number
  subscribers_lost: number
  net_subscribers: number
}

export interface SocialMediaListResponse {
  metric_date: string | null
  collected_at: string | null
  total: number
  items: SocialMediaVideo[]
}

export interface SocialMediaRun {
  id: string
  trigger: 'manual' | 'scheduled'
  status: 'pending' | 'running' | 'done' | 'failed'
  metric_date: string | null
  video_count: number
  error: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export interface SocialMediaSettings {
  schedule_enabled: boolean
  update_frequency: 'daily' | 'weekly' | 'manual'
  schedule_time: string
  timezone: string
  youtube_client_id: string | null
  youtube_client_secret_masked: string | null
  youtube_connected: boolean
  youtube_channel_id: string | null
  youtube_channel_title: string | null
  last_run_at: string | null
  next_run_at: string | null
}
