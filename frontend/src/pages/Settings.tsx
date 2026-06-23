import { useEffect, useState } from 'react'
import ConfirmDialog from '../components/ConfirmDialog'
import { useToast } from '../components/useToast'
import { useSparklingStore } from '../lib/store'

const dims = [384, 768, 1024, 1536, 3072]

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
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [progress, setProgress] = useState(0)
  const thresholdsValid = autoThreshold >= suggestThreshold + 0.05

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

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-6 md:px-6">
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
            Embed Dim
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
