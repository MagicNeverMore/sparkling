import { useState, type FormEvent } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { ApiError } from '../lib/api'
import { useAuthStore } from '../lib/authStore'
import { useI18n } from '../lib/I18nProvider'

export default function AuthPage() {
  const initialized = useAuthStore((state) => state.initialized)
  const login = useAuthStore((state) => state.login)
  const register = useAuthStore((state) => state.register)
  const { t } = useI18n()
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      if (initialized) {
        await login({ username, password })
      } else {
        await register({ username, password, email })
      }
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-slate-50 px-4 py-10 text-slate-950 dark:bg-slate-950 dark:text-slate-100">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="mb-6">
          <p className="text-sm font-semibold tracking-wide text-violet-500">Sparkling</p>
          <h1 className="mt-2 text-xl font-semibold">
            {initialized ? t('auth.loginTitle') : t('auth.registerTitle')}
          </h1>
        </div>

        <label className="mb-4 block">
          <span className="mb-1 block text-sm text-slate-600 dark:text-slate-300">{t('auth.username')}</span>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-violet-400 dark:border-slate-700 dark:bg-slate-950"
            required
          />
        </label>

        {!initialized && (
          <label className="mb-4 block">
            <span className="mb-1 block text-sm text-slate-600 dark:text-slate-300">{t('auth.email')}</span>
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              type="email"
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-violet-400 dark:border-slate-700 dark:bg-slate-950"
            />
          </label>
        )}

        <label className="mb-2 block">
          <span className="mb-1 block text-sm text-slate-600 dark:text-slate-300">{t('auth.password')}</span>
          <span className="flex rounded-md border border-slate-300 bg-white focus-within:border-violet-400 dark:border-slate-700 dark:bg-slate-950">
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={initialized ? 'current-password' : 'new-password'}
              type={showPassword ? 'text' : 'password'}
              className="min-w-0 flex-1 rounded-md bg-transparent px-3 py-2 text-sm outline-none"
              required
            />
            <button
              type="button"
              onClick={() => setShowPassword((value) => !value)}
              className="px-3 text-slate-500 transition hover:text-slate-900 dark:hover:text-slate-200"
              title={showPassword ? t('auth.hidePassword') : t('auth.showPassword')}
            >
              {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
            </button>
          </span>
        </label>

        {!initialized && <p className="mb-4 text-xs text-slate-500">{t('auth.usernameHelp')}</p>}
        {error && <p className="mb-4 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-600 dark:bg-rose-950/50 dark:text-rose-200">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-violet-500 px-3 py-2 text-sm font-medium text-white transition hover:bg-violet-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? t('common.processing') : initialized ? t('auth.login') : t('auth.createAccount')}
        </button>
      </form>
    </div>
  )
}
