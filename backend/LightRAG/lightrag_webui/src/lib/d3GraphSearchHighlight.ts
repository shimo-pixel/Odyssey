import type { LightragGraphType } from '@/api/lightrag'
import { getNodeLabel } from '@/lib/d3GraphTheme'
import type { GraphSearchHighlightPayload } from '@/lib/embedGraphMessages'

export function findGraphNodeByEntityName(
  nodes: LightragGraphType['nodes'],
  name: string
): LightragGraphType['nodes'][number] | null {
  const trimmed = name.trim()
  if (!trimmed) {
    return null
  }
  const byId = nodes.find((n) => n.id === trimmed)
  if (byId) {
    return byId
  }
  const byLabel = nodes.find((n) => getNodeLabel(n) === trimmed)
  if (byLabel) {
    return byLabel
  }
  const lower = trimmed.toLowerCase()
  return (
    nodes.find((n) => {
      const label = getNodeLabel(n)
      return (
        label.includes(trimmed) ||
        trimmed.includes(label) ||
        label.toLowerCase() === lower
      )
    }) ?? null
  )
}

export function resolveGraphSearchHighlight(
  graphData: LightragGraphType,
  payload: GraphSearchHighlightPayload | null
): { nodeIds: string[]; edgeIds: string[]; focusNodeIds: string[] } {
  if (!payload) {
    return { nodeIds: [], edgeIds: [], focusNodeIds: [] }
  }

  const nodeIds = new Set<string>()
  const focusNodeIds = new Set<string>()

  for (const name of payload.focusEntityNames ?? []) {
    const node = findGraphNodeByEntityName(graphData.nodes, name)
    if (node) {
      focusNodeIds.add(node.id)
      nodeIds.add(node.id)
    }
  }

  for (const name of payload.entityNames) {
    const node = findGraphNodeByEntityName(graphData.nodes, name)
    if (node) {
      nodeIds.add(node.id)
    }
  }

  for (const rel of payload.relationships) {
    const src = findGraphNodeByEntityName(graphData.nodes, rel.source)
    const tgt = findGraphNodeByEntityName(graphData.nodes, rel.target)
    if (src) {
      nodeIds.add(src.id)
    }
    if (tgt) {
      nodeIds.add(tgt.id)
    }
  }

  return {
    nodeIds: [...nodeIds],
    edgeIds: [],
    focusNodeIds: [...focusNodeIds]
  }
}
