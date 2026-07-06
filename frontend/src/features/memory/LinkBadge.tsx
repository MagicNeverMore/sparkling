import { useI18n } from '../../lib/I18nProvider'

interface Props {
  suggested: number
  confirmed: number
}

export default function LinkBadge({ suggested, confirmed }: Props) {
  const { t } = useI18n()
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="rounded-md border border-violet-400/30 bg-violet-400/10 px-2 py-1 text-violet-400">
        {t('link.suggested', { count: suggested })}
      </span>
      <span className="rounded-md border border-emerald-400/30 bg-emerald-400/10 px-2 py-1 text-emerald-400">
        {t('link.confirmed', { count: confirmed })}
      </span>
    </div>
  )
}
