import { useEffect } from 'react'
import GraphLabels from '@/components/graph/GraphLabels'
import D3ForceGraph from '@/components/graph/D3ForceGraph'
import { useD3GraphData } from '@/hooks/useD3GraphData'
import { useTaskStore } from '@/stores/task'
import { useGraphStore } from '@/stores/graph'
import { useSettingsStore } from '@/stores/settings'

export default function GraphViewer() {
  const currentWorkspace = useTaskStore.use.currentWorkspace()
  const { graphData, loading, isLiveUpdating } = useD3GraphData()

  useEffect(() => {
    useGraphStore.getState().reset()
    useGraphStore.getState().clearSearchHighlight()
    useSettingsStore.getState().triggerSearchLabelDropdownRefresh()
  }, [currentWorkspace])

  return (
    <div className="relative h-full w-full overflow-hidden">
      <div className="absolute top-3 left-3 z-30 rounded-xl border border-white/70 bg-gradient-to-br from-white/95 via-white/85 to-white/60 p-2 shadow-[0_4px_20px_rgba(0,0,0,0.06)] backdrop-blur-sm">
        <GraphLabels />
      </div>
      <D3ForceGraph
        graphData={graphData}
        loading={loading}
        isLiveUpdating={isLiveUpdating}
      />
    </div>
  )
}
