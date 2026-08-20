import { Check, Copy, LocateFixed } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useToast } from '../../../components/useToast'
import { api } from '../../../lib/api'
import { useI18n } from '../../../lib/I18nProvider'
import type { DeploymentSettings } from './types'

export default function DeploymentSettingsSection() {
  const { t } = useI18n()
  const { show } = useToast()
  const [settings, setSettings] = useState<DeploymentSettings | null>(null)
  const [publicOrigin, setPublicOrigin] = useState('')
  const [saving, setSaving] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    void api.get<DeploymentSettings>('/api/settings/deployment').then((value) => {
      setSettings(value)
      setPublicOrigin(value.public_origin ?? '')
    }).catch((error) => {
      show(t('settings.deploymentLoadFailed', { message: error instanceof Error ? error.message : String(error) }), 'error')
    })
  }, [show, t])

  const draftOrigin = publicOrigin.trim().replace(/\/+$/, '')
  const savedOrigin = settings?.public_origin ?? ''
  const hasUnsavedChanges = draftOrigin !== savedOrigin
  const callbackUri = hasUnsavedChanges ? null : settings?.youtube_callback_uri ?? null
  const browserOriginMismatch = Boolean(draftOrigin && draftOrigin !== window.location.origin)

  const save = async () => {
    setSaving(true)
    try {
      const saved = await api.put<DeploymentSettings>('/api/settings/deployment', {
        public_origin: publicOrigin.trim() || null,
      })
      setSettings(saved)
      setPublicOrigin(saved.public_origin ?? '')
      show(t('settings.deploymentSaved'), 'success')
    } catch (error) {
      show(error instanceof Error ? error.message : String(error), 'error')
    } finally {
      setSaving(false)
    }
  }

  const copyCallback = async () => {
    if (!callbackUri) return
    await navigator.clipboard.writeText(callbackUri)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 2000)
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
      <h1 className="text-lg font-semibold text-slate-950 dark:text-slate-100">{t('settings.deployment')}</h1>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{t('settings.deploymentDesc')}</p>

      <label className="mt-5 block text-sm text-slate-500 dark:text-slate-400">
        {t('settings.publicUrl')}
        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <input
            type="url"
            value={publicOrigin}
            onChange={(event) => setPublicOrigin(event.target.value)}
            placeholder="https://example.com:8443"
            className="min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-3 py-2 font-mono text-sm text-slate-950 outline-none focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
          />
          <button type="button" onClick={() => setPublicOrigin(window.location.origin)} className="inline-flex items-center justify-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
            <LocateFixed size={16} />{t('settings.useBrowserOrigin')}
          </button>
        </div>
      </label>
      <p className="mt-2 text-xs text-slate-500">{t('settings.publicUrlHint')}</p>
      {browserOriginMismatch && <p className="mt-2 text-xs text-amber-600 dark:text-amber-300">{t('settings.originMismatch')}</p>}

      <div className="mt-5">
        <div className="text-sm text-slate-500 dark:text-slate-400">{t('socialMedia.redirectUri')}</div>
        <div className="mt-2 flex flex-col gap-2 sm:flex-row">
          <code className="min-w-0 flex-1 overflow-x-auto rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">{callbackUri ?? (hasUnsavedChanges ? t('settings.saveToGenerateCallback') : t('settings.publicUrlRequired'))}</code>
          <button type="button" onClick={() => void copyCallback()} disabled={!callbackUri} className="inline-flex items-center justify-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
            {copied ? <Check size={16} /> : <Copy size={16} />}{copied ? t('socialMedia.guide.copied') : t('socialMedia.guide.copy')}
          </button>
        </div>
      </div>

      <div className="mt-5 flex justify-end">
        <button type="button" onClick={() => void save()} disabled={saving} className="rounded-md bg-violet-400 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-violet-300 disabled:cursor-not-allowed disabled:opacity-50">
          {saving ? t('common.processing') : t('common.save')}
        </button>
      </div>
    </section>
  )
}
