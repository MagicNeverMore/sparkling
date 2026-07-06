import { useEffect, useState, type FormEvent } from 'react'
import { LogOut } from 'lucide-react'
import { ApiError } from '../lib/api'
import { useAuthStore } from '../lib/authStore'
import { useI18n } from '../lib/I18nProvider'
import { useToast } from '../components/useToast'

export default function UserProfile() {
  const user = useAuthStore((state) => state.user)
  const updateMe = useAuthStore((state) => state.updateMe)
  const logout = useAuthStore((state) => state.logout)
  const { t } = useI18n()
  const { show } = useToast()
  const [username, setUsername] = useState(user?.username ?? '')
  const [email, setEmail] = useState(user?.email ?? '')
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setUsername(user?.username ?? '')
    setEmail(user?.email ?? '')
  }, [user])

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await updateMe({ username, email, password })
      setPassword('')
      show(t('common.saved'), 'success')
    } catch (err) {
      const message = err instanceof ApiError || err instanceof Error ? err.message : String(err)
      setError(message)
      show(t('common.saveFailed'), 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-5 p-4 md:p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-950 dark:text-slate-100">{t('user.title')}</h1>
        <button
          type="button"
          onClick={() => void logout()}
          className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          <LogOut size={16} />
          {t('auth.logout')}
        </button>
      </div>

      <form
        onSubmit={handleSubmit}
        className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
      >
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

        <label className="mb-4 block">
          <span className="mb-1 block text-sm text-slate-600 dark:text-slate-300">{t('user.newPassword')}</span>
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            type="password"
            placeholder={t('user.passwordPlaceholder')}
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-violet-400 dark:border-slate-700 dark:bg-slate-950"
          />
        </label>

        {error && <p className="mb-4 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-600 dark:bg-rose-950/50 dark:text-rose-200">{error}</p>}

        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-violet-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-violet-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {saving ? t('common.processing') : t('common.save')}
        </button>
      </form>
    </div>
  )
}
