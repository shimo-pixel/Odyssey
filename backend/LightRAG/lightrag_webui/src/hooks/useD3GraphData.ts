import { useCallback, useEffect, useRef, useState } from 'react'
import { LightragGraphType, queryGraphs } from '@/api/lightrag'
import { useSettingsStore } from '@/stores/settings'
import { useBackendState } from '@/stores/state'
import { useTaskStore } from '@/stores/task'
import { useGraphStore } from '@/stores/graph'
import { errorMessage } from '@/lib/utils'
import { graphNodeLayoutFingerprint } from '@/lib/d3GraphLayout'

const PIPELINE_POLL_MS = 10_000
const IDLE_POLL_MS = 30_000

export function useD3GraphData() {
  const queryLabel = useSettingsStore.use.queryLabel()
  const graphQueryMaxDepth = useSettingsStore.use.graphQueryMaxDepth()
  const graphMaxNodes = useSettingsStore.use.graphMaxNodes()
  const graphDataVersion = useGraphStore.use.graphDataVersion()
  const pipelineBusy = useBackendState.use.pipelineBusy()
  const currentWorkspace = useTaskStore.use.currentWorkspace()

  const [graphData, setGraphData] = useState<LightragGraphType | null>(null)
  const [loading, setLoading] = useState(false)
  const [isLiveUpdating, setIsLiveUpdating] = useState(false)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const nodeLayoutFingerprintRef = useRef('')

  const fetchGraph = useCallback(
    async (options?: { silent?: boolean }) => {
      const label = queryLabel || '*'
      if (!options?.silent) {
        setLoading(true)
      }
      try {
        const data = await queryGraphs(label, graphQueryMaxDepth, graphMaxNodes)
        const nodeFingerprint = data?.nodes?.length
          ? graphNodeLayoutFingerprint(data.nodes)
          : ''
        if (
          nodeFingerprint !== nodeLayoutFingerprintRef.current ||
          options?.silent === false
        ) {
          nodeLayoutFingerprintRef.current = nodeFingerprint
          setGraphData(data)
        }
      } catch (error) {
        useBackendState.getState().setErrorMessage(errorMessage(error), 'Query Graphs Error!')
      } finally {
        if (!options?.silent) {
          setLoading(false)
        }
      }
    },
    [graphMaxNodes, graphQueryMaxDepth, queryLabel]
  )

  const refresh = useCallback(() => {
    return fetchGraph({ silent: false })
  }, [fetchGraph])

  useEffect(() => {
    nodeLayoutFingerprintRef.current = ''
    setGraphData(null)
    fetchGraph({ silent: false })
  }, [queryLabel, graphQueryMaxDepth, graphMaxNodes, graphDataVersion, currentWorkspace, fetchGraph])

  useEffect(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }

    const interval = pipelineBusy ? PIPELINE_POLL_MS : IDLE_POLL_MS
    setIsLiveUpdating(pipelineBusy)

    pollTimerRef.current = setInterval(() => {
      fetchGraph({ silent: true })
    }, interval)

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
      }
    }
  }, [pipelineBusy, fetchGraph, currentWorkspace, queryLabel])

  return {
    graphData,
    loading,
    isLiveUpdating,
    refresh
  }
}
