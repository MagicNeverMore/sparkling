import { useEffect, useState } from 'react'
import ConfirmDialog from '../components/ConfirmDialog'
import { useToast } from '../components/useToast'
import { api, ApiError } from '../lib/api'
import { useSparklingStore } from '../lib/store'

const dims = [384, 768, 1024, 1536, 3072]

type DatabaseBackend = 'sqlite' | 'postgresql'

interface DatabaseSettingsRaw {
  db_backend: DatabaseBackend
  db_path?: string | null
  postgresql_url?: string | null
  restart_required: boolean
}

export default function Settings() {
  const { show } = useToast()
  const atomCount = useSparklingStore((state) => state.atoms.length)
  const [baseUrl, setBaseUrl] = useState('https://api.openai.com/v1')
  const [apiKey, setApiKey] = useState('')
  const [embedModel, setEmbedModel] = useState('text-embedding-3-small')
  const [embedDim, setEmbedDim] = useState(1536)
  const [chatModel, setChatModel] = useState('gpt-4.1-mini')
  const [autoThreshold, setAutoThreshold] = useState(0.85)
  const [suggestThreshold, setSuggestThreshold] = useState(0.7)
  const [dbBackend, setDbBackend] = useState<DatabaseBackend>('sqlite')
  const [dbPath, setDbPath] = useState('./sparkling.db')
  const [postgresqlUrl, setPostgresqlUrl] = useState('')
  const [dbSaving, setDbSaving] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [progress, setProgress] = useState(0)
  const loadInitial = useSparklingStore((state) => state.loadInitial)
  const thresholdsValid = autoThreshold >= suggestThreshold + 0.05
  const databaseValid = dbBackend === 'sqlite' ? dbPath.trim().length > 0 : postgresqlUrl.trim().length > 0

  useEffect(() => {
    if (!rebuilding) return
    const timer = window.setInterval(() => {
      setProgress((value) => {
        const next = Math.min(100, value + 5)
        if (next === 100) {
          window.clearInterval(timer)
          window.setTimeout(() => {
            setRebuilding(false)
            setConfirmOpen(false)
            show('Embedding 重建完成', 'success')
          }, 250)
        }
        return next
      })
    }, 300)
    return () => window.clearInterval(timer)
  }, [rebuilding, show])

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

  const saveSettings = () => {
    // TODO(real-api): PUT /api/settings with provider and threshold values.
    show('设置已保存', 'success')
  }

  const testConnection = () => {
    // TODO(real-api): POST /api/settings/test-provider.
    if (Math.random() < 0.8) show('连接测试成功', 'success')
    else show('连接失败，请检查 Base URL 和 API Key', 'error')
  }

  const startRebuild = () => {
    // TODO(real-api): POST /api/settings/rebuild-embeddings and subscribe to progress.
    setProgress(0)
    setRebuilding(true)
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
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <label className="text-sm text-slate-400">
            Base URL
            <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} className="mt-2 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-violet-400" />
          </label>
          <label className="text-sm text-slate-400">
            API Key
            <input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} className="mt-2 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-violet-400" />
          </label>
          <label className="text-sm text-slate-400">
            Embed Model
            <input value={embedModel} onChange={(event) => setEmbedModel(event.target.value)} className="mt-2 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-violet-400" />
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
                Embedding 向量的维度。维度越高，语义表示越精细，能捕捉更多细微关联，但计算与存储开销也越大。需与所选模型支持的维度匹配，通常为 384、768、1024、1536 或 3072。
              </span>
            </span>
            <select value={embedDim} onChange={(event) => setEmbedDim(Number(event.target.value))} className="mt-2 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-violet-400">
              {dims.map((dim) => (
                <option key={dim} value={dim}>
                  {dim}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm text-slate-400 md:col-span-2">
            Chat Model
            <input value={chatModel} onChange={(event) => setChatModel(event.target.value)} className="mt-2 w-full rounded-md border border-slate-800 bg-slate-950 px-3 py-2 text-slate-100 outline-none focus:border-violet-400" />
          </label>
        </div>
        <div className="mt-5 flex justify-end gap-3">
          <button type="button" onClick={testConnection} className="rounded-md border border-slate-700 px-4 py-2 text-sm text-slate-300 transition hover:bg-slate-800">
            测试连接
          </button>
          <button type="button" onClick={saveSettings} className="rounded-md bg-violet-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-violet-300">
            保存
          </button>
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
            onClick={saveSettings}
            className="rounded-md bg-violet-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-violet-300 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
          >
            保存阈值
          </button>
        </div>
      </section>

      <section className="rounded-xl border border-rose-500/60 bg-slate-900 p-5">
        <h2 className="text-lg font-semibold text-rose-400">危险操作</h2>
        <p className="mt-2 text-sm leading-6 text-slate-400">切换 embedding provider 或维度后，需要重新生成所有想法的向量。</p>
        {rebuilding && (
          <div className="mt-4">
            <div className="h-2 overflow-hidden rounded-full bg-slate-800">
              <div className="h-full bg-rose-500 transition-all" style={{ width: `${progress}%` }} />
            </div>
            <div className="mt-2 text-right font-mono text-xs text-slate-500">{progress}%</div>
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
        <p>将重新生成全部 {atomCount} 条想法的向量，并基于当前阈值重新发现关联。这个 mock 流程约 6 秒。</p>
      </ConfirmDialog>
    </div>
  )
}
