import GraphCanvas from '../components/GraphCanvas'
import { useSparklingStore } from '../lib/store'

export default function Graph() {
  const atoms = useSparklingStore((state) => state.atoms)
  const links = useSparklingStore((state) => state.links)
  const loading = useSparklingStore((state) => state.loading)

  if (loading) {
    return <div className="p-6 text-slate-500">加载图谱…</div>
  }

  return <GraphCanvas atoms={atoms} links={links} />
}
