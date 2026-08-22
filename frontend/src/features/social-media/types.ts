export interface SocialMediaVideoBase {
  id: string
  external_video_id: string
  title: string
  published_at: string
  platform: string
  duration_seconds: number
}

export interface SocialMediaVideoMetric {
  video_id: string
  ctr: number | null
  average_view_duration_seconds: number | null
  average_view_percentage: number | null
  views: number
  subscribers_gained: number
  subscribers_lost: number
  net_subscribers: number
}

export type SocialMediaVideo = SocialMediaVideoBase & Omit<SocialMediaVideoMetric, 'video_id'>

export interface SocialMediaVideoListResponse {
  total: number
  items: SocialMediaVideoBase[]
}

export interface SocialMediaMetricListResponse {
  data_date: string | null
  updated_at: string | null
  items: SocialMediaVideoMetric[]
}

export interface SocialMediaMetricDateListResponse {
  items: string[]
}

export interface SocialMediaListResponse {
  data_date: string | null
  updated_at: string | null
  total: number
  items: SocialMediaVideo[]
}

export interface SocialMediaRun {
  id: string
  trigger: 'manual' | 'scheduled' | 'recovered'
  status: 'running' | 'done' | 'failed'
  metric_date: string | null
  video_count: number
  error: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export interface SocialMediaSyncRequest {
  task_id: string
  trigger: 'manual'
  status: 'queued'
}

export interface SocialMediaSettings {
  schedule_enabled: boolean
  update_frequency: 'hourly' | 'manual'
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
