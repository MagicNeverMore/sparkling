export type TrendRunStatus = 'pending' | 'running' | 'done' | 'failed'
export type TrendScheduleMode = 'weekly' | 'interval'

export interface TrendResource {
  title: string
  url: string
  source: string
}

export interface TrendItem {
  id: string
  title: string
  category: string | null
  score: number
  scoring_reason: string | null
  core_insight: string | null
  content: string | null
  tags: string[]
  resources: TrendResource[]
  first_seen_at: string
  last_seen_at: string
  is_favorited: boolean
  favorited_at: string | null
  created_at: string
  updated_at: string
}

export interface TrendListRaw {
  items: TrendItem[]
  total: number
}

export interface TrendRun {
  id: string
  trigger: string
  status: TrendRunStatus
  error: string | null
  candidate_count: number
  saved_count: number
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

export interface TrendSettingsRaw {
  brand_prompt: string
  llm_base_url: string | null
  llm_api_key: string | null
  llm_api_key_masked: string | null
  llm_model: string | null
  effective_llm_base_url: string | null
  effective_llm_model: string | null
  uses_chat_fallback: boolean
  github_enabled: boolean
  hackernews_enabled: boolean
  google_enabled: boolean
  github_limit: number
  hackernews_limit: number
  google_limit: number
  github_token: string | null
  github_token_masked: string | null
  score_threshold: number
  result_limit: number
  schedule_enabled: boolean
  schedule_mode: TrendScheduleMode
  schedule_days: number[]
  schedule_interval_hours: number
  schedule_time: string
  timezone: string
  last_run_at: string | null
  next_run_at: string | null
}

export interface TrendRssSource {
  id: string
  name: string
  url: string
  enabled: boolean
  item_limit: number
  created_at: string
  updated_at: string
}

export interface TrendRssTestResult {
  ok: boolean
  candidate_count: number
  message: string
  samples: Array<{
    title: string
    url: string
  }>
}
