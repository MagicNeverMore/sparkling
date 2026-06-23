import AtomCard from '../components/AtomCard'
import EmptyState from '../components/EmptyState'
import QuickInput from '../components/QuickInput'
import { groupAtomsByTime } from '../lib/time'
import { useSparklingStore } from '../lib/store'

const skeletons = ['s1', 's2', 's3']

export default function Inbox() {
  const atoms = useSparklingStore((state) => state.atoms)
  const links = useSparklingStore((state) => state.links)
  const loading = useSparklingStore((state) => state.loading)
  const addAtom = useSparklingStore((state) => state.addAtom)
  const groups = groupAtomsByTime(atoms)

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-6">
      <QuickInput onSubmit={addAtom} />
      <div className="mt-6 space-y-6">
        {loading &&
          skeletons.map((item) => (
            <div key={item} className="rounded-xl border border-slate-800 bg-slate-900 p-4">
              <div className="h-4 w-3/4 rounded bg-slate-800" />
              <div className="mt-3 h-4 w-1/2 rounded bg-slate-800" />
              <div className="mt-5 h-8 w-full rounded bg-slate-800" />
            </div>
          ))}
        {!loading && atoms.length === 0 && <EmptyState title="把今天第一个想法记下来" description="快速记录之后，Sparkling 会把相关线索连起来。" />}
        {!loading &&
          Object.entries(groups).map(([label, items]) => (
            <section key={label}>
              <h2 className="mb-3 text-xs uppercase tracking-wide text-slate-500">{label}</h2>
              <div className="space-y-3">
                {items.map((atom) => (
                  <AtomCard key={atom.id} atom={atom} links={links} />
                ))}
              </div>
            </section>
          ))}
      </div>
    </div>
  )
}
