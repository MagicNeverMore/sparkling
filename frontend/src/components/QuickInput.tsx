import { useEffect, useRef, useState, type KeyboardEvent } from 'react'

interface Props {
  onSubmit: (content: string) => Promise<void>
}

export default function QuickInput({ onSubmit }: Props) {
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
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <textarea
        ref={ref}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="💭 把脑子里的东西扔进来…"
        rows={2}
        className="max-h-60 min-h-20 w-full resize-none bg-transparent text-base leading-7 text-slate-100 outline-none placeholder:text-slate-500"
      />
      <div className="mt-3 flex items-center justify-between">
        <span className="text-xs text-slate-500">Cmd+Enter</span>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!value.trim() || submitting}
          className="rounded-md bg-violet-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-violet-300 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
        >
          记录
        </button>
      </div>
    </section>
  )
}
