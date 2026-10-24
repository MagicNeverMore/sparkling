import { useId, useRef, useState } from 'react'
import { Check, ChevronDown } from 'lucide-react'

interface Props {
  value: string
  options: string[]
  disabled: boolean
  onChange: (value: string) => void
}

export default function SeriesInput({ value, options, disabled, onChange }: Props) {
  const id = useId()
  const input = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(-1)
  const filtered = options.filter(option => option.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))
  const expanded = open && !disabled
  const select = (option: string) => {
    onChange(option)
    setOpen(false)
    setActive(-1)
  }

  return <div className="relative text-sm" onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false)
  }}>
    <label htmlFor={id}>系列</label>
    <div className="mt-1 flex rounded-md border border-slate-200 focus-within:border-violet-400 dark:border-slate-700">
      <input ref={input} id={id} role="combobox" aria-autocomplete="list" aria-expanded={expanded}
        aria-controls={`${id}-options`} aria-activedescendant={expanded && filtered[active] ? `${id}-option-${active}` : undefined}
        aria-describedby={`${id}-hint`} autoComplete="off" disabled={disabled} value={value}
        placeholder="选择已有系列，或输入新系列"
        onFocus={() => { setOpen(true); setQuery(''); setActive(-1) }}
        onChange={event => { onChange(event.target.value); setQuery(event.target.value); setOpen(true); setActive(-1) }}
        onKeyDown={event => {
          if (event.key === 'Escape') { setOpen(false); return }
          if (event.key === 'Tab') { setOpen(false); return }
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault()
            setOpen(true)
            if (filtered.length) setActive(index => event.key === 'ArrowDown' ? (index + 1) % filtered.length : (index <= 0 ? filtered.length - 1 : index - 1))
          }
          if (event.key === 'Enter' && expanded) {
            event.preventDefault()
            if (filtered[active]) select(filtered[active])
            else setOpen(false)
          }
        }} className="min-w-0 flex-1 rounded-l-md bg-transparent px-3 py-2 outline-none disabled:bg-slate-50 dark:bg-slate-950 dark:disabled:bg-slate-800" />
      <button type="button" disabled={disabled} aria-label="展开已有系列" aria-expanded={expanded}
        onMouseDown={event => event.preventDefault()} onClick={() => {
          if (expanded) setOpen(false)
          else { input.current?.focus(); setQuery(''); setActive(-1); setOpen(true) }
        }} className="rounded-r-md px-3 text-slate-500 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-500 disabled:bg-slate-50 dark:hover:bg-slate-800 dark:disabled:bg-slate-800"><ChevronDown size={16} /></button>
    </div>
    {!disabled && <p id={`${id}-hint`} className="mt-1 text-xs text-slate-500">可直接选择旧系列；输入新名称后，随选题一起保存。</p>}
    {expanded && <div className="absolute z-20 mt-1 w-full rounded-md border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
      <ul id={`${id}-options`} role="listbox" aria-label="已有系列" className="max-h-52 overflow-y-auto py-1">
        {filtered.map((option, index) => <li key={option} id={`${id}-option-${index}`} role="option" aria-selected={value === option}
          onMouseDown={event => event.preventDefault()} onMouseEnter={() => setActive(index)} onClick={() => select(option)}
          className={`flex cursor-pointer items-center justify-between gap-2 px-3 py-2 ${index === active ? 'bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-200' : 'text-slate-700 dark:text-slate-200'}`}>
          <span className="break-words">{option}</span>{value === option && <Check size={14} className="shrink-0" />}
        </li>)}
      </ul>
      {filtered.length === 0 && <p className="px-3 py-2 text-xs text-slate-500">{value.trim() ? `保存时将使用新系列「${value.trim()}」` : '暂无已有系列，可直接输入新名称。'}</p>}
    </div>}
  </div>
}
