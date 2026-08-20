import { useEffect, useState, type ComponentType } from 'react'
import { Brain, Database, Eye, EyeOff, Globe2, Info, Share2, TrendingUp } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { useToast } from '../../components/useToast'
import { api, ApiError } from '../../lib/api'
import { useSparklingStore } from '../../lib/store'
import { useI18n } from '../../lib/I18nProvider'
import TrendSettingsSection from '../trend/TrendSettingsSection'
import type { TrendSettingsRaw } from '../trend/types'
import SocialMediaSettingsSection from '../social-media/settings/SocialMediaSettingsSection'
import DeploymentSettingsSection from './deployment/DeploymentSettingsSection'

const dims = [384, 512, 768, 1024, 1536, 2048, 2560, 3072, 4096]

type DatabaseBackend = 'sqlite' | 'postgresql'
type SettingsSection = 'database' | 'deployment' | 'ai' | 'trend' | 'social-media'

const settingsSections: SettingsSection[] = ['database', 'deployment', 'ai', 'trend', 'social-media']

interface DatabaseSettingsRaw {
  db_backend: DatabaseBackend
  db_path?: string | null
  postgresql_url?: string | null
  restart_required: boolean
}

interface SettingsRaw {
  embed_base_url: string | null
  embed_api_key: string | null
  embed_api_key_masked: string | null
  embed_model: string | null
  embed_dim: number | null
  embed_dim_locked: boolean
  embed_model_locked: boolean
  chat_base_url: string | null
  chat_api_key: string | null
  chat_api_key_masked: string | null
  chat_model: string | null
  link_threshold_auto: number
  link_threshold_suggest: number
}

interface TestProviderRaw {
  ok: boolean
  latency_ms: number
  error: string | null
}

interface EmbeddingStatusRaw {
  active_atoms: number
  embedded_atoms: number
  stale_atoms: number
  pending: number
  running: number
  failed: number
  last_error: string | null
}

interface SettingsNavItem {
  id: SettingsSection
  label: string
  Icon: ComponentType<{ size?: number; className?: string }>
}

export default function Settings() {
  const { t } = useI18n()
  const { show } = useToast()
  const [searchParams] = useSearchParams()
  const [activeSection, setActiveSection] = useState<SettingsSection>(() => {
    const requested = searchParams.get('section') as SettingsSection | null
    return requested && settingsSections.includes(requested) ? requested : 'database'
  })

  const [embedBaseUrl, setEmbedBaseUrl] = useState('https://api.openai.com/v1')
  const [embedApiKey, setEmbedApiKey] = useState('')
  const [embedApiKeyDirty, setEmbedApiKeyDirty] = useState(false)
  const [embedApiKeyVisible, setEmbedApiKeyVisible] = useState(false)
  const [embedApiKeyMasked, setEmbedApiKeyMasked] = useState<string | null>(null)
  const [embedModel, setEmbedModel] = useState('text-embedding-3-small')
  const [embedDim, setEmbedDim] = useState(1536)
  const [embedDimLocked, setEmbedDimLocked] = useState(false)
  const [embedModelLocked, setEmbedModelLocked] = useState(false)
  const [chatBaseUrl, setChatBaseUrl] = useState('https://api.openai.com/v1')
  const [chatApiKey, setChatApiKey] = useState('')
  const [chatApiKeyDirty, setChatApiKeyDirty] = useState(false)
  const [chatApiKeyVisible, setChatApiKeyVisible] = useState(false)
  const [chatApiKeyMasked, setChatApiKeyMasked] = useState<string | null>(null)
  const [chatModel, setChatModel] = useState('gpt-4.1-mini')
  const [trendBaseUrl, setTrendBaseUrl] = useState('')
  const [trendApiKey, setTrendApiKey] = useState('')
  const [trendApiKeyDirty, setTrendApiKeyDirty] = useState(false)
  const [trendApiKeyVisible, setTrendApiKeyVisible] = useState(false)
  const [trendApiKeyMasked, setTrendApiKeyMasked] = useState<string | null>(null)
  const [trendModel, setTrendModel] = useState('')
  const [trendUsesChatFallback, setTrendUsesChatFallback] = useState(true)
  const [effectiveTrendModel, setEffectiveTrendModel] = useState<string | null>(null)
  const [trendProviderSaving, setTrendProviderSaving] = useState(false)
  const [trendProviderTesting, setTrendProviderTesting] = useState(false)
  const [autoThreshold, setAutoThreshold] = useState(0.85)
  const [suggestThreshold, setSuggestThreshold] = useState(0.7)
  const [dbBackend, setDbBackend] = useState<DatabaseBackend>('sqlite')
  const [dbPath, setDbPath] = useState('./sparkling.db')
  const [postgresqlUrl, setPostgresqlUrl] = useState('')
  const [dbSaving, setDbSaving] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [dimEditing, setDimEditing] = useState(false)
  const [savedEmbedDim, setSavedEmbedDim] = useState(1536)
  const [savedEmbedModel, setSavedEmbedModel] = useState('text-embedding-3-small')
  const [retryingEmbeddings, setRetryingEmbeddings] = useState(false)
  const [embeddingStatus, setEmbeddingStatus] = useState<EmbeddingStatusRaw | null>(null)

  const loadInitial = useSparklingStore((state) => state.loadInitial)
  const thresholdsValid = autoThreshold >= suggestThreshold + 0.05
  const databaseValid = dbBackend === 'sqlite' ? dbPath.trim().length > 0 : postgresqlUrl.trim().length > 0
  const embeddingProgress = embeddingStatus?.active_atoms
    ? Math.round((embeddingStatus.embedded_atoms / embeddingStatus.active_atoms) * 100)
    : 0

  const navItems: SettingsNavItem[] = [
    { id: 'database', label: t('settings.database'), Icon: Database },
    { id: 'deployment', label: t('settings.deployment'), Icon: Globe2 },
    { id: 'ai', label: t('settings.aiProvider'), Icon: Brain },
    { id: 'trend', label: t('settings.trend'), Icon: TrendingUp },
    { id: 'social-media', label: t('socialMedia.settingsTitle'), Icon: Share2 },
  ]

  const loadAiSettings = () => {
    void api
      .get<SettingsRaw>('/api/settings')
      .then((s) => {
        setEmbedBaseUrl(s.embed_base_url ?? '')
        setEmbedApiKey(s.embed_api_key ?? '')
        setEmbedApiKeyDirty(false)
        setEmbedApiKeyMasked(s.embed_api_key_masked)
        setEmbedModel(s.embed_model ?? '')
        setEmbedDim(s.embed_dim ?? 1536)
        setEmbedDimLocked(s.embed_dim_locked)
        setEmbedModelLocked(s.embed_model_locked)
        setSavedEmbedModel(s.embed_model ?? '')
        setSavedEmbedDim(s.embed_dim ?? 1536)
        setChatBaseUrl(s.chat_base_url ?? '')
        setChatApiKey(s.chat_api_key ?? '')
        setChatApiKeyDirty(false)
        setChatApiKeyMasked(s.chat_api_key_masked)
        setChatModel(s.chat_model ?? '')
        if (s.link_threshold_auto !== undefined) setAutoThreshold(s.link_threshold_auto)
        if (s.link_threshold_suggest !== undefined) setSuggestThreshold(s.link_threshold_suggest)
      })
      .catch((error) => {
        const message = error instanceof Error ? error.message : String(error)
        show(t('settings.readAiFailed', { message }), 'error')
      })
  }

  const loadEmbeddingStatus = () => {
    void api
      .get<EmbeddingStatusRaw>('/api/settings/embedding-status')
      .then((status) => {
        setEmbeddingStatus(status)
        if (rebuilding && status.pending === 0 && status.running === 0) {
          setRebuilding(false)
          loadAiSettings()
          show(status.failed > 0 ? t('settings.embeddingDoneWithFailures') : t('settings.embeddingDone'), status.failed > 0 ? 'warning' : 'success')
        }
      })
      .catch(() => {
        setEmbeddingStatus(null)
      })
  }

  const applyTrendProviderSettings = (s: TrendSettingsRaw) => {
    setTrendBaseUrl(s.llm_base_url ?? '')
    setTrendApiKey(s.llm_api_key ?? '')
    setTrendApiKeyDirty(false)
    setTrendApiKeyMasked(s.llm_api_key_masked)
    setTrendModel(s.llm_model ?? '')
    setTrendUsesChatFallback(s.uses_chat_fallback)
    setEffectiveTrendModel(s.effective_llm_model)
  }

  const loadTrendProviderSettings = () => {
    void api
      .get<TrendSettingsRaw>('/api/settings/trend')
      .then(applyTrendProviderSettings)
      .catch((error) => {
        const message = error instanceof Error ? error.message : String(error)
        show(t('settings.readTrendFailed', { message }), 'error')
      })
  }

  useEffect(() => {
    loadAiSettings()
    loadEmbeddingStatus()
    loadTrendProviderSettings()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const timer = window.setInterval(loadEmbeddingStatus, 4000)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rebuilding])

  useEffect(() => {
    void api
      .get<DatabaseSettingsRaw>('/api/settings/database')
      .then((settings) => {
        setDbBackend(settings.db_backend)
        setDbPath(settings.db_path ?? './sparkling.db')
        setPostgresqlUrl(settings.postgresql_url ?? '')
      })
      .catch((error) => {
        const message = error instanceof Error ? error.message : String(error)
        show(t('settings.readDbFailed', { message }), 'error')
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const buildEmbedSettingsPayload = () => ({
    embed_base_url: embedBaseUrl || null,
    ...(embedApiKeyDirty ? { embed_api_key: embedApiKey } : {}),
    embed_model: embedModel || null,
    embed_dim: embedDim,
  })

  const buildChatSettingsPayload = () => ({
    chat_base_url: chatBaseUrl || null,
    ...(chatApiKeyDirty ? { chat_api_key: chatApiKey } : {}),
    chat_model: chatModel || null,
  })

  const buildTrendProviderPayload = () => ({
    llm_base_url: trendBaseUrl || null,
    ...(trendApiKeyDirty ? { llm_api_key: trendApiKey } : {}),
    llm_model: trendModel || null,
  })

  const saveEmbedSettings = async () => {
    if (embedDimLocked && embedDim !== savedEmbedDim) {
      chooseManualLinkResetAndRebuild()
      setDimEditing(false)
      return
    }
    const modelChanged = embedModel !== savedEmbedModel
    try {
      const s = await api.put<SettingsRaw>('/api/settings', buildEmbedSettingsPayload())
      if (s.embed_dim) setEmbedDim(s.embed_dim)
      setEmbedDimLocked(s.embed_dim_locked)
      setEmbedModelLocked(s.embed_model_locked)
      setSavedEmbedModel(s.embed_model ?? '')
      setSavedEmbedDim(s.embed_dim ?? embedDim)
      setDimEditing(false)
      setEmbedApiKey(s.embed_api_key ?? '')
      setEmbedApiKeyDirty(false)
      setEmbedApiKeyMasked(s.embed_api_key_masked)
      show(modelChanged ? t('settings.modelSavedRebuildSuggested') : t('settings.embedSaved'), modelChanged ? 'warning' : 'success')
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(message, 'error')
    }
  }

  const saveChatSettings = async () => {
    try {
      const s = await api.put<SettingsRaw>('/api/settings', buildChatSettingsPayload())
      setChatApiKey(s.chat_api_key ?? '')
      setChatApiKeyDirty(false)
      setChatApiKeyMasked(s.chat_api_key_masked)
      loadTrendProviderSettings()
      show(t('settings.chatSaved'), 'success')
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(message, 'error')
    }
  }

  const saveThresholds = async () => {
    try {
      await api.put<SettingsRaw>('/api/settings', {
        link_threshold_auto: autoThreshold,
        link_threshold_suggest: suggestThreshold,
      })
      await loadInitial()
      show(t('settings.thresholdSaved'), 'success')
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(message, 'error')
    }
  }

  const testEmbedConnection = async () => {
    try {
      await api.put<SettingsRaw>('/api/settings', buildEmbedSettingsPayload())
    } catch {
      // 保存失败也继续测试（可能 embed_dim 锁定等）
    }
    try {
      const r = await api.post<TestProviderRaw>('/api/settings/test-provider')
      if (r.ok) show(t('settings.embedConnected', { ms: r.latency_ms }), 'success')
      else show(t('settings.embedConnectFailed', { message: r.error ?? '' }), 'error')
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(t('settings.embedConnectFailed', { message }), 'error')
    }
  }

  const testChatConnection = async () => {
    try {
      await api.put<SettingsRaw>('/api/settings', buildChatSettingsPayload())
      loadTrendProviderSettings()
    } catch {
      // 保存失败也继续测试
    }
    try {
      const r = await api.post<TestProviderRaw>('/api/settings/test-chat-provider')
      if (r.ok) show(t('settings.chatConnected', { ms: r.latency_ms }), 'success')
      else show(t('settings.chatConnectFailed', { message: r.error ?? '' }), 'error')
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(t('settings.chatConnectFailed', { message }), 'error')
    }
  }

  const saveTrendProviderSettings = async () => {
    setTrendProviderSaving(true)
    try {
      const saved = await api.put<TrendSettingsRaw>('/api/settings/trend', buildTrendProviderPayload())
      applyTrendProviderSettings(saved)
      show(t('settings.trendSaved'), 'success')
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(message, 'error')
    } finally {
      setTrendProviderSaving(false)
    }
  }

  const testTrendConnection = async () => {
    setTrendProviderTesting(true)
    try {
      const saved = await api.put<TrendSettingsRaw>('/api/settings/trend', buildTrendProviderPayload())
      applyTrendProviderSettings(saved)
    } catch {
      // 保存失败也继续测试，后端会返回真实 provider 错误。
    }
    try {
      const r = await api.post<TestProviderRaw>('/api/settings/test-trend-provider')
      if (r.ok) show(t('settings.trendConnected', { ms: r.latency_ms }), 'success')
      else show(t('settings.trendConnectFailed', { message: r.error ?? '' }), 'error')
      loadTrendProviderSettings()
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(t('settings.trendConnectFailed', { message }), 'error')
    } finally {
      setTrendProviderTesting(false)
    }
  }

  const startRebuild = async (resetManualLinks: boolean) => {
    try {
      await api.post('/api/settings/rebuild-embeddings', {
        ...buildEmbedSettingsPayload(),
        reset_manual_links: resetManualLinks,
      })
      setRebuilding(true)
      setSavedEmbedDim(embedDim)
      setSavedEmbedModel(embedModel)
      loadEmbeddingStatus()
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(t('settings.rebuildFailed', { message }), 'error')
    }
  }

  const chooseManualLinkResetAndRebuild = () => {
    const resetManualLinks = window.confirm(t('settings.resetManualLinksConfirm'))
    void startRebuild(resetManualLinks)
  }

  const retryFailedEmbeddings = async () => {
    setRetryingEmbeddings(true)
    try {
      const result = await api.post<{ retried: number }>('/api/settings/retry-failed-embeddings')
      show(result.retried > 0 ? t('settings.retryResult', { count: result.retried }) : t('settings.noFailedTasks'), result.retried > 0 ? 'success' : 'info')
      loadEmbeddingStatus()
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(t('settings.retryFailed', { message }), 'error')
    } finally {
      setRetryingEmbeddings(false)
    }
  }

  const saveDatabaseSettings = async () => {
    if (!databaseValid) {
      show(dbBackend === 'sqlite' ? t('settings.dbPathRequired') : t('settings.postgresqlRequired'), 'warning')
      return
    }

    setDbSaving(true)
    try {
      const next = await api.put<DatabaseSettingsRaw>('/api/settings/database', {
        db_backend: dbBackend,
        db_path: dbPath.trim(),
        postgresql_url: postgresqlUrl.trim(),
      })
      setDbBackend(next.db_backend)
      setDbPath(next.db_path ?? './sparkling.db')
      setPostgresqlUrl(next.postgresql_url ?? '')
      await loadInitial()
      loadAiSettings()
      loadEmbeddingStatus()
      loadTrendProviderSettings()
      show(t('settings.dbSaved'), 'success')
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(message, 'error')
    } finally {
      setDbSaving(false)
    }
  }

  return (
    <div className="mx-auto grid max-w-6xl gap-6 px-4 py-6 md:grid-cols-[190px_1fr] md:px-6">
      <aside className="md:sticky md:top-6 md:self-start">
        <nav className="grid grid-cols-2 gap-2 md:grid-cols-1">
          {navItems.map(({ id, label, Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => setActiveSection(id)}
              className={`flex items-center gap-2 rounded-md border px-3 py-2 text-left text-sm transition ${
                activeSection === id
                  ? 'border-violet-300 bg-violet-50 text-slate-950 dark:border-violet-500/50 dark:bg-slate-900 dark:text-slate-100'
                  : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50 hover:text-slate-950 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100'
              }`}
            >
              <Icon size={16} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
      </aside>

      <div className="min-w-0 space-y-6">
        {activeSection === 'deployment' && <DeploymentSettingsSection />}
        {activeSection === 'database' && (
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
            <h1 className="text-lg font-semibold text-slate-950 dark:text-slate-100">{t('settings.database')}</h1>
            <div className="mt-4 flex w-fit overflow-hidden rounded-md border border-slate-200 dark:border-slate-700">
              <button
                type="button"
                onClick={() => setDbBackend('sqlite')}
                className={`px-4 py-2 text-sm transition ${
                  dbBackend === 'sqlite'
                    ? 'bg-violet-50 text-slate-950 dark:bg-slate-700 dark:text-slate-100'
                    : 'text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'
                }`}
              >
                SQLite
              </button>
              <button
                type="button"
                onClick={() => setDbBackend('postgresql')}
                className={`border-l border-slate-200 px-4 py-2 text-sm transition dark:border-slate-700 ${
                  dbBackend === 'postgresql'
                    ? 'bg-violet-50 text-slate-950 dark:bg-slate-700 dark:text-slate-100'
                    : 'text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'
                }`}
              >
                PostgreSQL
              </button>
            </div>

            <div className="mt-4 grid gap-4">
              {dbBackend === 'sqlite' ? (
                <label className="text-sm text-slate-500 dark:text-slate-400">
                  {t('settings.sqlitePath')}
                  <input
                    value={dbPath}
                    onChange={(event) => setDbPath(event.target.value)}
                    className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 font-mono text-sm text-slate-950 outline-none focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
                  />
                </label>
              ) : (
                <label className="text-sm text-slate-500 dark:text-slate-400">
                  {t('settings.postgresqlUrl')}
                  <input
                    value={postgresqlUrl}
                    onChange={(event) => setPostgresqlUrl(event.target.value)}
                    placeholder="postgresql://user:password@localhost:5432/sparkling"
                    className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 font-mono text-sm text-slate-950 outline-none focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
                  />
                </label>
              )}
            </div>

            <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400">
              {t('settings.dbHint')}
            </div>

            <div className="mt-5 flex justify-end">
              <button
                type="button"
                disabled={!databaseValid || dbSaving}
                onClick={() => void saveDatabaseSettings()}
                className="rounded-md bg-violet-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-violet-300 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
              >
                {dbSaving ? t('settings.switching') : t('settings.switchDatabase')}
              </button>
            </div>
          </section>
        )}

        {activeSection === 'ai' && (
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
            <h1 className="text-lg font-semibold text-slate-950 dark:text-slate-100">{t('settings.aiProvider')}</h1>

            <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/50">
              <h2 className="text-sm font-medium text-violet-400">Embedding</h2>
              <p className="mt-1 text-xs text-slate-500">{t('settings.embedDesc')}</p>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="text-sm text-slate-500 dark:text-slate-400">
                  Base URL
                  <input value={embedBaseUrl} onChange={(event) => setEmbedBaseUrl(event.target.value)} placeholder="https://api.openai.com/v1" className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-slate-950 outline-none placeholder:text-slate-400 focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-600" />
                </label>
                <label className="text-sm text-slate-500 dark:text-slate-400">
                  API Key
                  <div className="relative mt-2">
                    <input
                      type={embedApiKeyVisible ? 'text' : 'password'}
                      value={embedApiKey}
                      onChange={(event) => {
                        setEmbedApiKey(event.target.value)
                        setEmbedApiKeyDirty(true)
                      }}
                      placeholder={embedApiKeyMasked ? t('settings.savedKey', { value: embedApiKeyMasked }) : t('settings.apiKeyLocal')}
                      className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 pr-11 text-slate-950 outline-none placeholder:text-slate-400 focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-600"
                    />
                    <button
                      type="button"
                      onClick={() => setEmbedApiKeyVisible((value) => !value)}
                      className="absolute right-2 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                      aria-label={embedApiKeyVisible ? t('settings.hideKey') : t('settings.showKey')}
                      title={embedApiKeyVisible ? t('settings.hideKey') : t('settings.showKey')}
                    >
                      {embedApiKeyVisible ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
                    </button>
                  </div>
                </label>
                <label className="text-sm text-slate-500 dark:text-slate-400">
                  Embed Model
                  <input value={embedModel} onChange={(event) => setEmbedModel(event.target.value)} disabled={embedModelLocked && !dimEditing} placeholder="text-embedding-3-small" className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-slate-950 outline-none placeholder:text-slate-400 focus:border-violet-400 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-600 dark:disabled:bg-slate-900 dark:disabled:text-slate-500" />
                </label>
                <label className="text-sm text-slate-500 dark:text-slate-400">
                  <span className="group relative inline-flex items-center gap-1.5">
                    Embed Dim
                    <Info size={14} className="cursor-help text-slate-500 transition hover:text-slate-300" />
                    <span className="pointer-events-none absolute bottom-full left-0 z-30 mb-2 hidden w-64 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs leading-relaxed text-slate-600 shadow-xl group-hover:block dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300">
                      {t('settings.embedDimHelp')}
                    </span>
                  </span>
                  <input
                    type="number"
                    min={32}
                    max={4096}
                    value={embedDim}
                    onChange={(event) => setEmbedDim(Number(event.target.value))}
                    disabled={embedDimLocked && !dimEditing}
                    list="embed-dim-presets"
                    className="mt-2 h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-slate-950 outline-none focus:border-violet-400 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:disabled:bg-slate-900 dark:disabled:text-slate-500"
                  />
                  <datalist id="embed-dim-presets">
                    {dims.map((dim) => <option key={dim} value={dim} />)}
                  </datalist>
                  {(embedDimLocked || embedModelLocked) && !dimEditing && (
                    <button
                      type="button"
                      onClick={() => { setDimEditing(true); setSavedEmbedDim(embedDim); setSavedEmbedModel(embedModel) }}
                      className="mt-2 rounded-md border border-amber-500/50 px-3 py-1.5 text-xs text-amber-600 transition hover:bg-amber-50 hover:text-amber-700 dark:text-amber-400 dark:hover:bg-amber-500/10 dark:hover:text-amber-300"
                    >
                      {t('settings.changeDimOrModel')}
                    </button>
                  )}
                  {dimEditing && (
                    <div className="mt-2 flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          if (embedDim !== savedEmbedDim || embedModel !== savedEmbedModel) {
                            void saveEmbedSettings()
                          } else {
                            show(t('settings.dimModelUnchanged'), 'info')
                          }
                        }}
                        className="rounded-md bg-violet-500 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-violet-400"
                      >
                        {t('common.save')}
                      </button>
                      <button
                        type="button"
                        onClick={() => { setEmbedDim(savedEmbedDim); setEmbedModel(savedEmbedModel); setDimEditing(false) }}
                        className="rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                      >
                        {t('common.cancel')}
                      </button>
                    </div>
                  )}
                </label>
              </div>
              <div className="mt-4 flex justify-end gap-3">
                <button type="button" onClick={testEmbedConnection} className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
                  {t('settings.testConnection')}
                </button>
                <button type="button" onClick={saveEmbedSettings} className="rounded-md bg-violet-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-violet-300">
                  {t('common.save')}
                </button>
              </div>
              {embeddingStatus && (
                <div className="mt-4 rounded-md border border-slate-200 bg-white px-3 py-3 dark:border-slate-800 dark:bg-slate-950">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-slate-800 dark:text-slate-200">{t('settings.embeddingSync')}</div>
                      <div className="mt-1 text-xs text-slate-500">
                        {t('settings.synced', { done: embeddingStatus.embedded_atoms, total: embeddingStatus.active_atoms })}
                        {embeddingStatus.stale_atoms > 0 ? t('settings.stale', { count: embeddingStatus.stale_atoms }) : ''}
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2 text-xs">
                      <span className="rounded border border-slate-300 px-2 py-1 text-slate-500 dark:border-slate-700 dark:text-slate-400">pending {embeddingStatus.pending}</span>
                      <span className="rounded border border-slate-300 px-2 py-1 text-slate-500 dark:border-slate-700 dark:text-slate-400">running {embeddingStatus.running}</span>
                      <span className={`rounded border px-2 py-1 ${embeddingStatus.failed > 0 ? 'border-rose-500/60 text-rose-500 dark:text-rose-300' : 'border-slate-300 text-slate-500 dark:border-slate-700 dark:text-slate-400'}`}>failed {embeddingStatus.failed}</span>
                    </div>
                  </div>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
                    <div className="h-full bg-violet-400 transition-all" style={{ width: `${embeddingProgress}%` }} />
                  </div>
                  {embeddingStatus.last_error && (
                    <div className="mt-3 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs leading-5 text-rose-200">
                      {embeddingStatus.last_error}
                    </div>
                  )}
                  <div className="mt-3 flex justify-end">
                    <div className="flex flex-wrap justify-end gap-2">
                      <button
                        type="button"
                        onClick={chooseManualLinkResetAndRebuild}
                        disabled={rebuilding}
                        className="rounded-md border border-amber-500/50 px-3 py-1.5 text-xs text-amber-700 transition hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-60 dark:text-amber-300 dark:hover:bg-amber-500/10"
                      >
                        {rebuilding ? t('settings.rebuilding') : t('settings.rebuildEmbeddings')}
                      </button>
                      <button
                        type="button"
                        onClick={retryFailedEmbeddings}
                        disabled={retryingEmbeddings || embeddingStatus.failed === 0}
                        className="rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:border-slate-200 disabled:text-slate-400 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:disabled:border-slate-800 dark:disabled:text-slate-600"
                      >
                        {retryingEmbeddings ? t('settings.retrying') : t('settings.retryFailedTasks')}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              <div className="mt-4 rounded-md border border-slate-200 bg-white px-3 py-3 dark:border-slate-800 dark:bg-slate-950">
                <h3 className="text-sm font-medium text-slate-800 dark:text-slate-200">{t('settings.thresholds')}</h3>
                <div className="mt-4 space-y-5">
                  <label className="block text-sm text-slate-500 dark:text-slate-400">
                    <div className="mb-2 flex justify-between">
                      <span>{t('settings.autoConfirm')}</span>
                      <span className="font-mono text-slate-950 dark:text-slate-100">{autoThreshold.toFixed(2)}</span>
                    </div>
                    <input type="range" min="0" max="1" step="0.01" value={autoThreshold} onChange={(event) => setAutoThreshold(Number(event.target.value))} className="w-full accent-violet-400" />
                  </label>
                  <label className="block text-sm text-slate-500 dark:text-slate-400">
                    <div className="mb-2 flex justify-between">
                      <span>{t('settings.suggestThreshold')}</span>
                      <span className="font-mono text-slate-950 dark:text-slate-100">{suggestThreshold.toFixed(2)}</span>
                    </div>
                    <input type="range" min="0" max="1" step="0.01" value={suggestThreshold} onChange={(event) => setSuggestThreshold(Number(event.target.value))} className="w-full accent-violet-400" />
                  </label>
                  {!thresholdsValid && <div className="rounded-md border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-sm text-amber-600 dark:text-amber-400">{t('settings.thresholdInvalid')}</div>}
                  <button
                    type="button"
                    disabled={!thresholdsValid}
                    onClick={saveThresholds}
                    className="rounded-md bg-violet-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-violet-300 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
                  >
                    {t('settings.saveThresholds')}
                  </button>
                </div>
              </div>
            </div>

            <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/50">
              <h2 className="text-sm font-medium text-emerald-400">Chat</h2>
              <p className="mt-1 text-xs text-slate-500">{t('settings.chatDesc')}</p>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="text-sm text-slate-500 dark:text-slate-400">
                  Base URL
                  <input value={chatBaseUrl} onChange={(event) => setChatBaseUrl(event.target.value)} placeholder="https://api.openai.com/v1" className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-slate-950 outline-none placeholder:text-slate-400 focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-600" />
                </label>
                <label className="text-sm text-slate-500 dark:text-slate-400">
                  API Key
                  <div className="relative mt-2">
                    <input
                      type={chatApiKeyVisible ? 'text' : 'password'}
                      value={chatApiKey}
                      onChange={(event) => {
                        setChatApiKey(event.target.value)
                        setChatApiKeyDirty(true)
                      }}
                      placeholder={chatApiKeyMasked ? t('settings.savedKey', { value: chatApiKeyMasked }) : 'sk-...'}
                      className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 pr-11 text-slate-950 outline-none placeholder:text-slate-400 focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-600"
                    />
                    <button
                      type="button"
                      onClick={() => setChatApiKeyVisible((value) => !value)}
                      className="absolute right-2 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                      aria-label={chatApiKeyVisible ? t('settings.hideKey') : t('settings.showKey')}
                      title={chatApiKeyVisible ? t('settings.hideKey') : t('settings.showKey')}
                    >
                      {chatApiKeyVisible ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
                    </button>
                  </div>
                </label>
                <label className="text-sm text-slate-500 dark:text-slate-400">
                  Chat Model
                  <input value={chatModel} onChange={(event) => setChatModel(event.target.value)} placeholder="gpt-4.1-mini" className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-slate-950 outline-none placeholder:text-slate-400 focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-600" />
                </label>
              </div>
              <div className="mt-4 flex justify-end gap-3">
                <button type="button" onClick={testChatConnection} className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
                  {t('settings.testConnection')}
                </button>
                <button type="button" onClick={saveChatSettings} className="rounded-md bg-violet-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-violet-300">
                  {t('common.save')}
                </button>
              </div>
            </div>

            <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/50">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-sm font-medium text-cyan-500 dark:text-cyan-400">{t('settings.trendProvider')}</h2>
                  <p className="mt-1 text-xs text-slate-500">{t('settings.trendProviderDesc')}</p>
                </div>
                <div className="text-right text-xs text-slate-500">
                  <div>{t('settings.trendEffectiveModel')}: {effectiveTrendModel || '-'}</div>
                  <div>{trendUsesChatFallback ? t('settings.trendUsingChat') : t('settings.trendUsingOverride')}</div>
                </div>
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="text-sm text-slate-500 dark:text-slate-400">
                  Base URL
                  <input value={trendBaseUrl} onChange={(event) => setTrendBaseUrl(event.target.value)} placeholder="http://localhost:11434" className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-slate-950 outline-none placeholder:text-slate-400 focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-600" />
                </label>
                <label className="text-sm text-slate-500 dark:text-slate-400">
                  API Key
                  <div className="relative mt-2">
                    <input
                      type={trendApiKeyVisible ? 'text' : 'password'}
                      value={trendApiKey}
                      onChange={(event) => {
                        setTrendApiKey(event.target.value)
                        setTrendApiKeyDirty(true)
                      }}
                      placeholder={trendApiKeyMasked ? t('settings.savedKey', { value: trendApiKeyMasked }) : t('settings.trendApiKeyPlaceholder')}
                      className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 pr-11 text-slate-950 outline-none placeholder:text-slate-400 focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-600"
                    />
                    <button
                      type="button"
                      onClick={() => setTrendApiKeyVisible((value) => !value)}
                      className="absolute right-2 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                      aria-label={trendApiKeyVisible ? t('settings.hideKey') : t('settings.showKey')}
                      title={trendApiKeyVisible ? t('settings.hideKey') : t('settings.showKey')}
                    >
                      {trendApiKeyVisible ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
                    </button>
                  </div>
                </label>
                <label className="text-sm text-slate-500 dark:text-slate-400">
                  Model
                  <input value={trendModel} onChange={(event) => setTrendModel(event.target.value)} placeholder="qwen2.5:7b" className="mt-2 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-slate-950 outline-none placeholder:text-slate-400 focus:border-violet-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-600" />
                </label>
              </div>
              <div className="mt-4 flex justify-end gap-3">
                <button type="button" onClick={testTrendConnection} disabled={trendProviderTesting} className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-400 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
                  {trendProviderTesting ? t('common.processing') : t('settings.testConnection')}
                </button>
                <button type="button" onClick={saveTrendProviderSettings} disabled={trendProviderSaving} className="rounded-md bg-violet-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-violet-300 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500">
                  {trendProviderSaving ? t('common.processing') : t('settings.saveTrendProvider')}
                </button>
              </div>
            </div>
          </section>
        )}

        {activeSection === 'trend' && <TrendSettingsSection />}
        {activeSection === 'social-media' && <SocialMediaSettingsSection />}
      </div>
    </div>
  )
}
