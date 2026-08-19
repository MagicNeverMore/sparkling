import { useCallback, useEffect, useState } from 'react'
import { Eye, EyeOff, Link2, Unlink } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../../../lib/api'
import { useI18n } from '../../../lib/I18nProvider'
import { useToast } from '../../../components/useToast'
import type { SocialMediaSettings } from '../types'

interface OAuthUrlResponse {
  authorization_url: string
}

export default function SocialMediaSettingsSection() {
  const { t } = useI18n()
  const { show } = useToast()
  const [searchParams] = useSearchParams()
  const oauthResult = searchParams.get('youtube')
  const [settings, setSettings] = useState<SocialMediaSettings | null>(null)
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [secretDirty, setSecretDirty] = useState(false)
  const [showSecret, setShowSecret] = useState(false)
  const [saving, setSaving] = useState(false)

  const apply = useCallback((value: SocialMediaSettings) => {
    setSettings(value)
    setClientId(value.youtube_client_id ?? '')
    setClientSecret('')
    setSecretDirty(false)
  }, [])

  const load = useCallback(() => {
    void api.get<SocialMediaSettings>('/api/social-media/settings').then(apply).catch((error) => {
      show(error instanceof Error ? error.message : String(error), 'error')
    })
  }, [apply, show])

  useEffect(load, [load])
  useEffect(() => {
    if (oauthResult === 'connected') show(t('socialMedia.oauthConnected'), 'success')
    if (oauthResult === 'error') show(t('socialMedia.oauthFailed'), 'error')
  }, [oauthResult, show, t])

  const save = async () => {
    if (!settings) return null
    setSaving(true)
    try {
      const payload: Record<string, unknown> = {
        schedule_enabled: settings.schedule_enabled,
        update_frequency: settings.update_frequency,
        youtube_client_id: clientId.trim() || null,
      }
      if (secretDirty) payload.youtube_client_secret = clientSecret
      const saved = await api.put<SocialMediaSettings>('/api/social-media/settings', payload)
      apply(saved)
      show(t('socialMedia.settingsSaved'), 'success')
      return saved
    } catch (error) {
      show(error instanceof Error ? error.message : String(error), 'error')
      return null
    } finally {
      setSaving(false)
    }
  }

  const connect = async () => {
    const saved = await save()
    if (!saved) return
    try {
      const result = await api.get<OAuthUrlResponse>('/api/social-media/youtube/oauth/start')
      window.location.assign(result.authorization_url)
    } catch (error) {
      show(error instanceof Error ? error.message : String(error), 'error')
    }
  }

  const disconnect = async () => {
    try {
      apply(await api.post<SocialMediaSettings>('/api/social-media/youtube/disconnect'))
      show(t('socialMedia.disconnected'), 'success')
    } catch (error) {
      show(error instanceof Error ? error.message : String(error), 'error')
    }
  }

  const localDateTime = (value: string | null) => value
    ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
    : '—'

  if (!settings) return <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900">{t('common.loading')}</div>

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
        <h1 className="text-lg font-semibold text-slate-950 dark:text-slate-100">{t('socialMedia.settingsTitle')}</h1>
        <p className="mt-1 text-sm text-slate-500">{t('socialMedia.settingsDesc')}</p>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
        <h2 className="font-medium text-slate-900 dark:text-slate-100">{t('socialMedia.updateSchedule')}</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <label className="flex items-center justify-between rounded-md border border-slate-200 px-3 py-2 text-sm dark:border-slate-800">
            {t('socialMedia.autoUpdate')}
            <input type="checkbox" checked={settings.schedule_enabled} onChange={(event) => setSettings({ ...settings, schedule_enabled: event.target.checked })} className="h-4 w-4 accent-violet-500" />
          </label>
          <label className="text-sm text-slate-500">
            {t('socialMedia.frequency')}
            <select value={settings.update_frequency} onChange={(event) => setSettings({ ...settings, update_frequency: event.target.value as SocialMediaSettings['update_frequency'] })} className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100">
              <option value="hourly">{t('socialMedia.hourly')}</option>
              <option value="manual">{t('socialMedia.manual')}</option>
            </select>
          </label>
        </div>
        <p className="mt-3 text-xs text-slate-500">{t('socialMedia.hourlyDailyHint')}</p>
        <label className="mt-4 block text-sm text-slate-500">
          {t('socialMedia.redirectUri')}
          <input readOnly value={`${window.location.origin}/api/social-media/youtube/oauth/callback`} className="mt-2 w-full rounded-md border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300" />
        </label>
        <div className="mt-4 grid gap-2 text-xs text-slate-500 md:grid-cols-2">
          <span>{t('socialMedia.lastRun')}: {localDateTime(settings.last_run_at)}</span>
          <span>{t('socialMedia.nextRun')}: {localDateTime(settings.next_run_at)}</span>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-medium text-slate-900 dark:text-slate-100">YouTube Connection</h2>
            <p className="mt-1 text-sm text-slate-500">{settings.youtube_connected ? settings.youtube_channel_title : t('socialMedia.notConnected')}</p>
            <Link to="/settings/social-media/youtube-oauth-guide" className="mt-2 inline-block text-sm text-violet-500 hover:text-violet-400">{t('socialMedia.guide.link')}</Link>
          </div>
          <span className={`rounded-full px-2.5 py-1 text-xs ${settings.youtube_connected ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300' : 'bg-slate-100 text-slate-500 dark:bg-slate-800'}`}>
            {settings.youtube_connected ? t('socialMedia.connected') : t('socialMedia.notConnected')}
          </span>
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <label className="text-sm text-slate-500">
            OAuth Client ID
            <input value={clientId} onChange={(event) => setClientId(event.target.value)} className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100" />
          </label>
          <label className="text-sm text-slate-500">
            OAuth Client Secret
            <div className="relative mt-2">
              <input type={showSecret ? 'text' : 'password'} value={clientSecret} onChange={(event) => { setClientSecret(event.target.value); setSecretDirty(true) }} placeholder={settings.youtube_client_secret_masked ?? ''} className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 pr-10 text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100" />
              <button type="button" onClick={() => setShowSecret((value) => !value)} className="absolute right-1 top-1/2 -translate-y-1/2 rounded p-2 text-slate-500">
                {showSecret ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </label>
        </div>
        <div className="mt-5 flex flex-wrap justify-end gap-3">
          <button type="button" onClick={() => void save()} disabled={saving} className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">{t('common.save')}</button>
          {settings.youtube_connected ? (
            <button type="button" onClick={() => void disconnect()} className="flex items-center gap-2 rounded-md border border-rose-300 px-4 py-2 text-sm text-rose-600 hover:bg-rose-50 dark:border-rose-900 dark:text-rose-300 dark:hover:bg-rose-950"><Unlink size={16} />{t('socialMedia.disconnect')}</button>
          ) : (
            <button type="button" onClick={() => void connect()} className="flex items-center gap-2 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500"><Link2 size={16} />{t('socialMedia.connectYouTube')}</button>
          )}
        </div>
      </section>
    </div>
  )
}
