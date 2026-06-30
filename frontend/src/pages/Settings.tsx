import { useEffect, useState } from 'react'
import ConfirmDialog from '../components/ConfirmDialog'
import { useToast } from '../components/useToast'
import { api, ApiError } from '../lib/api'
import { useSparklingStore } from '../lib/store'

const dims = [384, 768, 1024, 1536, 2048, 3072]

type DatabaseBackend = 'sqlite' | 'postgresql'

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

export default function Settings() {
  const { show } = useToast()
  const atomCount = useSparklingStore((state) => state.atoms.length)
  const [embedBaseUrl, setEmbedBaseUrl] = useState('https://api.openai.com/v1')
  const [embedApiKey, setEmbedApiKey] = useState('')
  const [embedApiKeyDirty, setEmbedApiKeyDirty] = useState(false)
  const [embedApiKeyVisible, setEmbedApiKeyVisible] = useState(false)
  const [embedApiKeyMasked, setEmbedApiKeyMasked] = useState<string | null>(null)
  const [embedModel, setEmbedModel] = useState('text-embedding-3-small')
  const [embedDim, setEmbedDim] = useState(1536)
  const [embedDimLocked, setEmbedDimLocked] = useState(false)
  const [chatBaseUrl, setChatBaseUrl] = useState('https://api.openai.com/v1')
  const [chatApiKey, setChatApiKey] = useState('')
  const [chatApiKeyDirty, setChatApiKeyDirty] = useState(false)
  const [chatApiKeyVisible, setChatApiKeyVisible] = useState(false)
  const [chatApiKeyMasked, setChatApiKeyMasked] = useState<string | null>(null)
  const [chatModel, setChatModel] = useState('gpt-4.1-mini')
  const [autoThreshold, setAutoThreshold] = useState(0.85)
  const [suggestThreshold, setSuggestThreshold] = useState(0.7)
  const [dbBackend, setDbBackend] = useState<DatabaseBackend>('sqlite')
  const [dbPath, setDbPath] = useState('./sparkling.db')
  const [postgresqlUrl, setPostgresqlUrl] = useState('')
  const [dbSaving, setDbSaving] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [retryingEmbeddings, setRetryingEmbeddings] = useState(false)
  const [embeddingStatus, setEmbeddingStatus] = useState<EmbeddingStatusRaw | null>(null)
  const loadInitial = useSparklingStore((state) => state.loadInitial)
  const thresholdsValid = autoThreshold >= suggestThreshold + 0.05
  const databaseValid = dbBackend === 'sqlite' ? dbPath.trim().length > 0 : postgresqlUrl.trim().length > 0
  const embeddingProgress = embeddingStatus?.active_atoms
    ? Math.round((embeddingStatus.embedded_atoms / embeddingStatus.active_atoms) * 100)
    : 0

  const loadAiSettings = () => {
    void api
      .get<SettingsRaw>('/api/settings')
      .then((s) => {
        if (s.embed_base_url) setEmbedBaseUrl(s.embed_base_url)
        setEmbedApiKey(s.embed_api_key ?? '')
        setEmbedApiKeyDirty(false)
        setEmbedApiKeyMasked(s.embed_api_key_masked)
        if (s.embed_model) setEmbedModel(s.embed_model)
        if (s.embed_dim) setEmbedDim(s.embed_dim)
        setEmbedDimLocked(s.embed_dim_locked)
        if (s.chat_base_url) setChatBaseUrl(s.chat_base_url)
        setChatApiKey(s.chat_api_key ?? '')
        setChatApiKeyDirty(false)
        setChatApiKeyMasked(s.chat_api_key_masked)
        if (s.chat_model) setChatModel(s.chat_model)
        if (s.link_threshold_auto !== undefined) setAutoThreshold(s.link_threshold_auto)
        if (s.link_threshold_suggest !== undefined) setSuggestThreshold(s.link_threshold_suggest)
      })
      .catch((error) => {
        const message = error instanceof Error ? error.message : String(error)
        show(`读取 AI 设置失败：${message}`, 'error')
      })
  }

  const loadEmbeddingStatus = () => {
    void api
      .get<EmbeddingStatusRaw>('/api/settings/embedding-status')
      .then((status) => {
        setEmbeddingStatus(status)
        if (rebuilding && status.pending === 0 && status.running === 0) {
          setRebuilding(false)
          setConfirmOpen(false)
          show(status.failed > 0 ? 'Embedding 重建完成，但有失败任务' : 'Embedding 重建完成', status.failed > 0 ? 'warning' : 'success')
        }
      })
      .catch(() => {
        setEmbeddingStatus(null)
      })
  }

  useEffect(() => {
    loadAiSettings()
    loadEmbeddingStatus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const timer = window.setInterval(loadEmbeddingStatus, 4000)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rebuilding])

  // 数据库配置独立加载，不受 loadAiSettings 影响
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
        show(`读取数据库设置失败：${message}`, 'error')
      })
  }, [show])

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

  const saveEmbedSettings = async () => {
    try {
      const s = await api.put<SettingsRaw>('/api/settings', buildEmbedSettingsPayload())
      if (s.embed_dim) setEmbedDim(s.embed_dim)
      setEmbedDimLocked(s.embed_dim_locked)
      setEmbedApiKey(s.embed_api_key ?? '')
      setEmbedApiKeyDirty(false)
      setEmbedApiKeyMasked(s.embed_api_key_masked)
      show('Embedding 设置已保存', 'success')
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
      show('Chat 设置已保存', 'success')
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
      show('阈值已保存', 'success')
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(message, 'error')
    }
  }

  const testEmbedConnection = async () => {
    // 先保存当前 embed 配置再测试
    try {
      await api.put<SettingsRaw>('/api/settings', buildEmbedSettingsPayload())
    } catch {
      // 保存失败也继续测试（可能 embed_dim 锁定等）
    }
    try {
      const r = await api.post<TestProviderRaw>('/api/settings/test-provider')
      if (r.ok) show(`Embedding 连接成功 (${r.latency_ms}ms)`, 'success')
      else show(`Embedding 连接失败：${r.error}`, 'error')
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(`Embedding 连接失败：${message}`, 'error')
    }
  }

  const testChatConnection = async () => {
    // 先保存当前 chat 配置再测试
    try {
      await api.put<SettingsRaw>('/api/settings', buildChatSettingsPayload())
    } catch {
      // 保存失败也继续测试
    }
    try {
      const r = await api.post<TestProviderRaw>('/api/settings/test-chat-provider')
      if (r.ok) show(`Chat 连接成功 (${r.latency_ms}ms)`, 'success')
      else show(`Chat 连接失败：${r.error}`, 'error')
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(`Chat 连接失败：${message}`, 'error')
    }
  }

  const startRebuild = async () => {
    // 先保存当前配置再触发重建
    try {
      await api.put<SettingsRaw>('/api/settings', buildEmbedSettingsPayload())
    } catch {
      // 保存失败也继续
    }
    try {
      await api.post('/api/settings/rebuild-embeddings', {
        embed_dim: embedDim,
      })
      setRebuilding(true)
      loadEmbeddingStatus()
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(`重建失败：${message}`, 'error')
    }
  }

  const retryFailedEmbeddings = async () => {
    setRetryingEmbeddings(true)
    try {
      const result = await api.post<{ retried: number }>('/api/settings/retry-failed-embeddings')
      show(result.retried > 0 ? `已重试 ${result.retried} 个失败任务` : '没有失败任务需要重试', result.retried > 0 ? 'success' : 'info')
      loadEmbeddingStatus()
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(`重试失败：${message}`, 'error')
    } finally {
      setRetryingEmbeddings(false)
    }
  }

  const saveDatabaseSettings = async () => {
    if (!databaseValid) {
      show(dbBackend === 'sqlite' ? '请填写 SQLite 数据库路径' : '请填写 PostgreSQL URL', 'warning')
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
      show('数据库已切换；不会迁移已有数据', 'success')
    } catch (error) {
      const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
      show(message, 'error')
    } finally {
      setDbSaving(false)
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-6 md:px-6">
      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h1 className="text-lg font-semibold text-slate-100">数据库</h1>
        <div className="mt-4 flex w-fit overflow-hidden rounded-md border border-slate-700">
          <button
            type="button"
            onClick={() => setDbBackend('sqlite')}
            className={`px-4 py-2 text-sm transition ${
              dbBackend === 'sqlite'
                ? 'bg-slate-700 text-slate-100'
                : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
            }`}
          >
            SQLite
          </button>
          <button
            type="button"
            onClick={() => setDbBackend('postgresql')}
            className={`border-l border-slate-700 px-4 py-2 text-sm transition ${
              dbBackend === 'postgresql'
                ? 'bg-slate-700 text-slate-100'
                : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
            }`}
          >
            PostgreSQL
          </button>
        </div>

        <div className="mt-4 grid gap-4">
          {dbBackend === 'sqlite' ? (
            <label className="text-sm text-slate-400">
              SQLite DB Path
              <input
                value={dbPath}
                onChange={(event) => setDbPath(event.target.value)}
                className="mt-2 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-violet-400"
              />
            </label>
          ) : (
            <label className="text-sm text-slate-400">
              PostgreSQL URL
              <input
                value={postgresqlUrl}
                onChange={(event) => setPostgresqlUrl(event.target.value)}
                placeholder="postgresql://user:password@localhost:5432/sparkling"
                className="mt-2 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-violet-400"
              />
            </label>
          )}
        </div>

        <div className="mt-4 rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-400">
          切换会立即连接目标数据库并升级 schema；现有数据不会自动迁移。
        </div>

        <div className="mt-5 flex justify-end">
          <button
            type="button"
            disabled={!databaseValid || dbSaving}
            onClick={() => void saveDatabaseSettings()}
            className="rounded-md bg-violet-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-violet-300 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
          >
            {dbSaving ? '切换中…' : '切换数据库'}
          </button>
        </div>
      </section>

      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h1 className="text-lg font-semibold text-slate-100">AI Provider</h1>

        {/* ── Embedding ── */}
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-4">
          <h2 className="text-sm font-medium text-violet-400">Embedding</h2>
          <p className="mt-1 text-xs text-slate-500">用于生成想法语义向量，支持 OpenAI 兼容接口（OpenAI / DeepSeek / 智谱 / Ollama 等）。</p>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <label className="text-sm text-slate-400">
              Base URL
              <input value={embedBaseUrl} onChange={(event) => setEmbedBaseUrl(event.target.value)} placeholder="https://api.openai.com/v1" className="mt-2 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-violet-400 placeholder:text-slate-600" />
            </label>
            <label className="text-sm text-slate-400">
              API Key
              <div className="relative mt-2">
                <input
                  type={embedApiKeyVisible ? 'text' : 'password'}
                  value={embedApiKey}
                  onChange={(event) => {
                    setEmbedApiKey(event.target.value)
                    setEmbedApiKeyDirty(true)
                  }}
                  placeholder={embedApiKeyMasked ? `已保存 ${embedApiKeyMasked}` : '本地模型留空即可'}
                  className="w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 pr-11 text-slate-100 outline-none focus:border-violet-400 placeholder:text-slate-600"
                />
                <button
                  type="button"
                  onClick={() => setEmbedApiKeyVisible((value) => !value)}
                  className="absolute right-2 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-800 hover:text-slate-200"
                  aria-label={embedApiKeyVisible ? '隐藏 Embedding API Key' : '显示 Embedding API Key'}
                  title={embedApiKeyVisible ? '隐藏 API Key' : '显示 API Key'}
                >
                  {embedApiKeyVisible ? (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
                      <path d="M3 3l18 18" />
                      <path d="M10.7 5.1A10.7 10.7 0 0 1 12 5c5 0 9 4.5 10 7a13.2 13.2 0 0 1-3.2 4.3" />
                      <path d="M6.6 6.6A13 13 0 0 0 2 12c1 2.5 5 7 10 7 1.5 0 2.9-.4 4.1-1" />
                      <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
                    </svg>
                  ) : (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
                      <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
            </label>
            <label className="text-sm text-slate-400">
              Embed Model
              <input value={embedModel} onChange={(event) => setEmbedModel(event.target.value)} placeholder="text-embedding-3-small" className="mt-2 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-violet-400 placeholder:text-slate-600" />
            </label>
            <label className="text-sm text-slate-400">
              <span className="group relative inline-flex items-center gap-1.5">
                Embed Dim
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 16 16"
                  fill="currentColor"
                  className="h-3.5 w-3.5 cursor-help text-slate-500 transition hover:text-slate-300"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M8 15A7 7 0 1 0 8 1a7 7 0 0 0 0 14ZM8.93 6.588a2.065 2.065 0 0 0-1.947.319.75.75 0 1 1-.868-1.224 3.565 3.565 0 0 1 3.365-.55c.837.319 1.42 1.008 1.42 1.867 0 1.03-.669 1.764-1.318 2.26-.33.25-.697.464-.93.596v.394a.75.75 0 0 1-1.5 0V9.75c0-.613.377-1.079.865-1.442.259-.193.58-.4.819-.58C9.29 7.394 9.4 7.096 9.4 7c0-.37-.183-.58-.47-.693a2.065 2.065 0 0 0-.93-.28 2.06 2.06 0 0 0-.07-.007ZM8 12a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Z"
                    clipRule="evenodd"
                  />
                </svg>
                <span className="pointer-events-none absolute bottom-full left-0 z-30 mb-2 hidden w-64 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-xs leading-relaxed text-slate-300 shadow-xl group-hover:block">
                  Embedding 向量的维度。不同模型支持的 Embed Dim 不同，请按实际情况选择。维度越高，语义表示越精细，但计算与存储开销也越大。
                </span>
              </span>
              <select value={embedDim} onChange={(event) => setEmbedDim(Number(event.target.value))} disabled={embedDimLocked} className="mt-2 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-violet-400 h-10 disabled:cursor-not-allowed disabled:bg-slate-900 disabled:text-slate-500">
                {dims.map((dim) => (
                  <option key={dim} value={dim}>
                    {dim}
                  </option>
                ))}
              </select>
              {embedDimLocked && (
                <p className="mt-1 text-xs text-amber-400/80">维度已锁定（已有 embedding 数据）。如需更改请使用「重建 embedding」。</p>
              )}
            </label>
          </div>
          <div className="mt-4 flex justify-end gap-3">
            <button type="button" onClick={testEmbedConnection} className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-300 transition hover:bg-slate-800">
              测试连接
            </button>
            <button type="button" onClick={saveEmbedSettings} className="rounded-md bg-violet-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-violet-300">
              保存
            </button>
          </div>
          {embeddingStatus && (
            <div className="mt-4 rounded-md border border-slate-800 bg-slate-950 px-3 py-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-slate-200">Embedding 同步</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {embeddingStatus.embedded_atoms} / {embeddingStatus.active_atoms} 已同步
                    {embeddingStatus.stale_atoms > 0 ? `，${embeddingStatus.stale_atoms} 条待更新` : ''}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  <span className="rounded border border-slate-700 px-2 py-1 text-slate-400">pending {embeddingStatus.pending}</span>
                  <span className="rounded border border-slate-700 px-2 py-1 text-slate-400">running {embeddingStatus.running}</span>
                  <span className={`rounded border px-2 py-1 ${embeddingStatus.failed > 0 ? 'border-rose-500/60 text-rose-300' : 'border-slate-700 text-slate-400'}`}>failed {embeddingStatus.failed}</span>
                </div>
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-800">
                <div className="h-full bg-violet-400 transition-all" style={{ width: `${embeddingProgress}%` }} />
              </div>
              {embeddingStatus.last_error && (
                <div className="mt-3 rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs leading-5 text-rose-200">
                  {embeddingStatus.last_error}
                </div>
              )}
              <div className="mt-3 flex justify-end">
                <button
                  type="button"
                  onClick={retryFailedEmbeddings}
                  disabled={retryingEmbeddings || embeddingStatus.failed === 0}
                  className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:border-slate-800 disabled:text-slate-600"
                >
                  {retryingEmbeddings ? '重试中…' : '重试失败任务'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ── Chat ── */}
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/50 p-4">
          <h2 className="text-sm font-medium text-emerald-400">Chat</h2>
          <p className="mt-1 text-xs text-slate-500">用于想法摘要、主题聚类、内容建议等 LLM 功能（Phase 2）。当前仅存储配置。</p>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <label className="text-sm text-slate-400">
              Base URL
              <input value={chatBaseUrl} onChange={(event) => setChatBaseUrl(event.target.value)} placeholder="https://api.openai.com/v1" className="mt-2 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-violet-400 placeholder:text-slate-600" />
            </label>
            <label className="text-sm text-slate-400">
              API Key
              <div className="relative mt-2">
                <input
                  type={chatApiKeyVisible ? 'text' : 'password'}
                  value={chatApiKey}
                  onChange={(event) => {
                    setChatApiKey(event.target.value)
                    setChatApiKeyDirty(true)
                  }}
                  placeholder={chatApiKeyMasked ? `已保存 ${chatApiKeyMasked}` : 'sk-...'}
                  className="w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 pr-11 text-slate-100 outline-none focus:border-violet-400 placeholder:text-slate-600"
                />
                <button
                  type="button"
                  onClick={() => setChatApiKeyVisible((value) => !value)}
                  className="absolute right-2 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-slate-500 transition hover:bg-slate-800 hover:text-slate-200"
                  aria-label={chatApiKeyVisible ? '隐藏 Chat API Key' : '显示 Chat API Key'}
                  title={chatApiKeyVisible ? '隐藏 API Key' : '显示 API Key'}
                >
                  {chatApiKeyVisible ? (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
                      <path d="M3 3l18 18" />
                      <path d="M10.7 5.1A10.7 10.7 0 0 1 12 5c5 0 9 4.5 10 7a13.2 13.2 0 0 1-3.2 4.3" />
                      <path d="M6.6 6.6A13 13 0 0 0 2 12c1 2.5 5 7 10 7 1.5 0 2.9-.4 4.1-1" />
                      <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
                    </svg>
                  ) : (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
                      <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
            </label>
            <label className="text-sm text-slate-400">
              Chat Model
              <input value={chatModel} onChange={(event) => setChatModel(event.target.value)} placeholder="gpt-4.1-mini" className="mt-2 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-violet-400 placeholder:text-slate-600" />
            </label>
          </div>
          <div className="mt-4 flex justify-end gap-3">
            <button type="button" onClick={testChatConnection} className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-300 transition hover:bg-slate-800">
              测试连接
            </button>
            <button type="button" onClick={saveChatSettings} className="rounded-md bg-violet-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-violet-300">
              保存
            </button>
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h2 className="text-lg font-semibold text-slate-100">关联阈值</h2>
        <div className="mt-4 space-y-5">
          <label className="block text-sm text-slate-400">
            <div className="mb-2 flex justify-between">
              <span>自动确认</span>
              <span className="font-mono text-slate-100">{autoThreshold.toFixed(2)}</span>
            </div>
            <input type="range" min="0" max="1" step="0.01" value={autoThreshold} onChange={(event) => setAutoThreshold(Number(event.target.value))} className="w-full accent-violet-400" />
          </label>
          <label className="block text-sm text-slate-400">
            <div className="mb-2 flex justify-between">
              <span>建议门槛</span>
              <span className="font-mono text-slate-100">{suggestThreshold.toFixed(2)}</span>
            </div>
            <input type="range" min="0" max="1" step="0.01" value={suggestThreshold} onChange={(event) => setSuggestThreshold(Number(event.target.value))} className="w-full accent-violet-400" />
          </label>
          {!thresholdsValid && <div className="rounded-md border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-sm text-amber-400">自动确认必须至少比建议门槛高 0.05</div>}
          <button
            type="button"
            disabled={!thresholdsValid}
            onClick={saveThresholds}
            className="rounded-md bg-violet-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-violet-300 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
          >
            保存阈值
          </button>
        </div>
      </section>

      <section className="rounded-xl border border-rose-500/60 bg-slate-900 p-5">
        <h2 className="text-lg font-semibold text-rose-400">危险操作</h2>
        <p className="mt-2 text-sm leading-6 text-slate-400">切换 embedding provider 或维度后，需要重新生成所有想法的向量。</p>
        {embeddingStatus && (
          <div className="mt-4">
            <div className="h-2 overflow-hidden rounded-full bg-slate-800">
              <div className="h-full bg-rose-500 transition-all" style={{ width: `${embeddingProgress}%` }} />
            </div>
            <div className="mt-2 text-right font-mono text-xs text-slate-500">{embeddingProgress}%</div>
          </div>
        )}
        <button
          type="button"
          onClick={() => setConfirmOpen(true)}
          disabled={rebuilding}
          className="mt-4 rounded-md bg-rose-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-rose-400 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
        >
          重建 embedding
        </button>
      </section>

      <ConfirmDialog open={confirmOpen} title="重建 embedding" confirmLabel="开始重建" confirming={rebuilding} onCancel={() => setConfirmOpen(false)} onConfirm={startRebuild}>
        <p>将重新生成全部 {atomCount} 条想法的向量，并基于当前阈值重新发现关联。进度会按后台任务真实状态更新。</p>
      </ConfirmDialog>
    </div>
  )
}
