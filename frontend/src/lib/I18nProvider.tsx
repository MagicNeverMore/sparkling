import { createContext, useContext, useState, type ReactNode } from 'react'

export type Lang = 'zh' | 'en'

interface I18nCtx {
  lang: Lang
  setLang: (l: Lang) => void
  t: (key: string) => string
}

const STORAGE_KEY = 'sparkling-lang'

// ── 翻译表 ──
const zh: Record<string, string> = {
  'nav.inbox': '收件箱',
  'nav.graph': '知识图谱',
  'nav.search': '搜索',
  'nav.tasks': '任务',
  'nav.settings': '设置',
  'heatmap.title': '活跃',
  'heatmap.legend.less': '少',
  'heatmap.legend.more': '多',
  'theme.dark': '深色',
  'theme.light': '浅色',
  'theme.system': '跟随系统',
  'lang.switch': 'English',
}

const en: Record<string, string> = {
  'nav.inbox': 'Inbox',
  'nav.graph': 'Graph',
  'nav.search': 'Search',
  'nav.tasks': 'Tasks',
  'nav.settings': 'Settings',
  'heatmap.title': 'Activity',
  'heatmap.legend.less': 'Less',
  'heatmap.legend.more': 'More',
  'theme.dark': 'Dark',
  'theme.light': 'Light',
  'theme.system': 'System',
  'lang.switch': '中文',
}

const translations: Record<Lang, Record<string, string>> = { zh, en }

function getStoredLang(): Lang {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'zh' || v === 'en') return v
  } catch { /* noop */ }
  // Default to Chinese
  return 'zh'
}

const I18nContext = createContext<I18nCtx>({
  lang: 'zh',
  setLang: () => {},
  t: (k: string) => k,
})

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(getStoredLang)

  const setLang = (l: Lang) => {
    setLangState(l)
    try { localStorage.setItem(STORAGE_KEY, l) } catch { /* noop */ }
  }

  const t = (key: string): string => {
    return translations[lang][key] ?? key
  }

  return (
    <I18nContext.Provider value={{ lang, setLang, t }}>
      {children}
    </I18nContext.Provider>
  )
}

export function useI18n() {
  return useContext(I18nContext)
}
