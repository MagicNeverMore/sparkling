import { ArrowLeft, Check, Copy, ExternalLink } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useI18n } from '../../lib/I18nProvider'
import { api } from '../../lib/api'
import type { DeploymentSettings } from '../settings/deployment/types'

export default function YouTubeOAuthGuide() {
  const { t } = useI18n()
  const [copied, setCopied] = useState(false)
  const [deployment, setDeployment] = useState<DeploymentSettings | null>(null)
  const redirectUri = deployment?.youtube_callback_uri ?? ''

  useEffect(() => {
    void api.get<DeploymentSettings>('/api/settings/deployment').then(setDeployment)
  }, [])

  const copyRedirectUri = async () => {
    if (!redirectUri) return
    await navigator.clipboard.writeText(redirectUri)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 2000)
  }

  const steps = [
    {
      title: t('socialMedia.guide.step1Title'),
      body: t('socialMedia.guide.step1Body'),
      href: 'https://console.cloud.google.com/projectcreate',
      link: t('socialMedia.guide.openGoogleCloud'),
    },
    {
      title: t('socialMedia.guide.step2Title'),
      body: t('socialMedia.guide.step2Body'),
      href: 'https://console.cloud.google.com/apis/library',
      link: t('socialMedia.guide.openApiLibrary'),
    },
    {
      title: t('socialMedia.guide.step3Title'),
      body: t('socialMedia.guide.step3Body'),
      href: 'https://console.cloud.google.com/auth/overview',
      link: t('socialMedia.guide.openConsentScreen'),
    },
    {
      title: t('socialMedia.guide.step4Title'),
      body: t('socialMedia.guide.step4Body'),
      href: 'https://console.cloud.google.com/apis/credentials',
      link: t('socialMedia.guide.openCredentials'),
    },
    {
      title: t('socialMedia.guide.step5Title'),
      body: t('socialMedia.guide.step5Body'),
    },
    {
      title: t('socialMedia.guide.step6Title'),
      body: t('socialMedia.guide.step6Body'),
    },
  ]

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-6 md:px-6">
      <Link to="/settings?section=social-media" className="inline-flex items-center gap-2 text-sm text-slate-500 transition hover:text-violet-500">
        <ArrowLeft size={16} />{t('socialMedia.guide.back')}
      </Link>

      <header>
        <h1 className="text-2xl font-semibold text-slate-950 dark:text-slate-100">{t('socialMedia.guide.title')}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500 dark:text-slate-400">{t('socialMedia.guide.intro')}</p>
      </header>

      <section className="rounded-xl border border-violet-200 bg-violet-50 p-5 dark:border-violet-900/70 dark:bg-violet-950/30">
        <h2 className="text-sm font-medium text-violet-800 dark:text-violet-200">{t('socialMedia.guide.callbackTitle')}</h2>
        <p className="mt-1 text-xs leading-5 text-violet-700/80 dark:text-violet-300/80">{t('socialMedia.guide.callbackHelp')}</p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <code className="min-w-0 flex-1 overflow-x-auto rounded-md border border-violet-200 bg-white px-3 py-2 text-xs text-slate-700 dark:border-violet-900 dark:bg-slate-950 dark:text-slate-200">{redirectUri || t('settings.publicUrlRequired')}</code>
          <button type="button" onClick={() => void copyRedirectUri()} disabled={!redirectUri} className="inline-flex items-center justify-center gap-2 rounded-md bg-violet-500 px-3 py-2 text-sm font-medium text-white transition hover:bg-violet-400 disabled:cursor-not-allowed disabled:opacity-50">
            {copied ? <Check size={16} /> : <Copy size={16} />}
            {copied ? t('socialMedia.guide.copied') : t('socialMedia.guide.copy')}
          </button>
        </div>
        {!redirectUri && <Link to="/settings?section=deployment" className="mt-3 inline-block text-sm font-medium text-violet-700 underline dark:text-violet-300">{t('settings.configurePublicUrl')}</Link>}
      </section>

      <ol className="space-y-4">
        {steps.map((step, index) => (
          <li key={step.title} className="flex gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-violet-100 text-sm font-semibold text-violet-700 dark:bg-violet-950 dark:text-violet-300">{index + 1}</span>
            <div className="min-w-0">
              <h2 className="font-medium text-slate-900 dark:text-slate-100">{step.title}</h2>
              <p className="mt-1 text-sm leading-6 text-slate-500 dark:text-slate-400">{step.body}</p>
              {step.href && (
                <a href={step.href} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1.5 text-sm text-violet-500 hover:text-violet-400">
                  {step.link}<ExternalLink size={14} />
                </a>
              )}
            </div>
          </li>
        ))}
      </ol>

      <section className="rounded-xl border border-amber-200 bg-amber-50 p-5 dark:border-amber-900/70 dark:bg-amber-950/30">
        <h2 className="font-medium text-amber-900 dark:text-amber-200">{t('socialMedia.guide.troubleshooting')}</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-6 text-amber-800/80 dark:text-amber-300/80">
          <li>{t('socialMedia.guide.redirectMismatch')}</li>
          <li>{t('socialMedia.guide.accessDenied')}</li>
          <li>{t('socialMedia.guide.firstReport')}</li>
        </ul>
      </section>
    </div>
  )
}
