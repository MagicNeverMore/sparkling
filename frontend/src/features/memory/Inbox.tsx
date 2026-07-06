import AtomCard from './AtomCard'
import EmptyState from '../../components/EmptyState'
import QuickInput from './QuickInput'
import { useToast } from '../../components/useToast'
import { groupAtomsByTime } from '../../lib/time'
import { useSparklingStore } from '../../lib/store'
import { useI18n } from '../../lib/I18nProvider'

const skeletons = ['s1', 's2', 's3']

export default function Inbox() {
  const { lang, t } = useI18n()
  const atoms = useSparklingStore((state) => state.atoms)
  const links = useSparklingStore((state) => state.links)
  const loading = useSparklingStore((state) => state.loading)
  const addAtom = useSparklingStore((state) => state.addAtom)
  const deleteAtom = useSparklingStore((state) => state.deleteAtom)
  const { show } = useToast()
  const groups = groupAtomsByTime(atoms, lang)

  const removeAtom = async (id: string) => {
    try {
      await deleteAtom(id)
      show(t('common.deleted'), 'info')
    } catch {
      show(t('common.deleteFailed'), 'error')
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-6">
      <QuickInput onSubmit={addAtom} />
      <div className="mt-6 space-y-6">
        {loading &&
          skeletons.map((item) => (
            <div key={item} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
              <div className="h-4 w-3/4 rounded bg-slate-200 dark:bg-slate-800" />
              <div className="mt-3 h-4 w-1/2 rounded bg-slate-200 dark:bg-slate-800" />
              <div className="mt-5 h-8 w-full rounded bg-slate-200 dark:bg-slate-800" />
            </div>
          ))}
        {!loading && atoms.length === 0 && <EmptyState title={t('inbox.empty.title')} description={t('inbox.empty.desc')} />}
        {!loading &&
          Object.entries(groups).map(([label, items]) => (
            <section key={label}>
              <h2 className="mb-3 text-xs uppercase tracking-wide text-slate-500">{label}</h2>
              <div className="space-y-3">
                {items.map((atom) => (
                  <AtomCard key={atom.id} atom={atom} links={links} onDelete={(id) => void removeAtom(id)} />
                ))}
              </div>
            </section>
          ))}
      </div>
    </div>
  )
}
