export interface DeploymentSettings {
  public_origin: string | null
  effective_origin: string | null
  youtube_callback_uri: string | null
  source: 'saved' | 'development' | 'unconfigured'
  restart_required: boolean
}
