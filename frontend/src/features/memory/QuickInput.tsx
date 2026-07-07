import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useI18n } from '../../lib/I18nProvider'
import { MAX_ATOM_CONTENT_CHARS } from '../../lib/limits'

interface Props {
  onSubmit: (content: string) => Promise<void>
}

export default function QuickInput({ onSubmit }: Props) {
  const { t } = useI18n()
  const [value, setValue] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const textarea = ref.current
    if (!textarea) return
    textarea.style.height = 'auto'
    textarea.style.height = `${textarea.scrollHeight}px`
  }, [value])

  const submit = async () => {
    const content = value.trim()
    if (!content || submitting) return
    if (content.length > MAX_ATOM_CONTENT_CHARS) return
    setSubmitting(true)
    await onSubmit(content)
    setValue('')
    setSubmitting(false)
    ref.current?.focus()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault()
      void submit()
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
      <textarea
        ref={ref}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={t('quick.placeholder')}
        maxLength={MAX_ATOM_CONTENT_CHARS}
        rows={2}
        className="max-h-60 min-h-20 w-full resize-none bg-transparent text-base leading-7 text-slate-950 outline-none placeholder:text-slate-400 dark:text-slate-100 dark:placeholder:text-slate-500"
      />
      <div className="mt-3 flex items-center justify-between">
        <span className="text-xs text-slate-500">Cmd+Enter · {value.length}/{MAX_ATOM_CONTENT_CHARS}</span>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!value.trim() || submitting}
          className="rounded-md bg-violet-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-violet-300 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
        >
          {t('quick.submit')}
        </button>
      </div>
    </section>
  )
}
