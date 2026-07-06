import { useEffect, useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { useToast } from '../../components/useToast'
import { api, ApiError } from '../../lib/api'
import { useI18n } from '../../lib/I18nProvider'
import { formatDateTime } from '../../lib/time'
import type { TrendScheduleMode, TrendSettingsRaw } from './types'

const weekDays = [
  { value: 1, labelKey: 'settings.weekdayMon' },
  { value: 2, labelKey: 'settings.weekdayTue' },
  { value: 3, labelKey: 'settings.weekdayWed' },
  { value: 4, labelKey: 'settings.weekdayThu' },
  { value: 5, labelKey: 'settings.weekdayFri' },
  { value: 6, labelKey: 'settings.weekdaySat' },
  { value: 7, labelKey: 'settings.weekdaySun' },
]

export default function TrendSettingsSection() {
  const { lang, t } = useI18n()
  const { show } = useToast()
  const [brandPrompt, setBrandPrompt] = useState('')
  const [redditEnabled, setRedditEnabled] = useState(true)
  const [githubEnabled, setGithubEnabled] = useState(true)
  const [hackernewsEnabled, setHackernewsEnabled] = useState(true)
  const [googleEnabled, setGoogleEnabled] = useState(false)
  const [redditLimit, setRedditLimit] = useState(8)
  const [githubLimit, setGithubLimit] = useState(8)
  const [hackernewsLimit, setHackernewsLimit] = useState(8)
  const [googleLimit, setGoogleLimit] = useState(8)
  const [githubToken, setGithubToken] = useState('')
  const [githubTokenDirty, setGithubTokenDirty] = useState(false)
  const [githubTokenVisible, setGithubTokenVisible] = useState(false)
  const [githubTokenMasked, setGithubTokenMasked] = useState<string | null>(null)
  const [scoreThreshold, setScoreThreshold] = useState(70)
  const [resultLimit, setResultLimit] = useState(20)
  const [scheduleEnabled, setScheduleEnabled] = useState(false)
  const [scheduleMode, setScheduleMode] = useState<TrendScheduleMode>('weekly')
  const [scheduleDays, setScheduleDays] = useState<number[]>([1, 2, 3, 4, 5, 6, 7])
  const [scheduleIntervalHours, setScheduleIntervalHours] = useState(24)
  const [scheduleTime, setScheduleTime] = useState('09:00')
  const [lastRunAt, setLastRunAt] = useState<string | null>(null)
  const [nextRunAt, setNextRunAt] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const loadTrendSettings = () => {
    void api
      .get<TrendSettingsRaw>('/api/settings/trend')
      .then((s) => {
        setBrandPrompt(s.brand_prompt)
        setRedditEnabled(s.reddit_enabled)
        setGithubEnabled(s.github_enabled)
        setHackernewsEnabled(s.hackernews_enabled)
        setGoogleEnabled(s.google_enabled)
        setRedditLimit(s.reddit_limit)
        setGithubLimit(s.github_limit)
        setHackernewsLimit(s.hackernews_limit)
        setGoogleLimit(s.google_limit)
        setGithubToken(s.github_token ?? '')
        setGithubTokenDirty(false)
        setGithubTokenMasked(s.github_token_masked)
        setScoreThreshold(s.score_threshold)
        setResultLimit(s.result_limit)
        setScheduleEnabled(s.schedule_enabled)
        setScheduleMode(s.schedule_mode)
        setScheduleDays(s.schedule_days.length > 0 ? s.schedule_days : [1, 2, 3, 4, 5, 6, 7])
        setScheduleIntervalHours(s.schedule_interval_hours)
        setScheduleTime(s.schedule_time)
        setLastRunAt(s.last_run_at)
        setNextRunAt(s.next_run_at)
      })
      .catch((error) => {
        const message = error instanceof Error ? error.message : String(error)
        show(t('settings.readTrendFailed', { message }), 'error')
      })
  }

  useEffect(() => {
    loadTrendSettings()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const buildPayload = () => ({
    brand_prompt: brandPrompt || null,
    reddit_enabled: redditEnabled,
    github_enabled: githubEnabled,
    hackernews_enabled: hackernewsEnabled,
    google_enabled: googleEnabled,
    reddit_limit: redditLimit,
    github_limit: githubLimit,
    hackernews_limit: hackernewsLimit,
    google_limit: googleLimit,
    ...(githubTokenDirty ? { github_token: githubToken } : {}),
    score_threshold: scoreThreshold,
    result_limit: resultLimit,
    schedule_enabled: scheduleEnabled,
    schedule_mode: scheduleMode,
    schedule_days: scheduleDays,
    schedule_interval_hours: scheduleIntervalHours,
    schedule_time: scheduleTime,
  })

  const applySavedSettings = (s: TrendSettingsRaw) => {
    setGithubToken(s.github_token ?? '')
    setGithubTokenDirty(false)
    setGithubTokenMasked(s.github_token_masked)
    setScheduleMode(s.schedule_mode)
    setScheduleDays(s.schedule_days.length > 0 ? s.schedule_days : [1, 2, 3, 4, 5, 6, 7])
    setScheduleIntervalHours(s.schedule_interval_hours)
    setLastRunAt(s.last_run_at)
    setNextRunAt(s.next_run_at)
  }

  const saveSettings = async () => {
    setSaving(true)
    try {
      const saved = await api.put<TrendSettingsRaw>('/api/settings/trend', buildPayload())
      applySavedSettings(saved)
      show(t('settings.trendSaved'), 'success')
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(message, 'error')
    } finally {
      setSaving(false)
    }
  }

  const toggleDay = (day: number) => {
    setScheduleDays((current) => {
      const next = current.includes(day)
        ? current.filter((value) => value !== day)
        : [...current, day].sort((a, b) => a - b)
      return next.length > 0 ? next : current
    })
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
      <h1 className="text-lg font-semibold text-slate-950 dark:text-slate-100">{t('settings.trend')}</h1>
      <p className="mt-1 text-sm text-slate-500">{t('settings.trendDesc')}</p>

      <div className="mt-5 space-y-6">
        <label className="block text-sm text-slate-500 dark:text-slate-400">
          {t('settings.brandPrompt')}
          <textarea
            value={brandPrompt}
            onChange={(event) => setBrandPrompt(event.target.value)}
            placeholder={t('settings.brandPromptPlaceholder')}
            rows={5}
            className="mt-2 w-full resize-y rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-950 outline-none placeholder:text-slate-400 focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-600"
          />
        </label>

        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/50">
          <h2 className="text-sm font-medium text-emerald-400">{t('settings.trendSources')}</h2>
          <div className="mt-4 grid gap-3">
            <SourceRow label="Reddit" enabled={redditEnabled} onEnabled={setRedditEnabled} limit={redditLimit} onLimit={setRedditLimit} />
            <SourceRow label="GitHub" enabled={githubEnabled} onEnabled={setGithubEnabled} limit={githubLimit} onLimit={setGithubLimit} />
            <SourceRow label="Hacker News" enabled={hackernewsEnabled} onEnabled={setHackernewsEnabled} limit={hackernewsLimit} onLimit={setHackernewsLimit} />
            <SourceRow label="Google Search" enabled={googleEnabled} onEnabled={setGoogleEnabled} limit={googleLimit} onLimit={setGoogleLimit} disabledHint={t('settings.googleDisabledHint')} />
          </div>
          <label className="mt-4 block text-sm text-slate-500 dark:text-slate-400">
            GitHub Token
            <div className="relative mt-2">
              <input
                type={githubTokenVisible ? 'text' : 'password'}
                value={githubToken}
                onChange={(event) => {
                  setGithubToken(event.target.value)
                  setGithubTokenDirty(true)
                }}
                placeholder={githubTokenMasked ? t('settings.savedKey', { value: githubTokenMasked }) : t('settings.githubTokenPlaceholder')}
                className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 pr-11 text-slate-950 outline-none placeholder:text-slate-400 focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-600"
              />
              <button
                type="button"
                onClick={() => setGithubTokenVisible((value) => !value)}
                className="absolute right-2 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                aria-label={githubTokenVisible ? t('settings.hideKey') : t('settings.showKey')}
                title={githubTokenVisible ? t('settings.hideKey') : t('settings.showKey')}
              >
                {githubTokenVisible ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
              </button>
            </div>
          </label>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="block text-sm text-slate-500 dark:text-slate-400">
            <div className="mb-2 flex justify-between">
              <span>{t('settings.trendScoreThreshold')}</span>
              <span className="font-mono text-slate-950 dark:text-slate-100">{scoreThreshold.toFixed(0)}</span>
            </div>
            <input type="range" min="0" max="100" step="1" value={scoreThreshold} onChange={(event) => setScoreThreshold(Number(event.target.value))} className="w-full accent-violet-400" />
          </label>
          <label className="text-sm text-slate-500 dark:text-slate-400">
            {t('settings.trendResultLimit')}
            <input type="number" min={1} max={100} value={resultLimit} onChange={(event) => setResultLimit(Number(event.target.value))} className="mt-2 h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-slate-950 outline-none focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100" />
          </label>
        </div>

        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/50">
          <h2 className="text-sm font-medium text-amber-500">{t('settings.trendSchedule')}</h2>
          <div className="mt-4 space-y-4">
            <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
              <input type="checkbox" checked={scheduleEnabled} onChange={(event) => setScheduleEnabled(event.target.checked)} className="h-4 w-4 rounded border-slate-300 accent-violet-400" />
              {t('settings.scheduleEnabled')}
            </label>
            <div className="flex w-fit overflow-hidden rounded-md border border-slate-200 dark:border-slate-700">
              {(['weekly', 'interval'] as TrendScheduleMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setScheduleMode(mode)}
                  className={`px-3 py-2 text-sm transition ${
                    scheduleMode === mode
                      ? 'bg-violet-50 text-slate-950 dark:bg-slate-700 dark:text-slate-100'
                      : 'text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'
                  }`}
                >
                  {mode === 'weekly' ? t('settings.scheduleByWeekday') : t('settings.scheduleByInterval')}
                </button>
              ))}
            </div>
            {scheduleMode === 'weekly' ? (
              <div className="grid gap-4 md:grid-cols-[1fr_180px]">
                <div>
                  <div className="mb-2 text-sm text-slate-500">{t('settings.scheduleDays')}</div>
                  <div className="flex flex-wrap gap-2">
                    {weekDays.map((day) => (
                      <button
                        key={day.value}
                        type="button"
                        onClick={() => toggleDay(day.value)}
                        className={`rounded-md border px-3 py-1.5 text-sm transition ${
                          scheduleDays.includes(day.value)
                            ? 'border-violet-400 bg-violet-50 text-slate-950 dark:bg-slate-800 dark:text-slate-100'
                            : 'border-slate-200 text-slate-500 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800'
                        }`}
                      >
                        {t(day.labelKey)}
                      </button>
                    ))}
                  </div>
                </div>
                <label className="text-sm text-slate-500 dark:text-slate-400">
                  {t('settings.scheduleTime')}
                  <input type="time" value={scheduleTime} onChange={(event) => setScheduleTime(event.target.value)} className="mt-2 h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-slate-950 outline-none focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100" />
                </label>
              </div>
            ) : (
              <label className="block max-w-xs text-sm text-slate-500 dark:text-slate-400">
                {t('settings.scheduleIntervalHours')}
                <input type="number" min={1} max={720} value={scheduleIntervalHours} onChange={(event) => setScheduleIntervalHours(Number(event.target.value))} className="mt-2 h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-slate-950 outline-none focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100" />
              </label>
            )}
          </div>
          <div className="mt-3 grid gap-2 text-xs text-slate-500 md:grid-cols-2">
            <div>{t('settings.lastRun')}: {lastRunAt ? formatDateTime(lastRunAt, lang) : '-'}</div>
            <div>{t('settings.nextRun')}: {nextRunAt ? formatDateTime(nextRunAt, lang) : '-'}</div>
          </div>
        </div>

        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={saveSettings}
            disabled={saving}
            className="rounded-md bg-violet-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-violet-300 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
          >
            {saving ? t('common.processing') : t('settings.saveTrendSettings')}
          </button>
        </div>
      </div>
    </section>
  )
}

function SourceRow({
  label,
  enabled,
  onEnabled,
  limit,
  onLimit,
  disabledHint,
}: {
  label: string
  enabled: boolean
  onEnabled: (value: boolean) => void
  limit: number
  onLimit: (value: number) => void
  disabledHint?: string
}) {
  return (
    <div className="grid gap-3 rounded-md border border-slate-200 bg-white p-3 md:grid-cols-[1fr_120px] dark:border-slate-800 dark:bg-slate-950">
      <label className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
        <input type="checkbox" checked={enabled} onChange={(event) => onEnabled(event.target.checked)} className="mt-0.5 h-4 w-4 rounded border-slate-300 accent-violet-400" />
        <span>
          <span className="block font-medium text-slate-900 dark:text-slate-100">{label}</span>
          {disabledHint && <span className="mt-1 block text-xs leading-5 text-slate-500">{disabledHint}</span>}
        </span>
      </label>
      <label className="text-xs text-slate-500">
        Count
        <input type="number" min={1} max={50} value={limit} onChange={(event) => onLimit(Number(event.target.value))} className="mt-1 h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-950 outline-none focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100" />
      </label>
    </div>
  )
}
